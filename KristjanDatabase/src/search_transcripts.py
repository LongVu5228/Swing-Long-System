"""Full-text search over the local transcript database.

Usage:
    python src/search_transcripts.py "episodic pivot"
    python src/search_transcripts.py "gap up" --limit 10
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

from database import DB_PATH
from utils import format_hhmmss, timestamped_url

QUERY_SQL = """
SELECT
    segments.video_id,
    videos.title,
    videos.upload_date,
    segments.start,
    snippet(segments_fts, 0, '>>>', '<<<', ' ... ', 12) AS snippet,
    bm25(segments_fts) AS score
FROM segments_fts
JOIN segments ON segments.id = segments_fts.rowid
JOIN videos ON videos.video_id = segments.video_id
WHERE segments_fts MATCH ?
ORDER BY score
LIMIT ?
"""


def search(query: str, limit: int = 20, db_path=DB_PATH) -> list[sqlite3.Row]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}. Run src/database.py first.")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(QUERY_SQL, (query, limit)).fetchall()
    finally:
        con.close()


def print_results(query: str, rows: list[sqlite3.Row]) -> None:
    print(f"\nSearch: \"{query}\" - {len(rows)} match(es)\n")
    for i, row in enumerate(rows, start=1):
        stamp = format_hhmmss(row["start"])
        url = timestamped_url(row["video_id"], row["start"])
        date = row["upload_date"] or "unknown-date"
        title = row["title"] or "(untitled)"
        snippet = row["snippet"].replace("\n", " ")
        print(f"{i:2d}. [{date}] {title}")
        print(f"    [{stamp}] {snippet}")
        print(f"    {url}\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Full-text search over the transcript database.")
    parser.add_argument("query", help="Search text (SQLite FTS5 query syntax, e.g. episodic NEAR pivot).")
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of results (default: 20).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows = search(args.query, limit=args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: {exc}")
        return 1

    print_results(args.query, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
