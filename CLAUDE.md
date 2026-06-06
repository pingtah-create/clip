# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Clip is a personal opus.pro clone: turn long videos (YouTube URL or upload) into short 9:16 clips with burned-in karaoke captions, optionally auto-posting them to YouTube Shorts. Single-user, runs locally on Windows. Two entry points share the same pipeline:

- **Web UI** (`run.bat`) — paste a URL / upload, pick clips manually, download or upload per-clip.
- **Daemon** (`run_daemon.bat`) — autonomous loop: discovers videos from `channels.txt` (RSS) and `queries.txt` (YouTube search), clips them, and posts the strongest clips on a schedule.

## Commands

- **First-time setup:** `setup.bat` (creates `.venv` with Python 3.12, installs `requirements.txt`, makes `data/` subdirs, copies `.env.example` → `.env`).
- **Run the web server:** `run.bat` → uvicorn at http://localhost:8000. No frontend build; [frontend/index.html](frontend/index.html) is served directly. Has `--timeout-graceful-shutdown 1` so Ctrl+C doesn't hang on stuck ffmpeg.
- **Run the daemon:** `run_daemon.bat`, or directly: `python -m backend.daemon`. Useful flags: `--once` (single cycle then exit, for testing) and `--status` (human-readable dump of `data/processed.json`).
- **Authorize YouTube:** `python -m backend.youtube` runs the OAuth browser flow once; token cached in `data/youtube_token.json`.
- **Install/update a dep:** edit `requirements.txt` then `.venv\Scripts\pip.exe install -r requirements.txt`. yt-dlp breaks often — `pip install -U yt-dlp` is the usual fix when downloads start failing.
- **No test suite or linter.** Verify by running `--once` (or the web UI) on a short video end-to-end and watching one rendered clip. Several behaviors (zoom level, caption smoothness, active-speaker tracking) are **visual and can only be verified by watching output**, not from code.
- **Server hangs on Ctrl+C / port 8000 in use:** `Get-Process python, ffmpeg | Stop-Process -Force` in PowerShell.

## Required external tools

- **Python 3.12** specifically (`setup.bat` uses `py -3.12`).
- **ffmpeg on PATH.** [backend/tools.py](backend/tools.py) resolves it once at import and falls back to the per-user winget location (`%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*`). On non-Windows/non-winget setups put ffmpeg on PATH or update `_find_ffmpeg()`.

## Architecture

The clip pipeline is linear and lives in [backend/pipeline.py](backend/pipeline.py). One job = one `Job` record. The **web UI** runs `pipeline.run()` in a background thread (`POST /api/process` in [backend/main.py](backend/main.py)); the frontend polls `GET /api/jobs/{id}`. The **daemon** ([backend/daemon.py](backend/daemon.py)) runs `pipeline.run()` synchronously inside a timeout-guarded worker thread, one video at a time.

Pipeline stages, each its own module:

1. **[download.py](backend/download.py)** — yt-dlp for URLs, or normalize an uploaded file. Always produces `data/jobs/<id>/source.mp4` (h264+aac). Downstream assumes this exact codec — don't skip normalize even for mp4 input.
2. **[transcribe.py](backend/transcribe.py)** — faster-whisper with `word_timestamps=True`. Model cached in a module global so back-to-back jobs reuse it. Returns `Segment`s of `Word`s. The longest stage by far (~55% of the progress bar).
3. **[select.py](backend/select.py)** — sends a compact `[HH:MM:SS] text` transcript to the Anthropic SDK, parses strict JSON. `_snap_to_words()` rounds boundaries to Whisper word edges. Picks are filtered by `hook_strength` (a self-rated 1-100 the model returns for the opening line; clips below `MIN_HOOK_STRENGTH` are dropped) and sorted hook-first. The system prompt = `BASE_SYSTEM` + `style.md` + a performance-feedback block built from `data/top_performers.json`. **Always go through the Anthropic SDK** — DeepSeek is just `ANTHROPIC_BASE_URL` pointed at their compatible endpoint, no SDK swap, no second client.
4. **[reframe.py](backend/reframe.py)** — two-pass active-speaker-tracked 9:16 crop. Pass 1: mediapipe **FaceMesh** every `DETECT_EVERY` frames → `_pick_speaker_x()` scores each face by size × mouth-openness (lip landmarks 13/14) so the crop follows whoever's *talking*; also returns `face_coverage` (fraction of frames with a visible face). Pass 2: OpenCV crops per frame, pipes raw bgr24 to one ffmpeg subprocess, `_mux_audio()` re-adds audio. `reframe()` **returns face_coverage** — the pipeline rejects clips below `MIN_FACE_COVERAGE` (no speaker on screen = bad Short). `REFRAME_ZOOM_OUT` controls how wide the crop is (1.0 = tight/zoomed, higher = pulled back).
5. **[captions.py](backend/captions.py)** — ASS subtitles. Words are grouped into **stable cues** (a fixed text block that holds still on screen); within a cue, one Dialogue event per active word changes only that word's color/scale while the surrounding text stays steady — this is what reads as "smooth" (an earlier per-word sliding-window with block-level fades flickered, don't reintroduce it). Emphasis coloring: numbers→green, shock words→red, else yellow. A `Hook` style overlay shows the clip's hook big at the top for the first ~2s. `burn()` uses ffmpeg's `ass` filter; note the Windows path escaping (`replace(":", r"\:")`) — libass on Windows is picky.

### Cross-cutting things to know

- **External tools resolved once in [backend/tools.py](backend/tools.py).** Every module imports `FFMPEG` / `YT_DLP_CMD` from there. Never call bare `"ffmpeg"` in a subprocess.
- **`load_dotenv(override=True)`** in both [backend/main.py](backend/main.py) and [backend/daemon.py](backend/daemon.py) is deliberate — an inherited `ANTHROPIC_BASE_URL` (e.g. from a wrapper shell) would otherwise silently override `.env` and break DeepSeek mode. Don't change to `False`.
- **Windows console encoding:** [backend/daemon.py](backend/daemon.py) reconfigures stdout/stderr to UTF-8 at import — without it, the `→`/`↑`/`✓` progress markers crash the cycle under cp1252. Keep that, or use only ASCII in daemon prints.
- **YouTube quota:** free tier = 10,000 units/day, each upload = 1,600 → **~6 uploads/day**. The daemon sets `_quota_exhausted` on the first 429 and stops attempting uploads that cycle (rendered clips stay on disk). Tune volume via `DAEMON_N_CLIPS_PER_VIDEO` / `DAEMON_MIN_SCORE_TO_UPLOAD`.
- **DeepSeek returns a `thinking` block before the `text` block.** Filter content on `b.type == "text" and b.text`; `max_tokens` must be generous (16k) or thinking eats the whole budget and the JSON never arrives. `deepseek-v4-flash` has no thinking block and is the better pick for this task.

### State

`Job`/`Clip` dataclasses in [backend/jobs.py](backend/jobs.py) live in a process-local dict — **not persisted; the web UI loses its job index on restart** (clip files on disk survive). The **daemon does persist**: `data/processed.json` (every video it's seen, with per-clip scores/hooks/youtube_ids/upload outcomes — this is the debuggable record) and `data/top_performers.json` (highest-viewed past clips, fed back into the picker). First-run seeding (`FIRST_RUN_SEEDS_ONLY`) marks current videos as seen without processing so the daemon never backfills a busy channel.

## Configuration

- **`.env`** — `ANTHROPIC_API_KEY` required; `CLAUDE_MODEL` defaults to `claude-sonnet-4-6` (or `deepseek-v4-flash`). Whisper: `WHISPER_DEVICE=cuda` + `WHISPER_COMPUTE=float16` for GPU. YouTube: `YOUTUBE_PRIVACY` (`private`/`unlisted`/`public`), `YOUTUBE_DEFAULT_TAGS`. Daemon: `DAEMON_*` knobs (interval, clips/video, score floor, duration window, age limit, podcast bias, pipeline timeout, keep-intermediates). Quality: `MIN_HOOK_STRENGTH`, `MIN_FACE_COVERAGE`, `REFRAME_ZOOM_OUT`. See [.env.example](.env.example) for the full annotated list.
- **[style.md](style.md)** — appended to the picker's system prompt. User edits this to match their channel's voice. Treat as user content, not code — don't refactor into Python constants.
- **`channels.txt` / `queries.txt`** — daemon sources, one entry per line, `#` for comments. Re-read every cycle (no restart needed to edit). Person-name search queries tend to surface stale archive content that outranks new uploads; topic/event queries and the podcast bias help.

## Conventions

- Each backend module starts with a docstring explaining *why* the approach was chosen, not what it does. Match that style.
- Subprocess calls swallow stdout/stderr (`DEVNULL`) — fine for the happy path; temporarily remove when debugging an ffmpeg/yt-dlp failure.
- Secrets and state are gitignored: `.env`, `client_secret.json`, `data/youtube_token.json`, `data/processed.json`, `data/top_performers.json`. The repo is shared with collaborators — never commit these.
