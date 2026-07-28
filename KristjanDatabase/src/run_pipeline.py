"""One-command pipeline: collect newest channel videos, fetch transcripts,
and produce a report.

Usage:
    python src/run_pipeline.py --channel-url "https://www.youtube.com/@Someone/videos" --limit 20

Exit code is nonzero ONLY for pipeline-level fatal errors (bad/placeholder
channel URL, channel unreachable, metadata file missing). An individual
video's missing transcript is not a fatal error - it's recorded in the
transcript report and the pipeline continues.
"""

from __future__ import annotations

import argparse
import sys

import collect_latest_videos
import fetch_transcripts
from utils import LATEST_VIDEOS_JSON, ensure_directories, is_placeholder_url, setup_logger

logger = setup_logger("run_pipeline", "run_pipeline.log")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full KristjanDatabase pipeline end to end.")
    parser.add_argument("--channel-url", required=True, help="URL of the channel's 'Videos' tab.")
    parser.add_argument("--limit", type=int, default=20, help="Number of newest videos to collect (default: 20).")
    parser.add_argument("--buffer", type=int, default=10, help="Extra candidates fetched beyond --limit.")
    parser.add_argument("--delay-min", type=float, default=1.0, help="Minimum delay between transcript requests.")
    parser.add_argument("--delay-max", type=float, default=3.0, help="Maximum delay between transcript requests.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if is_placeholder_url(args.channel_url):
        message = (
            "The channel URL is still a placeholder. Replace --channel-url with the real "
            "'Videos' tab URL (e.g. https://www.youtube.com/@ChannelName/videos) before running "
            "the pipeline. No network requests were made."
        )
        logger.error(message)
        print(f"\nERROR: {message}")
        return 1

    print("Step 0/3: Ensuring project folders exist...")
    ensure_directories()

    print(f"\nStep 1/3: Collecting the {args.limit} newest public videos from the channel...")
    try:
        records = collect_latest_videos.collect(
            args.channel_url, limit=args.limit, buffer=args.buffer, delay=args.delay_min
        )
    except Exception as exc:  # noqa: BLE001 - a collection failure is pipeline-fatal
        logger.error("Fatal error during video collection: %s", exc)
        print(f"\nPIPELINE FAILED at video collection: {exc}")
        return 1

    collect_latest_videos.save_metadata(records)
    collect_latest_videos.print_video_list(records)

    print("\nStep 2/3: Fetching transcripts for each video (this can take a while)...")
    try:
        report_rows = fetch_transcripts.run(
            LATEST_VIDEOS_JSON, delay_min=args.delay_min, delay_max=args.delay_max
        )
    except Exception as exc:  # noqa: BLE001 - only raised for pipeline-level problems (e.g. missing metadata file)
        logger.error("Fatal error during transcript fetching: %s", exc)
        print(f"\nPIPELINE FAILED at transcript fetching: {exc}")
        return 1

    print("\nStep 3/3: Writing transcript report...")
    fetch_transcripts.save_report(report_rows)
    fetch_transcripts.print_summary(report_rows)

    print("\nPipeline complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
