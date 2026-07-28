"""Collect metadata for the N most recently uploaded PUBLIC videos on a
YouTube channel's Videos tab, using yt-dlp only (no video/audio download,
no YouTube Data API key).

Usage:
    python src/collect_latest_videos.py --channel-url "https://www.youtube.com/@Someone/videos" --limit 20
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from typing import Any

import yt_dlp

from utils import (
    LATEST_VIDEOS_CSV,
    LATEST_VIDEOS_JSON,
    ensure_directories,
    is_placeholder_url,
    retry_with_backoff,
    setup_logger,
)
import json

logger = setup_logger("collect_latest_videos", "collect_latest_videos.log")

CSV_FIELDS = [
    "video_id",
    "title",
    "webpage_url",
    "upload_date",
    "timestamp",
    "duration",
    "channel",
    "channel_id",
]

# Statuses that mean "not a normal public, finished video" and should be skipped.
_UNAVAILABLE_STATUSES = {"private", "needs_auth", "subscriber_only", "premium_only"}
_LIVE_STATUSES_TO_SKIP = {"is_live", "is_upcoming"}


def _flat_video_ids(channel_url: str, fetch_count: int) -> list[str]:
    """Fast pass: list video IDs on the channel's Videos tab, newest first."""
    flat_opts = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "playlistend": fetch_count,
    }
    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    if info is None:
        raise RuntimeError("yt-dlp returned no data for the channel URL (channel unreachable or invalid).")

    entries = info.get("entries") or []
    video_ids: list[str] = []
    for entry in entries:
        if not entry:
            continue
        # A channel root URL can yield nested tab entries instead of videos directly.
        if entry.get("_type") == "url" and entry.get("ie_key") and not entry.get("id"):
            continue
        video_id = entry.get("id")
        if video_id:
            video_ids.append(video_id)

    return video_ids[:fetch_count]


@retry_with_backoff((yt_dlp.utils.ExtractorError, yt_dlp.utils.DownloadError), tries=3, base_delay=2.0, logger=logger)
def _extract_full_metadata(video_id: str) -> dict[str, Any]:
    """Slow pass: full extract_info for a single video (no download)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        raise RuntimeError(f"No metadata returned for video {video_id}")
    return info


def _is_public_finished_video(info: dict[str, Any]) -> tuple[bool, str]:
    availability = info.get("availability")
    live_status = info.get("live_status")

    if availability in _UNAVAILABLE_STATUSES:
        return False, f"availability={availability}"
    if live_status in _LIVE_STATUSES_TO_SKIP:
        return False, f"live_status={live_status}"
    return True, ""


def _to_record(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "video_id": info.get("id"),
        "title": info.get("title"),
        "webpage_url": info.get("webpage_url") or f"https://www.youtube.com/watch?v={info.get('id')}",
        "upload_date": info.get("upload_date"),
        "timestamp": info.get("timestamp"),
        "duration": info.get("duration"),
        "channel": info.get("channel") or info.get("uploader"),
        "channel_id": info.get("channel_id") or info.get("uploader_id"),
    }


def collect(channel_url: str, limit: int = 20, buffer: int = 10, delay: float = 1.0) -> list[dict[str, Any]]:
    """Collect up to `limit` newest public videos' metadata from a channel URL."""
    if is_placeholder_url(channel_url):
        raise ValueError(
            "The channel URL is still a placeholder (PASTE_KRISTJAN_CHANNEL_VIDEOS_URL_HERE). "
            "Replace --channel-url with the real 'Videos' tab URL before running this script."
        )

    fetch_count = limit + buffer
    logger.info("Listing up to %d candidate video IDs from channel Videos tab...", fetch_count)
    video_ids = _flat_video_ids(channel_url, fetch_count)
    logger.info("Found %d candidate video IDs.", len(video_ids))

    if not video_ids:
        raise RuntimeError(
            "No video entries found at the given channel URL. "
            "Confirm the URL points to a channel's 'Videos' tab."
        )

    records: list[dict[str, Any]] = []
    skipped = 0

    for i, video_id in enumerate(video_ids, start=1):
        if len(records) >= limit:
            break
        try:
            info = _extract_full_metadata(video_id)
        except Exception as exc:  # noqa: BLE001 - log and continue, one bad video shouldn't stop the batch
            logger.warning("[%d/%d] Skipping %s: could not fetch metadata (%s)", i, len(video_ids), video_id, exc)
            skipped += 1
            time.sleep(delay)
            continue

        ok, reason = _is_public_finished_video(info)
        if not ok:
            logger.info("[%d/%d] Skipping %s: %s", i, len(video_ids), video_id, reason)
            skipped += 1
            time.sleep(delay)
            continue

        records.append(_to_record(info))
        time.sleep(delay)

    if not records:
        raise RuntimeError("Found candidate videos, but none were public/available. Nothing to save.")

    def sort_key(record: dict[str, Any]) -> int:
        if record.get("timestamp") is not None:
            return int(record["timestamp"])
        upload_date = record.get("upload_date") or "00000000"
        return int(upload_date)

    records.sort(key=sort_key, reverse=True)
    records = records[:limit]

    logger.info("Collected %d public videos (%d skipped/unavailable).", len(records), skipped)
    return records


def save_metadata(records: list[dict[str, Any]]) -> None:
    ensure_directories()

    with LATEST_VIDEOS_JSON.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info("Saved JSON metadata to %s", LATEST_VIDEOS_JSON)

    with LATEST_VIDEOS_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key, "") for key in CSV_FIELDS})
    logger.info("Saved CSV metadata to %s", LATEST_VIDEOS_CSV)


def print_video_list(records: list[dict[str, Any]]) -> None:
    print(f"\nFound {len(records)} videos (newest to oldest):")
    for i, record in enumerate(records, start=1):
        title = record.get("title") or "(untitled)"
        upload_date = record.get("upload_date") or "unknown-date"
        print(f"{i:2d}. [{upload_date}] {title} - {record.get('webpage_url')}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect the newest public videos from a YouTube channel.")
    parser.add_argument("--channel-url", required=True, help="URL of the channel's 'Videos' tab.")
    parser.add_argument("--limit", type=int, default=20, help="Number of newest videos to collect (default: 20).")
    parser.add_argument(
        "--buffer",
        type=int,
        default=10,
        help="Extra candidates to fetch beyond --limit, to allow for unavailable/private/live skips.",
    )
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between per-video metadata requests.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        records = collect(args.channel_url, limit=args.limit, buffer=args.buffer, delay=args.delay)
    except ValueError as exc:
        logger.error(str(exc))
        print(f"\nERROR: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.error("Fatal error while collecting videos: %s", exc)
        print(f"\nERROR: {exc}")
        return 1

    save_metadata(records)
    print_video_list(records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
