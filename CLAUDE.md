# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Clip is a personal opus.pro clone: turn long videos (YouTube URL or upload) into short 9:16 clips with burned-in karaoke captions. Single-user, single-process, runs locally on Windows.

## Commands

- **First-time setup:** `setup.bat` (creates `.venv` with Python 3.12, installs `requirements.txt`, makes `data/` subdirs, copies `.env.example` → `.env`).
- **Run the server:** `run.bat` → starts uvicorn at http://localhost:8000. There is no separate frontend build; [frontend/index.html](frontend/index.html) is served directly.
- **Install/update a dep:** edit `requirements.txt` then `.venv\Scripts\pip.exe install -r requirements.txt`. yt-dlp breaks often — `pip install -U yt-dlp` is the usual fix when downloads start failing.
- **No test suite or linter** is configured. Verify changes by running the server and processing a short clip end-to-end.

## Required external tools

- **Python 3.12** specifically (`setup.bat` uses `py -3.12`).
- **ffmpeg on PATH.** [backend/tools.py](backend/tools.py) resolves it once at import time and also falls back to the per-user winget location (`%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*`). On non-Windows or non-winget setups put ffmpeg on PATH; otherwise update `_find_ffmpeg()`.

## Architecture

The pipeline is linear and lives entirely in [backend/pipeline.py](backend/pipeline.py). One job = one background thread, kicked off from `POST /api/process` in [backend/main.py](backend/main.py). The thread mutates an in-memory `Job` record; the frontend polls `GET /api/jobs/{id}` for progress.

Stages, each its own module:

1. **[download.py](backend/download.py)** — yt-dlp for URLs, or normalize an uploaded file. Always produces `data/jobs/<id>/source.mp4` (h264+aac). Downstream stages assume this exact codec, so don't skip the normalize step even when the input is already mp4.
2. **[transcribe.py](backend/transcribe.py)** — faster-whisper with `word_timestamps=True`. The model is cached in a module-level global so back-to-back jobs reuse it. Returns `Segment`s containing `Word`s with start/end times. The longest stage by far — owns ~55% of the progress bar.
3. **[select.py](backend/select.py)** — sends a compact `[HH:MM:SS] text` transcript to the Anthropic SDK and parses strict JSON back. Then `_snap_to_words()` rounds the model's start/end to the nearest Whisper word boundary so clips never start mid-syllable. **Always go through the Anthropic SDK** — DeepSeek support is implemented by setting `ANTHROPIC_BASE_URL` to their Anthropic-compatible endpoint, no SDK swap. Don't introduce a second client.
4. **[reframe.py](backend/reframe.py)** — two-pass active-speaker-tracked 9:16 crop. Pass 1: mediapipe **FaceMesh** every `DETECT_EVERY` frames → `_pick_speaker_x()` scores each face by size × mouth-openness (lip-gap landmarks 13/14) so the crop follows whoever is *talking*, not just the biggest face → EMA smoothing. Pass 2: OpenCV reads the segment, crops per frame, pipes raw bgr24 frames to a single ffmpeg subprocess that encodes silent h264. Then `_mux_audio()` muxes the original audio back. The mouth-openness heuristic is deliberately not full audio-visual ASD — cheap, no extra deps, right ~80% of the time on interviews.
5. **[captions.py](backend/captions.py)** — emits ASS subtitles with per-word "karaoke" highlighting (one Dialogue event per active word). `burn()` calls ffmpeg's `ass` filter; note the Windows path escaping (`replace(":", r"\:")`) — libass on Windows is picky.

### Two cross-cutting things to know

- **External tools are resolved once in [backend/tools.py](backend/tools.py).** Every module imports `FFMPEG` and `YT_DLP_CMD` from there. Never call `"ffmpeg"` as a bare string in a subprocess — use `FFMPEG`.
- **`load_dotenv(override=True)` in [backend/main.py](backend/main.py) is deliberate.** If Claude Code (or another wrapper) is in the parent shell's env, an inherited `ANTHROPIC_BASE_URL` would silently override the user's `.env` and break DeepSeek mode. Don't change `override=True` to `False`.

### State

`Job` and `Clip` are dataclasses in [backend/jobs.py](backend/jobs.py), held in a process-local dict guarded by a lock. **Nothing is persisted across restarts** — by design. Outputs on disk under `data/jobs/<id>/` (intermediates) and `data/clips/<id>/` (final mp4s) survive, but the job index does not. If you're tempted to add a SQLite/JSON store, first check whether the use case justifies the complexity for a single-user local tool.

## Configuration

- **`.env`** — `ANTHROPIC_API_KEY` is required; `CLAUDE_MODEL` defaults to `claude-sonnet-4-6`. For DeepSeek, uncomment the `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` block in [.env.example](.env.example). For GPU users, set `WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE=float16`.
- **[style.md](style.md)** — appended to the clip-picker's system prompt at request time. The user edits this to retarget the tool to their channel's voice. Treat it as user content, not code; don't refactor it into Python constants.

## Conventions

- Each backend module starts with a docstring explaining *why* the approach was chosen, not what it does. Match that style if you add modules.
- Subprocess calls swallow stdout/stderr (`stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL`) — fine for the happy path, but temporarily remove those when debugging an ffmpeg/yt-dlp failure.
