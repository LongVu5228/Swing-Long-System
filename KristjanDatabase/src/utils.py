"""Shared helpers for the KristjanDatabase pipeline: paths, logging, retries,
filename safety, and subtitle-file parsing (VTT / JSON3) used by the yt-dlp
fallback transcript path."""

from __future__ import annotations

import functools
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

# src/utils.py -> parents[1] is the KristjanDatabase project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
METADATA_DIR = DATA_DIR / "metadata"
LOGS_DIR = PROJECT_ROOT / "logs"

LATEST_VIDEOS_JSON = METADATA_DIR / "latest_20_videos.json"
LATEST_VIDEOS_CSV = METADATA_DIR / "latest_20_videos.csv"
TRANSCRIPT_REPORT_JSON = METADATA_DIR / "transcript_report.json"
TRANSCRIPT_REPORT_CSV = METADATA_DIR / "transcript_report.csv"

# The repo-root .env (one level above this project) holds shared secrets for
# every tool in the repo, e.g. POLYGON_API_KEY. It's gitignored at the repo root.
ENV_FILE = PROJECT_ROOT.parent / ".env"

PLACEHOLDER_MARKERS = ("PASTE_KRISTJAN_CHANNEL_VIDEOS_URL_HERE", "PASTE_", "CHANNEL_URL")


def ensure_directories() -> None:
    """Create every data/log directory the pipeline needs, if missing."""
    for directory in (RAW_DIR, TRANSCRIPTS_DIR, METADATA_DIR, LOGS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def get_env(key: str, env_file: Path = ENV_FILE) -> str | None:
    """Read a KEY=value entry from the repo-root .env file (no external dependency).

    Falls back to a real environment variable of the same name if the .env
    file doesn't define it, so either storage approach works.
    """
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            file_key, _, value = line.partition("=")
            if file_key.strip() == key:
                value = value.strip().strip('"').strip("'")
                if value:
                    return value
    import os

    return os.environ.get(key) or None


def is_placeholder_url(channel_url: str) -> bool:
    """Return True if the channel URL still looks like the unfilled template value."""
    if not channel_url or not channel_url.strip():
        return True
    return any(marker in channel_url for marker in PLACEHOLDER_MARKERS)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logger(name: str, log_filename: str) -> logging.Logger:
    """Configure a logger that writes to both console and a rotating-free log file."""
    ensure_directories()
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        # Already configured (e.g. run_pipeline imported this module twice).
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(LOGS_DIR / log_filename, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# ---------------------------------------------------------------------------
# Retry with modest exponential backoff
# ---------------------------------------------------------------------------

T = TypeVar("T")


def retry_with_backoff(
    exceptions: tuple[type[BaseException], ...],
    tries: int = 3,
    base_delay: float = 1.5,
    max_delay: float = 8.0,
    logger: logging.Logger | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: retry a function on the given exceptions with exponential backoff.

    Intended for transient failures (network hiccups, rate limiting) - not for
    permanent failures like a disabled transcript, which should not be retried.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = base_delay
            last_error: BaseException | None = None
            for attempt in range(1, tries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # type: ignore[misc]
                    last_error = exc
                    if attempt == tries:
                        break
                    if logger:
                        logger.warning(
                            "Attempt %d/%d failed for %s: %s (retrying in %.1fs)",
                            attempt, tries, func.__name__, exc, delay,
                        )
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)
            assert last_error is not None
            raise last_error

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Text / filename helpers
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def normalize_whitespace(text: str) -> str:
    """Collapse runs of horizontal whitespace and trim ends, without altering wording."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RE.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    return " ".join(line for line in lines if line).strip()


def safe_filename(value: str, max_length: int = 150) -> str:
    """Strip characters that are invalid in Windows/POSIX filenames."""
    cleaned = _UNSAFE_FILENAME_RE.sub("_", value).strip().strip(".")
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned[:max_length] if cleaned else "untitled"


def format_hhmmss(seconds: float) -> str:
    """Format a seconds offset as HH:MM:SS for the plain-text transcript."""
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def timestamped_url(video_id: str, start_seconds: float) -> str:
    return f"https://www.youtube.com/watch?v={video_id}&t={int(start_seconds)}s"


# ---------------------------------------------------------------------------
# Segment dataclass shared by both transcript retrieval paths
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    start: float
    duration: float
    text: str

    @property
    def end(self) -> float:
        return self.start + self.duration

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": round(self.start, 3),
            "duration": round(self.duration, 3),
            "end": round(self.end, 3),
            "text": self.text,
        }


# ---------------------------------------------------------------------------
# Subtitle file parsers (yt-dlp fallback path)
# ---------------------------------------------------------------------------

_VTT_TIME_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})\s*-->\s*"
    r"(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})"
)
_VTT_TAG_RE = re.compile(r"<[^>]+>")


def _vtt_timestamp_to_seconds(stamp: str) -> float:
    parts = stamp.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        hours, minutes, seconds = "0", parts[0], parts[1]
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_vtt(path: Path) -> list[Segment]:
    """Parse a WebVTT subtitle file into deduplicated transcript segments.

    Auto-generated YouTube captions use "rolling" cues where each cue repeats
    part of the previous cue's text. Three cases are handled:
      - exact repeat, or new cue's text is a substring of the previous cue's
        text (shrinking/repeat) -> dropped entirely.
      - new cue's text starts with the previous cue's text (growing, the
        common case) -> only the newly-added trailing words are kept, timed
        to this cue.
      - anything else -> kept in full as a new segment.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", raw)

    segments: list[Segment] = []
    last_text = ""

    for block in blocks:
        match = _VTT_TIME_RE.search(block)
        if not match:
            continue
        start = _vtt_timestamp_to_seconds(match.group(1))
        end = _vtt_timestamp_to_seconds(match.group(2))

        text_lines = block[match.end():].strip().split("\n")
        cleaned_lines = [_VTT_TAG_RE.sub("", line).strip() for line in text_lines]
        full_text = normalize_whitespace(" ".join(cleaned_lines))

        if not full_text or full_text == "WEBVTT":
            continue
        if full_text == last_text or (last_text and full_text in last_text):
            continue

        if last_text and full_text.startswith(last_text):
            text = full_text[len(last_text):].strip()
            if not text:
                continue
        else:
            text = full_text

        segments.append(Segment(start=start, duration=max(0.0, end - start), text=text))
        last_text = full_text

    return segments


def parse_json3(path: Path) -> list[Segment]:
    """Parse a YouTube json3 caption file into transcript segments."""
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    segments: list[Segment] = []

    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        text = normalize_whitespace("".join(seg.get("utf8", "") for seg in segs))
        if not text:
            continue
        start_ms = event.get("tStartMs", 0)
        duration_ms = event.get("dDurationMs", 0)
        segments.append(
            Segment(start=start_ms / 1000.0, duration=duration_ms / 1000.0, text=text)
        )

    return segments


def find_subtitle_file(directory: Path, stem: str) -> tuple[Path | None, str | None]:
    """Locate a downloaded subtitle file for `stem` and report its format.

    Returns (path, format) where format is "json3" or "vtt", preferring json3
    since it carries cleaner per-cue boundaries.
    """
    json3_matches = sorted(directory.glob(f"{stem}.*.json3")) + sorted(directory.glob(f"{stem}.*.json"))
    if json3_matches:
        return json3_matches[0], "json3"

    vtt_matches = sorted(directory.glob(f"{stem}.*.vtt"))
    if vtt_matches:
        return vtt_matches[0], "vtt"

    return None, None


def iter_chunks(items: Iterable[T], size: int) -> Iterable[list[T]]:
    chunk: list[T] = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
