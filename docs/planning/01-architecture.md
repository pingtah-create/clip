# 01 — Target Architecture

## Guiding principle

**Reuse the engine, replace the plumbing.** The `backend/` pipeline
(`download → transcribe → select → reframe → captions → verify`) stays. What changes: it must
run **statelessly** in a GPU worker, reading its input from and writing its output to object
storage instead of local disk, with job state in Postgres instead of an in-process dict.

## System diagram

```
                         ┌───────────────────────────────────────────┐
                         │  Next.js app (Vercel)                       │
   Browser ──────────────┤  • Marketing: landing, pricing, blog, docs  │
                         │  • App: dashboard, editor, publish, billing │
                         └───────────────┬─────────────────────────────┘
                                         │  HTTPS (REST/JSON)
                         ┌───────────────▼─────────────────────────────┐
                         │  API service — FastAPI (reuse backend/)      │
                         │  auth guard · projects · jobs · clips ·      │
                         │  billing webhooks · publish · public API     │
                         └───┬───────────┬───────────────┬──────────────┘
              enqueue job    │           │ read/write     │ verify plan/credits
                         ┌───▼────┐   ┌──▼──────────┐  ┌──▼───────────────┐
                         │ Queue   │   │  Postgres   │  │ Stripe (billing) │
                         │ (Redis) │   │  (state)    │  └──────────────────┘
                         └───┬────┘   └─────────────┘
                             │ trigger
                         ┌───▼─────────────────────────────────────────┐
                         │  Modal — GPU worker (the pipeline, container) │
                         │  pulls source ↓ , renders clips ↑ , updates   │
                         │  job/clip rows via API callback               │
                         └───┬───────────────────────────────┬──────────┘
                    download │                        upload  │
                         ┌───▼───────────────────────────────▼──────────┐
                         │  Object storage (S3 / Cloudflare R2)          │
                         │  sources/{job}.mp4 · clips/{clip}.mp4 · .ass  │
                         └───────────────────────────────────────────────┘

  External: YouTube / TikTok / Instagram publish APIs · Anthropic/DeepSeek (select) ·
            yt-dlp (ingest) · OAuth providers for connected social accounts
```

## Components

### 1. Next.js app (Vercel)
Single Next.js project serves **both** the marketing site and the authenticated app (route
groups: `(marketing)` and `(app)`). SSR/SSG for SEO on marketing pages; client-heavy for the
editor. Talks to the FastAPI API over REST. Auth handled by the chosen provider (see tech-stack).

### 2. API service — FastAPI (evolves `backend/main.py`)
Stays Python so we keep the engine and its deps in one language. New responsibilities:
- **Auth guard** — validate session/JWT on every request; resolve `user`/`org`.
- **Projects & jobs** — CRUD backed by Postgres (replaces `jobs.py`'s in-process dict).
- **Enqueue** — on `POST /api/process`, write a `job` row and push to the queue instead of
  spawning a thread.
- **Billing** — check credit balance before enqueue; handle Stripe webhooks.
- **Publish** — proxy to platform APIs using the user's connected-account tokens.
- **Public API** — same endpoints behind API-key auth + rate limiting.
Deployed as a container (Fly.io / Render / Cloud Run) — CPU-only; no GPU here.

### 3. Modal — GPU worker (wraps `backend/pipeline.py`)
The pipeline packaged as a Modal function with a GPU + ffmpeg + the Python deps. Per job it:
1. Downloads the source from object storage (or runs yt-dlp for URL ingest).
2. Runs the existing stages; **Whisper runs on GPU** (`WHISPER_DEVICE=cuda`).
3. Uploads rendered clips + `.ass` to object storage.
4. Calls back to the API to update `job`/`clip` rows (status, scores, storage keys).
Scales to zero when idle → we pay GPU only while rendering. This is the cost center; see pricing.

### 4. Postgres — state
Replaces the non-persisted job dict and the daemon's JSON files. Schema in
[04-data-model.md](./04-data-model.md). Managed host (Supabase / Neon / RDS).

### 5. Object storage — media
Sources and rendered clips. Signed URLs for browser upload (direct-to-storage) and playback.
Lifecycle rules expire sources after render and clips per the user's plan retention.

### 6. Queue — Redis (RQ/Celery) or Modal's own queue
Decouples request from render. Enables retries, concurrency limits per plan, and priority
(paid jobs ahead of free). If we lean fully on Modal, its built-in queue may remove the need
for a separate Redis initially — decided in Phase 1.

## Job lifecycle

```
queued → downloading → transcribing → selecting → reframing → captioning → verifying
       → (per clip) rendered | rejected(reason)  → done | failed
```
Each transition writes to the `jobs` table and streams to the UI (polling first, SSE/websocket
later). Mirrors the current pipeline stages so the engine barely changes — it just reports
progress to Postgres via API callbacks instead of updating a local `Job` object.

## What we reuse vs. build

| Existing (`backend/`) | Reuse as-is? | Change |
|---|---|---|
| `download.py` | ✅ | Read/write via object storage keys. |
| `transcribe.py` | ✅ | Force GPU in the Modal image; model cached warm. |
| `select.py` | ✅ | Per-org `style`/presets; keys from settings, not global `.env`. |
| `reframe.py` | ✅ | Output aspect ratios beyond 9:16. |
| `captions.py` | ✅ | Emit **editable** cue data (JSON) alongside burned `.ass`. |
| `verify.py` | ✅ | Same gate; report reason to `clips` row. |
| `pipeline.py` | ♻️ | Orchestrates the same stages, but stateless + storage-backed. |
| `daemon.py` | ♻️ | Becomes the **Autopilot** worker (per-account, DB-driven). |
| `jobs.py` | ❌ replace | Postgres models. |
| `main.py` | ♻️ | Grows auth, billing, publish, API-key routes. |
| `youtube.py` | ✅ + extend | One of several publish targets; per-user OAuth tokens. |
| `frontend/` (legacy) | ❌ retire | Replaced by the Next.js app. |
