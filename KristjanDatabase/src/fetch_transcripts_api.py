"""Fetch video metadata + English transcripts in bulk via the youtube-transcript.io
paid API, as an alternative to the direct-from-YouTube path in fetch_transcripts.py
when YouTube itself is rate-limiting/IP-blocking direct requests.

Requires YOUTUBE_TRANSCRIPT_IO_TOKEN in the repo-root .env file.

The API batches up to 50 video IDs per request and is rate-limited to 5
requests per 10 seconds (with a Retry-After header on 429), so covering the
whole channel (588 videos = ~12 requests) takes well under a minute.

Bonus: each response item includes a `microformat` block with the video's
real upload date, duration, and channel info, so this also produces full
metadata for videos we never ran yt-dlp's per-video extraction on.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

from utils import (
    LATEST_VIDEOS_CSV,
    LATEST_VIDEOS_JSON,
    TRANSCRIPTS_DIR,
    TRANSCRIPT_REPORT_CSV,
    TRANSCRIPT_REPORT_JSON,
    Segment,
    ensure_directories,
    format_hhmmss,
    get_env,
    normalize_whitespace,
    safe_filename,
    setup_logger,
    timestamped_url,
)

logger = setup_logger("fetch_transcripts_api", "fetch_transcripts_api.log")

API_URL = "https://www.youtube-transcript.io/api/transcripts"
BATCH_SIZE = 50
MIN_SECONDS_BETWEEN_REQUESTS = 2.2  # keeps us under 5 requests / 10 seconds

VIDEO_CSV_FIELDS = ["video_id", "title", "webpage_url", "upload_date", "timestamp", "duration", "channel", "channel_id"]
REPORT_FIELDS = [
    "video_id", "title", "upload_date", "transcript_status", "retrieval_method",
    "transcript_language", "is_generated", "segment_count",
    "output_json_path", "output_txt_path", "error_type", "error_message",
]


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _post_batch(ids: list[str], token: str, max_retries: int = 5) -> list[dict[str, Any]]:
    for attempt in range(1, max_retries + 1):
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
            json={"ids": ids},
            timeout=60,
        )
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "10"))
            logger.warning("API rate limit hit; sleeping %.0fs (attempt %d/%d)...", retry_after, attempt, max_retries)
            time.sleep(retry_after)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"Exceeded max retries ({max_retries}) on 429 rate-limit responses.")


def _upload_date_from_microformat(item: dict[str, Any]) -> str | None:
    publish_date = (
        item.get("microformat", {}).get("playerMicroformatRenderer", {}).get("publishDate")
    )
    if not publish_date:
        return None
    # publishDate is usually "YYYY-MM-DD" but for some (older livestream?) videos
    # comes back as a full ISO timestamp with timezone, e.g. "2021-02-23T07:10:59-08:00".
    # Only the date portion matters for our YYYYMMDD convention.
    date_part = publish_date.split("T", 1)[0]
    return date_part.replace("-", "")


def _video_record(item: dict[str, Any], fallback_title: str | None, fallback_url: str | None) -> dict[str, Any]:
    renderer = item.get("microformat", {}).get("playerMicroformatRenderer", {})
    video_id = item.get("id")
    duration = renderer.get("lengthSeconds")
    return {
        "video_id": video_id,
        "title": item.get("title") or fallback_title,
        "webpage_url": fallback_url or f"https://www.youtube.com/watch?v={video_id}",
        "upload_date": _upload_date_from_microformat(item),
        "timestamp": None,
        "duration": int(duration) if duration else None,
        "channel": renderer.get("ownerChannelName"),
        "channel_id": renderer.get("externalChannelId"),
    }


def _segments_from_item(item: dict[str, Any]) -> list[Segment]:
    tracks = item.get("tracks") or []
    if not tracks:
        return []
    raw_segments = tracks[0].get("transcript") or []
    segments = []
    for seg in raw_segments:
        text = normalize_whitespace(seg.get("text", ""))
        if not text:
            continue
        segments.append(Segment(start=float(seg["start"]), duration=float(seg["dur"]), text=text))
    return segments


def _write_transcript_outputs(video: dict[str, Any], segments: list[Segment], language_code: str) -> tuple[str, str]:
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
        "language": "English (auto-generated)" if language_code.startswith("en") else language_code,
        "language_code": language_code,
        # The API doesn't flag manual vs. auto-generated captions explicitly; cross-checked
        # against a known video and it matches YouTube's auto-generated track.
        "is_generated": True,
        "segments": [segment.to_dict() for segment in segments],
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    lines = [
        f"[{format_hhmmss(segment.start)}] ({timestamped_url(video_id, segment.start)}) {segment.text}"
        for segment in segments
    ]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return str(json_path), str(txt_path)


def run(video_ids: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """video_ids: list of {'video_id', 'title'?, 'webpage_url'?} dicts to fetch.

    Returns (video_records, report_rows).
    """
    ensure_directories()
    token = get_env("YOUTUBE_TRANSCRIPT_IO_TOKEN")
    if not token:
        raise RuntimeError(
            "YOUTUBE_TRANSCRIPT_IO_TOKEN not found. Add it to the repo-root .env file."
        )

    fallback_by_id = {v["video_id"]: v for v in video_ids}
    id_batches = _chunk([v["video_id"] for v in video_ids], BATCH_SIZE)

    video_records: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []

    for batch_num, batch_ids in enumerate(id_batches, start=1):
        logger.info("Batch %d/%d: requesting %d video(s)...", batch_num, len(id_batches), len(batch_ids))
        start_time = time.monotonic()
        items = _post_batch(batch_ids, token)

        for item in items:
            fallback = fallback_by_id.get(item.get("id"), {})
            video = _video_record(item, fallback.get("title"), fallback.get("webpage_url"))
            video_records.append(video)

            reason = item.get("playabilityStatus", {}).get("reason", "")
            segments = _segments_from_item(item)

            row = {
                "video_id": video["video_id"],
                "title": video["title"],
                "upload_date": video["upload_date"],
                "transcript_status": "failed",
                "retrieval_method": "youtube_transcript_io_api",
                "transcript_language": "",
                "is_generated": "",
                "segment_count": 0,
                "output_json_path": "",
                "output_txt_path": "",
                "error_type": "",
                "error_message": "",
            }

            if segments:
                language_code = item["tracks"][0].get("language", "en")
                json_path, txt_path = _write_transcript_outputs(video, segments, language_code)
                row.update(
                    {
                        "transcript_status": "success",
                        "transcript_language": "English (auto-generated)" if language_code.startswith("en") else language_code,
                        "is_generated": True,
                        "segment_count": len(segments),
                        "output_json_path": json_path,
                        "output_txt_path": txt_path,
                    }
                )
                logger.info("Success: %s [%d segments]", video["video_id"], len(segments))
            else:
                row["transcript_status"] = "no_transcript"
                row["error_type"] = "TranscriptUnavailable"
                row["error_message"] = reason or "No transcript track returned by API."
                logger.info("No transcript for %s (%s)", video["video_id"], reason)

            report_rows.append(row)

        elapsed = time.monotonic() - start_time
        if batch_num < len(id_batches) and elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)

    return video_records, report_rows


def _load_existing(path: Path, key: str = "video_id") -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        rows = json.load(f)
    return {row[key]: row for row in rows if row.get(key)}


def save_video_metadata(video_records: list[dict[str, Any]]) -> None:
    """Merge new/updated video records into the existing metadata file rather
    than overwriting it, so videos not covered by this run aren't lost."""
    merged = _load_existing(LATEST_VIDEOS_JSON)
    for record in video_records:
        merged[record["video_id"]] = record

    def sort_key(record: dict[str, Any]) -> str:
        return record.get("upload_date") or "00000000"

    all_records = sorted(merged.values(), key=sort_key, reverse=True)

    with LATEST_VIDEOS_JSON.open("w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    with LATEST_VIDEOS_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=VIDEO_CSV_FIELDS)
        writer.writeheader()
        for record in all_records:
            writer.writerow({key: record.get(key, "") for key in VIDEO_CSV_FIELDS})
    logger.info(
        "Merged %d new/updated video record(s); %d total in %s",
        len(video_records), len(all_records), LATEST_VIDEOS_JSON,
    )


def save_report(report_rows: list[dict[str, Any]]) -> None:
    """Merge new/updated report rows into the existing report rather than
    overwriting it, so rows for videos not covered by this run aren't lost."""
    merged = _load_existing(TRANSCRIPT_REPORT_JSON)
    for row in report_rows:
        merged[row["video_id"]] = row
    all_rows = list(merged.values())

    with TRANSCRIPT_REPORT_JSON.open("w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)
    with TRANSCRIPT_REPORT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({key: row.get(key, "") for key in REPORT_FIELDS})
    logger.info(
        "Merged %d new/updated report row(s); %d total in %s",
        len(report_rows), len(all_rows), TRANSCRIPT_REPORT_JSON,
    )


def print_summary(report_rows: list[dict[str, Any]]) -> None:
    total = len(report_rows)
    success = sum(1 for row in report_rows if row["transcript_status"] == "success")
    no_transcript = sum(1 for row in report_rows if row["transcript_status"] == "no_transcript")
    other_failures = total - success - no_transcript

    print("\n--- Transcript Retrieval Summary (youtube-transcript.io API) ---")
    print(f"Videos discovered: {total}")
    print(f"Transcripts retrieved: {success}")
    print(f"No transcript: {no_transcript}")
    print(f"Other failures: {other_failures}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk-fetch transcripts via the youtube-transcript.io API.")
    parser.add_argument(
        "--video-list",
        default=None,
        help="Path to a JSON file of {video_id, title, webpage_url} entries. "
        "Defaults to data/metadata/pending_caption_check.json (videos not yet "
        "confirmed either way), to avoid spending API quota on videos we "
        "already have a definitive answer for.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from utils import METADATA_DIR

    args = parse_args(argv)
    video_list_path = Path(args.video_list) if args.video_list else METADATA_DIR / "pending_caption_check.json"

    if not video_list_path.exists():
        print(f"\nERROR: video list not found: {video_list_path}")
        return 1

    with video_list_path.open("r", encoding="utf-8") as f:
        video_ids = json.load(f)

    try:
        video_records, report_rows = run(video_ids)
    except Exception as exc:  # noqa: BLE001
        logger.error("Fatal error: %s", exc)
        print(f"\nERROR: {exc}")
        return 1

    save_video_metadata(video_records)
    save_report(report_rows)
    print_summary(report_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
