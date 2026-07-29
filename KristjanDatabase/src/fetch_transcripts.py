"""Fetch English transcripts for every video listed in
data/metadata/latest_20_videos.json.

Primary method: youtube-transcript-api (manually created English transcript
preferred, automatic English captions as fallback within that library).

Fallback method: yt-dlp subtitle retrieval (skip download, write
subtitles/automatic subtitles, English language, VTT or json3 format) when
youtube-transcript-api fails entirely.

Never downloads video or audio. Never crashes the batch on a single video's
failure - errors are recorded in the transcript report.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from typing import Any

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from utils import (
    LATEST_VIDEOS_JSON,
    RAW_DIR,
    TRANSCRIPTS_DIR,
    TRANSCRIPT_REPORT_CSV,
    TRANSCRIPT_REPORT_JSON,
    Segment,
    ensure_directories,
    find_subtitle_file,
    normalize_whitespace,
    parse_json3,
    parse_vtt,
    retry_with_backoff,
    safe_filename,
    setup_logger,
    format_hhmmss,
    timestamped_url,
)

logger = setup_logger("fetch_transcripts", "fetch_transcripts.log")

ENGLISH_LANGUAGE_PRIORITY = ["en", "en-US", "en-GB", "en-orig"]

REPORT_FIELDS = [
    "video_id",
    "title",
    "upload_date",
    "transcript_status",
    "retrieval_method",
    "transcript_language",
    "is_generated",
    "segment_count",
    "output_json_path",
    "output_txt_path",
    "error_type",
    "error_message",
]


class TranscriptUnavailable(Exception):
    """Raised when no English transcript could be found by either method."""


# ---------------------------------------------------------------------------
# Primary method: youtube-transcript-api
# ---------------------------------------------------------------------------

@retry_with_backoff((CouldNotRetrieveTranscript,), tries=2, base_delay=2.0, logger=logger)
def _fetch_via_transcript_api(video_id: str) -> tuple[list[Segment], str, str, bool]:
    """Return (segments, language, language_code, is_generated) or raise."""
    ytt_api = YouTubeTranscriptApi()
    transcript_list = ytt_api.list(video_id)

    try:
        transcript = transcript_list.find_manually_created_transcript(ENGLISH_LANGUAGE_PRIORITY)
    except NoTranscriptFound:
        transcript = transcript_list.find_generated_transcript(ENGLISH_LANGUAGE_PRIORITY)

    fetched = transcript.fetch()
    segments = [
        Segment(start=snippet.start, duration=snippet.duration, text=normalize_whitespace(snippet.text))
        for snippet in fetched
        if normalize_whitespace(snippet.text)
    ]
    if not segments:
        raise TranscriptUnavailable(f"Transcript for {video_id} had zero usable segments.")

    return segments, fetched.language, fetched.language_code, fetched.is_generated


# ---------------------------------------------------------------------------
# Fallback method: yt-dlp subtitle retrieval
# ---------------------------------------------------------------------------

def _pick_english_lang(available: dict[str, Any]) -> str | None:
    for lang in ENGLISH_LANGUAGE_PRIORITY:
        if lang in available:
            return lang
    for lang in available:
        if lang.startswith("en"):
            return lang
    return None


def _fetch_via_ytdlp(video_id: str, webpage_url: str) -> tuple[list[Segment], str, str, bool]:
    """Inspect available subtitles, download the best English track, and parse it."""
    probe_opts = {"skip_download": True, "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(probe_opts) as ydl:
        info = ydl.extract_info(webpage_url, download=False)
    if info is None:
        raise TranscriptUnavailable(f"yt-dlp returned no info for {video_id}")

    manual_subs = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}

    lang = _pick_english_lang(manual_subs)
    is_generated = False
    if not lang:
        lang = _pick_english_lang(auto_subs)
        is_generated = True

    if not lang:
        raise TranscriptUnavailable(f"No English subtitles or automatic captions found for {video_id}")

    download_opts = {
        "skip_download": True,
        "writesubtitles": not is_generated,
        "writeautomaticsub": is_generated,
        "subtitleslangs": [lang],
        "subtitlesformat": "json3/vtt",
        "outtmpl": str(RAW_DIR / f"{video_id}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(download_opts) as ydl:
        ydl.download([webpage_url])

    sub_path, sub_format = find_subtitle_file(RAW_DIR, video_id)
    if sub_path is None:
        raise TranscriptUnavailable(f"yt-dlp reported subtitles for {video_id} but no file was written")

    segments = parse_json3(sub_path) if sub_format == "json3" else parse_vtt(sub_path)
    if not segments:
        raise TranscriptUnavailable(f"Subtitle file for {video_id} parsed to zero segments")

    language_name = "English" if lang.startswith("en") else lang
    return segments, language_name, lang, is_generated


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _write_outputs(
    video: dict[str, Any],
    segments: list[Segment],
    language: str,
    language_code: str,
    is_generated: bool,
) -> tuple[str, str]:
    video_id = video["video_id"]
    upload_date = video.get("upload_date") or "00000000"
    stem = safe_filename(f"{upload_date}_{video_id}")

    json_path = TRANSCRIPTS_DIR / f"{stem}.json"
    txt_path = TRANSCRIPTS_DIR / f"{stem}.txt"

    payload = {
        "video_id": video_id,
        "title": video.get("title"),
        "upload_date": upload_date,
        "video_url": video.get("webpage_url"),
        "language": language,
        "language_code": language_code,
        "is_generated": is_generated,
        "segments": [segment.to_dict() for segment in segments],
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    lines = []
    for segment in segments:
        stamp = format_hhmmss(segment.start)
        url = timestamped_url(video_id, segment.start)
        lines.append(f"[{stamp}] ({url}) {segment.text}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return str(json_path), str(txt_path)


# ---------------------------------------------------------------------------
# Per-video orchestration
# ---------------------------------------------------------------------------

def _expected_output_paths(video: dict[str, Any]) -> tuple[Any, Any]:
    upload_date = video.get("upload_date") or "00000000"
    stem = safe_filename(f"{upload_date}_{video.get('video_id')}")
    return TRANSCRIPTS_DIR / f"{stem}.json", TRANSCRIPTS_DIR / f"{stem}.txt"


def _load_confirmed_no_transcript_rows(report_path=TRANSCRIPT_REPORT_JSON) -> dict[str, dict[str, Any]]:
    """Video IDs whose last run confirmed (via both methods) there's no English
    transcript at all - as opposed to a rate-limit/network failure, which
    should still be retried. Skipping these on rerun avoids re-hammering
    YouTube for videos we already know the answer for.
    """
    if not report_path.exists():
        return {}
    with report_path.open("r", encoding="utf-8") as f:
        rows = json.load(f)
    return {row["video_id"]: row for row in rows if row.get("transcript_status") == "no_transcript"}


def _cached_report_row(video: dict[str, Any], json_path: Any, txt_path: Any) -> dict[str, Any]:
    with json_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return {
        "video_id": video.get("video_id"),
        "title": video.get("title"),
        "upload_date": video.get("upload_date"),
        "transcript_status": "success",
        "retrieval_method": "cached",
        "transcript_language": payload.get("language", ""),
        "is_generated": payload.get("is_generated", ""),
        "segment_count": len(payload.get("segments", [])),
        "output_json_path": str(json_path),
        "output_txt_path": str(txt_path),
        "error_type": "",
        "error_message": "",
    }


def process_video(video: dict[str, Any]) -> dict[str, Any]:
    video_id = video.get("video_id")
    title = video.get("title")
    upload_date = video.get("upload_date")
    webpage_url = video.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"

    report_row: dict[str, Any] = {
        "video_id": video_id,
        "title": title,
        "upload_date": upload_date,
        "transcript_status": "failed",
        "retrieval_method": "",
        "transcript_language": "",
        "is_generated": "",
        "segment_count": 0,
        "output_json_path": "",
        "output_txt_path": "",
        "error_type": "",
        "error_message": "",
    }

    if not video_id:
        report_row["error_type"] = "InvalidRecord"
        report_row["error_message"] = "Metadata record is missing video_id."
        return report_row

    segments: list[Segment] | None = None
    language = language_code = ""
    is_generated = False
    method = ""
    primary_error: Exception | None = None

    try:
        segments, language, language_code, is_generated = _fetch_via_transcript_api(video_id)
        method = "youtube_transcript_api"
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable, TranscriptUnavailable, CouldNotRetrieveTranscript) as exc:
        primary_error = exc
        logger.info("Primary method found no transcript for %s (%s); trying yt-dlp fallback.", video_id, exc.__class__.__name__)
    except Exception as exc:  # noqa: BLE001
        primary_error = exc
        logger.warning("Primary method errored for %s (%s); trying yt-dlp fallback.", video_id, exc)

    if segments is None:
        try:
            segments, language, language_code, is_generated = _fetch_via_ytdlp(video_id, webpage_url)
            method = "yt_dlp_subtitles"
        except Exception as fallback_exc:  # noqa: BLE001
            final_error = fallback_exc
            is_no_transcript = isinstance(
                primary_error, (TranscriptsDisabled, NoTranscriptFound, TranscriptUnavailable)
            ) and isinstance(fallback_exc, TranscriptUnavailable)
            report_row["transcript_status"] = "no_transcript" if is_no_transcript else "failed"
            report_row["error_type"] = final_error.__class__.__name__
            report_row["error_message"] = f"primary={primary_error}; fallback={final_error}" if primary_error else str(final_error)
            logger.error("No transcript available for %s: %s", video_id, report_row["error_message"])
            return report_row

    assert segments is not None
    try:
        json_path, txt_path = _write_outputs(video, segments, language, language_code, is_generated)
    except Exception as exc:  # noqa: BLE001
        report_row["transcript_status"] = "failed"
        report_row["error_type"] = exc.__class__.__name__
        report_row["error_message"] = f"Fetched transcript but failed to write output files: {exc}"
        logger.error("Write failure for %s: %s", video_id, exc)
        return report_row

    report_row.update(
        {
            "transcript_status": "success",
            "retrieval_method": method,
            "transcript_language": language,
            "is_generated": is_generated,
            "segment_count": len(segments),
            "output_json_path": json_path,
            "output_txt_path": txt_path,
        }
    )
    logger.info("Success (%s, %s): %s [%d segments]", method, language_code, video_id, len(segments))
    return report_row


# ---------------------------------------------------------------------------
# Batch driver + report
# ---------------------------------------------------------------------------

# Errors that mean "YouTube is throttling/blocking us right now", as opposed to
# "this specific video genuinely has no English captions". Retrying the latter
# immediately is pointless; the former just needs a real cooldown.
_RATE_LIMIT_ERROR_TYPES = {"IpBlocked", "RequestBlocked"}
_RATE_LIMIT_MESSAGE_MARKERS = ("429", "Too Many Requests", "blocking requests")

RATE_LIMIT_BASE_COOLDOWN = 20.0
RATE_LIMIT_MAX_COOLDOWN = 240.0


def _looks_rate_limited(row: dict[str, Any]) -> bool:
    if row.get("error_type") in _RATE_LIMIT_ERROR_TYPES:
        return True
    message = row.get("error_message", "") or ""
    return any(marker in message for marker in _RATE_LIMIT_MESSAGE_MARKERS)


def run(
    metadata_path=LATEST_VIDEOS_JSON,
    delay_min: float = 1.0,
    delay_max: float = 3.0,
    force: bool = False,
    batch_size: int | None = None,
    batch_cooldown: float = 90.0,
) -> list[dict[str, Any]]:
    ensure_directories()

    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Metadata file not found: {metadata_path}. Run collect_latest_videos.py first."
        )

    with metadata_path.open("r", encoding="utf-8") as f:
        videos = json.load(f)

    if not videos:
        raise RuntimeError(f"Metadata file {metadata_path} is empty; nothing to transcribe.")

    confirmed_no_transcript = {} if force else _load_confirmed_no_transcript_rows()

    report_rows: list[dict[str, Any]] = []
    consecutive_rate_limit_hits = 0
    processed_since_batch_start = 0

    for i, video in enumerate(videos, start=1):
        json_path, txt_path = _expected_output_paths(video)
        video_id = video.get("video_id")

        if not force and json_path.exists() and txt_path.exists():
            logger.info(
                "[%d/%d] Skipping %s (%s): transcript already on disk (use --force to refetch).",
                i, len(videos), video_id, video.get("title"),
            )
            report_rows.append(_cached_report_row(video, json_path, txt_path))
            continue

        if video_id in confirmed_no_transcript:
            logger.info(
                "[%d/%d] Skipping %s (%s): confirmed no English transcript last run (use --force to recheck).",
                i, len(videos), video_id, video.get("title"),
            )
            report_rows.append(confirmed_no_transcript[video_id])
            continue

        logger.info("[%d/%d] Processing %s (%s)", i, len(videos), video_id, video.get("title"))
        row = process_video(video)
        report_rows.append(row)
        processed_since_batch_start += 1

        if row["transcript_status"] != "success" and _looks_rate_limited(row):
            consecutive_rate_limit_hits += 1
            cooldown = min(
                RATE_LIMIT_BASE_COOLDOWN * (2 ** (consecutive_rate_limit_hits - 1)),
                RATE_LIMIT_MAX_COOLDOWN,
            )
            logger.warning(
                "Rate limit detected (%d in a row). Cooling down for %.0fs before continuing...",
                consecutive_rate_limit_hits, cooldown,
            )
            time.sleep(cooldown)
            continue

        consecutive_rate_limit_hits = 0
        if i >= len(videos):
            continue

        if batch_size and processed_since_batch_start >= batch_size:
            logger.info(
                "Processed a batch of %d videos. Cooling down for %.0fs before the next batch...",
                processed_since_batch_start, batch_cooldown,
            )
            time.sleep(batch_cooldown)
            processed_since_batch_start = 0
        else:
            time.sleep(random.uniform(delay_min, delay_max))

    return report_rows


def save_report(report_rows: list[dict[str, Any]]) -> None:
    ensure_directories()

    with TRANSCRIPT_REPORT_JSON.open("w", encoding="utf-8") as f:
        json.dump(report_rows, f, ensure_ascii=False, indent=2)
    logger.info("Saved JSON report to %s", TRANSCRIPT_REPORT_JSON)

    with TRANSCRIPT_REPORT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for row in report_rows:
            writer.writerow({key: row.get(key, "") for key in REPORT_FIELDS})
    logger.info("Saved CSV report to %s", TRANSCRIPT_REPORT_CSV)


def print_summary(report_rows: list[dict[str, Any]]) -> None:
    total = len(report_rows)
    success = sum(1 for row in report_rows if row["transcript_status"] == "success")
    no_transcript = sum(1 for row in report_rows if row["transcript_status"] == "no_transcript")
    other_failures = total - success - no_transcript

    print("\n--- Transcript Retrieval Summary ---")
    print(f"Videos discovered: {total}")
    print(f"Transcripts retrieved: {success}")
    print(f"No transcript: {no_transcript}")
    print(f"Other failures: {other_failures}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch English transcripts for collected videos.")
    parser.add_argument("--metadata-file", default=str(LATEST_VIDEOS_JSON), help="Path to latest_20_videos.json")
    parser.add_argument("--delay-min", type=float, default=1.0, help="Minimum delay between videos (seconds)")
    parser.add_argument("--delay-max", type=float, default=3.0, help="Maximum delay between videos (seconds)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refetch transcripts even if an output file already exists on disk.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Process this many videos, then pause for --batch-cooldown seconds before continuing "
        "(cached/skipped videos don't count). Helps avoid tripping YouTube's rate limiting on large runs.",
    )
    parser.add_argument(
        "--batch-cooldown",
        type=float,
        default=90.0,
        help="Seconds to pause between batches when --batch-size is set (default: 90).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from pathlib import Path

    args = parse_args(argv)
    try:
        report_rows = run(
            Path(args.metadata_file),
            delay_min=args.delay_min,
            delay_max=args.delay_max,
            force=args.force,
            batch_size=args.batch_size,
            batch_cooldown=args.batch_cooldown,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Fatal error while fetching transcripts: %s", exc)
        print(f"\nERROR: {exc}")
        return 1

    save_report(report_rows)
    print_summary(report_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
