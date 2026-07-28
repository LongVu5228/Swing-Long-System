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
python src/run_pipeline.py --channel-url "CHANNEL_URL" --limit 20
```

This runs the full pipeline in one command:
1. Creates any missing `data/` and `logs/` folders.
2. Collects metadata for the 20 newest public videos.
3. Fetches an English transcript for each video (manual captions preferred,
   automatic captions as fallback).
4. Writes a report showing which videos succeeded or failed.

You can also run each stage on its own:

```
python src/collect_latest_videos.py --channel-url "CHANNEL_URL" --limit 20
python src/fetch_transcripts.py
```

## 4. Where output files appear

```
data/metadata/latest_20_videos.json     Metadata for the newest videos (JSON)
data/metadata/latest_20_videos.csv      Same metadata, as a spreadsheet
data/metadata/transcript_report.json    Per-video success/failure report (JSON)
data/metadata/transcript_report.csv     Same report, as a spreadsheet
data/transcripts/{date}_{video_id}.json Full transcript with timestamps (JSON)
data/transcripts/{date}_{video_id}.txt  Readable transcript with [HH:MM:SS] links
data/raw/                               Temporary subtitle files from the yt-dlp fallback
logs/                                   Log files for each pipeline stage
```

Open the `.txt` files in any text editor, or the `.csv` files in Excel, to
browse and search the results. The `.json` files are best for programmatic
searching (e.g. loading into a script or a simple search index later).

## 5. Rerunning later for the newest videos

Just run the same command again:

```
python src/run_pipeline.py --channel-url "CHANNEL_URL" --limit 20
```

It re-collects the current newest 20 videos and re-fetches any transcripts
that are missing or changed. Existing transcript files for videos that are
still in the newest 20 are overwritten with fresh copies; older transcript
files from previous runs are **not** deleted, so your local database grows
over time as long as you don't clear `data/transcripts/`.

## 6. Common errors

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

## 7. Updating the packages

```
pip install --upgrade yt-dlp youtube-transcript-api
```

Do this whenever YouTube changes break collection or transcript fetching —
`yt-dlp` in particular is updated frequently to keep up with YouTube.
