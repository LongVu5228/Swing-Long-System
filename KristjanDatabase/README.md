# KristjanDatabase

A local, searchable database of YouTube video metadata and English
transcripts for a channel — built entirely with free, open-source tools
(`yt-dlp` and `youtube-transcript-api`). No video/audio is downloaded, no
paid scraping service is used, and no YouTube Data API key is required.

## 1. Create and activate a virtual environment (Windows)

Open a terminal in the `KristjanDatabase` folder and run:

```
python -m venv .venv
.venv\Scripts\activate
```

Your prompt should now start with `(.venv)`. If `python` isn't recognized,
see **Common errors** below.

## 2. Install dependencies

```
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Run the program

Replace `CHANNEL_URL` with the channel's **Videos** tab URL, e.g.
`https://www.youtube.com/@ChannelName/videos`:

```
python src/run_pipeline.py --channel-url "CHANNEL_URL" --limit 100
```

This runs the full pipeline in one command:
1. Creates any missing `data/` and `logs/` folders.
2. Collects metadata for the `--limit` newest public videos (default 20).
3. Fetches an English transcript for each video (manual captions preferred,
   automatic captions as fallback), skipping any video that already has a
   transcript saved on disk (pass `--force` to refetch everything).
4. Writes a report showing which videos succeeded or failed.
5. Builds `data/kristjan.db`, a local SQLite database with full-text search
   over every transcript collected so far.

You can also run each stage on its own:

```
python src/collect_latest_videos.py --channel-url "CHANNEL_URL" --limit 100
python src/fetch_transcripts.py
python src/database.py
```

## 4. Searching the database

Once `data/kristjan.db` has been built, search it from the command line:

```
python src/search_transcripts.py "episodic pivot"
python src/search_transcripts.py "gap up" --limit 10
```

Each result shows the video title, upload date, a highlighted snippet, and a
timestamped YouTube link (`&t=123s`) that jumps straight to that moment in
the video. The query box accepts [SQLite FTS5 query syntax](https://www.sqlite.org/fts5.html#full_text_query_syntax)
— e.g. `episodic NEAR pivot`, `"exact phrase"`, `breakout OR pullback`.

You can also open `data/kristjan.db` directly with any SQLite browser (e.g.
[DB Browser for SQLite](https://sqlitebrowser.org/)) or query it yourself:

```sql
SELECT videos.title, segments.start, segments.text
FROM segments
JOIN videos ON videos.video_id = segments.video_id
WHERE segments.text LIKE '%episodic pivot%';
```

## 4b. Alternative: bulk fetch via youtube-transcript.io (paid)

If YouTube starts IP-blocking direct requests (`IpBlocked`/`RequestBlocked`/HTTP
429 in the logs — this happens on large channels after a few dozen videos),
`fetch_transcripts.py`'s direct-from-YouTube approach can grind to a halt for
hours regardless of network/IP changes. As a paid alternative,
[youtube-transcript.io](https://www.youtube-transcript.io) offers a simple
bulk API (up to 50 video IDs per request, 5 requests/10s) that doesn't hit
YouTube's per-IP throttling at all, and also returns upload date/duration/
channel metadata for free.

Setup:
1. Sign up at youtube-transcript.io and copy your API token.
2. Add it to the repo-root `.env` file (one level above `KristjanDatabase/`):
   ```
   YOUTUBE_TRANSCRIPT_IO_TOKEN=your-token-here
   ```
3. Run:
   ```
   python src/fetch_transcripts_api.py
   ```
   By default this reads `data/metadata/all_588_videos_flat.json` (or pass
   `--video-list path/to/file.json`, a JSON list of `{video_id, title,
   webpage_url}` entries) and only sends video IDs it doesn't already have a
   confirmed answer for, to conserve your monthly quota. Results merge into
   the same `latest_20_videos.json`/`transcript_report.json` files the rest
   of the pipeline uses, so `database.py` and `search_transcripts.py` work
   identically regardless of which fetch method was used.

**Be mindful of your plan's monthly quota** — check whether "no transcript
available" results count against it before running this against a very large
channel, since the docs don't state this explicitly.

## 5. Where output files appear

```
data/metadata/latest_20_videos.json     Metadata for the collected videos (JSON) - filename is historical, holds whatever --limit was used
data/metadata/latest_20_videos.csv      Same metadata, as a spreadsheet
data/metadata/transcript_report.json    Per-video success/failure report (JSON)
data/metadata/transcript_report.csv     Same report, as a spreadsheet
data/transcripts/{date}_{video_id}.json Full transcript with timestamps (JSON)
data/transcripts/{date}_{video_id}.txt  Readable transcript with [HH:MM:SS] links
data/kristjan.db                        SQLite database: videos, transcripts, segments + full-text search
data/raw/                               Temporary subtitle files from the yt-dlp fallback (not kept in git)
logs/                                   Log files for each pipeline stage (not kept in git)
```

Open the `.txt` files in any text editor, or the `.csv` files in Excel, to
browse the raw results. Use `search_transcripts.py` or a SQLite browser for
actual searching — that's what the database is for.

## 6. Rerunning later for the newest videos

Just run the same command again:

```
python src/run_pipeline.py --channel-url "CHANNEL_URL" --limit 100
```

It re-collects the current newest N videos and only fetches transcripts for
videos that don't already have one saved (fast reruns). Older transcript
files from previous runs are **not** deleted even if a video falls outside
the newest N next time, so your local archive only grows. The database step
always does a full rebuild from whatever is currently in `data/transcripts/`,
so it stays consistent even if you've fetched videos across several runs
with different `--limit` values.

## 7. Common errors

- **`'python' is not recognized...`** — Python isn't installed or isn't on
  your PATH. Install Python from python.org and make sure "Add Python to
  PATH" is checked during setup, then open a new terminal.
- **yt-dlp outdated / channel listing looks wrong or empty** — YouTube
  changes frequently and old yt-dlp versions break. Update it (see below).
- **`transcript disabled` / no transcript for a video** — the uploader
  disabled captions entirely for that video. This is recorded in the report
  as `no_transcript`; the pipeline continues with the next video.
- **No English captions available** — the video only has captions in other
  languages (or none at all). Also recorded as `no_transcript`.
- **YouTube request blocking / `RequestBlocked` / `IpBlocked`** — you made
  too many requests too quickly, or YouTube is temporarily rate-limiting
  your IP. Wait a while before rerunning; the pipeline already adds a
  1-3 second delay between transcript requests to reduce this risk.
- **Members-only / private video** — these are skipped automatically during
  collection (they are not public) and never reach the transcript step.
- **`Sign in to confirm your age`** — the video is age-restricted. yt-dlp
  cannot fetch it without a signed-in cookie, which this tool intentionally
  does not use. It's skipped automatically and logged as unavailable.

## 7. Updating the packages

```
pip install --upgrade yt-dlp youtube-transcript-api
```

Do this whenever YouTube changes break collection or transcript fetching —
`yt-dlp` in particular is updated frequently to keep up with YouTube.
