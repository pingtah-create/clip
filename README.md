# Clip

Personal opus.pro clone — turn long videos into short vertical clips with AI, optionally posting them to your own YouTube channel automatically.

**Pipeline:** YouTube URL or upload → Whisper transcript → Claude picks viral moments → face-tracked 9:16 reframe → burned-in karaoke captions → manual review or auto-post to YouTube Shorts.

## Quick setup

1. Install prereqs:
   - Python 3.12 (`py -3.12 --version`)
   - ffmpeg on PATH (`ffmpeg -version`)
2. Run `setup.bat` once (creates venv, installs deps).
3. Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.
   - To use DeepSeek V4 instead (cheaper, faster), uncomment the DeepSeek block in `.env.example`. Same SDK — just sets `ANTHROPIC_BASE_URL` to DeepSeek's compatible endpoint.

## Two ways to use it

### A. Web UI — manual one-off clipping

```
run.bat
```

Open http://localhost:8000. Paste a YouTube URL or upload a file, pick clip length (Short/Standard/Long) and count, hit "Make clips." Each finished clip has Download + Upload-to-YouTube buttons. Bulk "Upload all" button on the job card.

### B. Daemon — autonomous discovery and posting

```
run_daemon.bat
```

Polls every `DAEMON_INTERVAL_HOURS` (default 4), finds new videos from `channels.txt` (RSS) and `queries.txt` (YouTube search), runs them through the pipeline, posts the highest-scored clips to YouTube. State persists in `data/processed.json` so it never reprocesses.

**First-run safety:** on a fresh `data/processed.json`, the daemon just seeds "already-seen" markers without processing — so it doesn't backfill a year of work the first time you point it at a busy channel. Disable by editing `FIRST_RUN_SEEDS_ONLY = False` in `backend/daemon.py`.

## YouTube auto-upload setup (optional)

Skip this if you only want manual download via the web UI.

1. Create a Google Cloud project at https://console.cloud.google.com
2. Enable **YouTube Data API v3** for that project
3. Configure the OAuth consent screen as **External**, Testing mode, with your own Gmail as the only test user
4. Create OAuth 2.0 credentials → **Desktop app** type → download as `client_secret.json` into the project root
5. Authorize once:
   ```
   .venv\Scripts\python.exe -m backend.youtube
   ```
   A browser will open. Sign in with the Gmail that owns your YouTube channel, approve, done. The refresh token is cached in `data/youtube_token.json` (gitignored).

**Quota awareness:** YouTube's free tier is 10,000 quota units/day. Each upload costs 1,600 units → **~6 uploads/day max**. The daemon defaults (`DAEMON_N_CLIPS_PER_VIDEO=2`, `DAEMON_MIN_SCORE_TO_UPLOAD=85`) are tuned to stay within this. Once the daemon hits a 429, it stops attempting uploads for the rest of the cycle and resumes next cycle.

## Files you edit

- `style.md` — appended to Claude's system prompt. Defines your channel's voice (what's a viral hook, what to reject, title format). Default is finance/investor talking-head. Rewrite freely.
- `channels.txt` — channel URLs the daemon watches. One per line, `#` for comments.
- `queries.txt` — YouTube search queries the daemon runs every cycle. One per line.
- `.env` — API keys, model selection, daemon tuning knobs.

## Knobs in `.env`

**Anthropic / model:**
- `ANTHROPIC_API_KEY` — required. From console.anthropic.com or DeepSeek.
- `CLAUDE_MODEL` — default `claude-sonnet-4-6`. For DeepSeek use `deepseek-v4-flash` (faster, cheaper, no thinking-block).
- `ANTHROPIC_BASE_URL` — set to `https://api.deepseek.com/anthropic` to use DeepSeek.

**Whisper transcription:**
- `WHISPER_MODEL` — `tiny | base | small | medium | large-v3`. `small` is the CPU sweet spot.
- `WHISPER_DEVICE` — `cpu` or `cuda`. Default `cpu`.
- `WHISPER_COMPUTE` — `int8` (CPU) or `float16` (GPU).

**YouTube auto-upload:**
- `YOUTUBE_PRIVACY` — `private | unlisted | public`. Default `private` for safety. Daemon respects this.
- `YOUTUBE_DEFAULT_TAGS` — comma-separated tags added to every uploaded video.

**Daemon:**
- `DAEMON_INTERVAL_HOURS=4` — how often the daemon polls.
- `DAEMON_N_CLIPS_PER_VIDEO=2` — clips rendered per source video.
- `DAEMON_MIN_SCORE_TO_UPLOAD=85` — Claude's score floor for auto-upload.
- `DAEMON_MAX_VIDEO_DURATION_MIN=180` / `MIN=5` — source video length window.
- `DAEMON_MAX_VIDEO_AGE_DAYS=14` — search results older than this are skipped.
- `DAEMON_RESULTS_PER_QUERY=1` — top N fresh results per query per cycle.

## What the daemon outputs

- Processed videos: `data/processed.json` (state, gitignored)
- Per-job intermediates: `data/jobs/<id>/`
- Final clips: `data/clips/<id>/*.mp4`
- Posted clip IDs: visible in YouTube Studio under your channel

## File map

- `backend/main.py` — FastAPI app and HTTP routes
- `backend/pipeline.py` — orchestrates one clip job
- `backend/daemon.py` — autonomous loop
- `backend/download.py` — yt-dlp wrapper
- `backend/transcribe.py` — faster-whisper with word timings
- `backend/select.py` — Claude picks clips from transcript
- `backend/reframe.py` — mediapipe face tracking → 9:16 crop
- `backend/captions.py` — sliding-window karaoke ASS subtitles
- `backend/youtube.py` — OAuth + upload
- `backend/jobs.py` — in-memory job store
- `backend/tools.py` — resolves ffmpeg and yt-dlp paths
- `frontend/index.html` — single-page UI

## Troubleshooting

- **"ffmpeg not found":** update `_find_ffmpeg()` in `backend/tools.py` to your install path.
- **Server hangs on Ctrl+C:** `Get-Process python, ffmpeg | Stop-Process -Force` in PowerShell.
- **DeepSeek "Model returned no text" with `stop_reason=max_tokens`:** switch to `deepseek-v4-flash` (it doesn't emit a `thinking` block that eats the budget).
- **YouTube "quotaExceeded":** you hit 6 uploads today. Resets at midnight Pacific.
- **Captions don't appear in the rendered video:** check `data/jobs/<id>/clip_*/subs.ass` — if every Dialogue is on one line, the file is malformed; reopen an issue.
