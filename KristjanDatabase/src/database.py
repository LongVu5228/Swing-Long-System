"""Build a local searchable SQLite database from the collected video metadata
and transcript JSON files.

The database is fully rebuilt from data/metadata/*.json and
data/transcripts/*.json each time this runs, so it is always a clean,
consistent reflection of whatever is currently on disk - the JSON/CSV files
remain the source of truth; the database is a derived, queryable view over
them with full-text search (SQLite FTS5) on transcript text.

Usage:
    python src/database.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from utils import DATA_DIR, LATEST_VIDEOS_JSON, TRANSCRIPTS_DIR, ensure_directories, setup_logger

logger = setup_logger("database", "database.log")

DB_PATH = DATA_DIR / "kristjan.db"

SCHEMA_SQL = """
CREATE TABLE videos (
    video_id    TEXT PRIMARY KEY,
    title       TEXT,
    webpage_url TEXT,
    upload_date TEXT,
    timestamp   INTEGER,
    duration    INTEGER,
    channel     TEXT,
    channel_id  TEXT
);

CREATE TABLE transcripts (
    video_id       TEXT PRIMARY KEY REFERENCES videos(video_id),
    language       TEXT,
    language_code  TEXT,
    is_generated   INTEGER,
    segment_count  INTEGER,
    source_json    TEXT
);

CREATE TABLE segments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id   TEXT REFERENCES videos(video_id),
    seq        INTEGER,
    start      REAL,
    duration   REAL,
    end        REAL,
    text       TEXT
);
CREATE INDEX idx_segments_video_id ON segments(video_id);

CREATE VIRTUAL TABLE segments_fts USING fts5(
    text,
    content='segments',
    content_rowid='id'
);
"""


def _load_videos(metadata_path: Path) -> list[dict[str, Any]]:
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Metadata file not found: {metadata_path}. Run collect_latest_videos.py first."
        )
    with metadata_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _find_transcript_file(video: dict[str, Any]) -> Path | None:
    from utils import safe_filename

    upload_date = video.get("upload_date") or "00000000"
    stem = safe_filename(f"{upload_date}_{video.get('video_id')}")
    path = TRANSCRIPTS_DIR / f"{stem}.json"
    return path if path.exists() else None


def build(metadata_path: Path = LATEST_VIDEOS_JSON, db_path: Path = DB_PATH) -> dict[str, int]:
    """Rebuild the SQLite database from scratch. Returns summary counts."""
    ensure_directories()
    videos = _load_videos(metadata_path)
    if not videos:
        raise RuntimeError(f"Metadata file {metadata_path} is empty; nothing to build.")

    if db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(db_path)
    try:
        con.executescript(SCHEMA_SQL)

        video_count = 0
        transcript_count = 0
        segment_count = 0

        for video in videos:
            video_id = video.get("video_id")
            if not video_id:
                continue

            con.execute(
                """
                INSERT OR REPLACE INTO videos
                    (video_id, title, webpage_url, upload_date, timestamp, duration, channel, channel_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video_id,
                    video.get("title"),
                    video.get("webpage_url"),
                    video.get("upload_date"),
                    video.get("timestamp"),
                    video.get("duration"),
                    video.get("channel"),
                    video.get("channel_id"),
                ),
            )
            video_count += 1

            transcript_path = _find_transcript_file(video)
            if transcript_path is None:
                continue

            with transcript_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)

            segments = payload.get("segments", [])
            con.execute(
                """
                INSERT OR REPLACE INTO transcripts
                    (video_id, language, language_code, is_generated, segment_count, source_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    video_id,
                    payload.get("language"),
                    payload.get("language_code"),
                    1 if payload.get("is_generated") else 0,
                    len(segments),
                    str(transcript_path),
                ),
            )
            transcript_count += 1

            con.executemany(
                """
                INSERT INTO segments (video_id, seq, start, duration, end, text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (video_id, seq, seg.get("start"), seg.get("duration"), seg.get("end"), seg.get("text"))
                    for seq, seg in enumerate(segments)
                ],
            )
            segment_count += len(segments)

        con.execute("INSERT INTO segments_fts(rowid, text) SELECT id, text FROM segments")
        con.commit()

        logger.info(
            "Built database: %d videos, %d transcripts, %d segments -> %s",
            video_count, transcript_count, segment_count, db_path,
        )
        return {"videos": video_count, "transcripts": transcript_count, "segments": segment_count}
    finally:
        con.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local searchable SQLite database.")
    parser.add_argument("--metadata-file", default=str(LATEST_VIDEOS_JSON), help="Path to the video metadata JSON.")
    parser.add_argument("--db-path", default=str(DB_PATH), help="Output path for the SQLite database file.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        counts = build(Path(args.metadata_file), Path(args.db_path))
    except Exception as exc:  # noqa: BLE001
        logger.error("Fatal error while building database: %s", exc)
        print(f"\nERROR: {exc}")
        return 1

    print("\n--- Database Build Summary ---")
    print(f"Videos:      {counts['videos']}")
    print(f"Transcripts: {counts['transcripts']}")
    print(f"Segments:    {counts['segments']}")
    print(f"Database:    {args.db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
