"""FastAPI app: serves the single-page frontend and the job API."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import jobs, pipeline


def _hard_exit(signum, frame):
    """Ctrl+C → kill every ffmpeg/python child immediately, then exit. Uvicorn alone
    would wait for daemon pipeline threads to finish, which blocks on stuck ffmpeg
    calls indefinitely. This bypasses the polite shutdown."""
    try:
        # taskkill is the only reliable Windows way to terminate a tree of orphan
        # ffmpeg processes spawned by subprocess.Popen. /F = force, /T = include children.
        subprocess.run(["taskkill", "/F", "/IM", "ffmpeg.exe"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    # os._exit skips the daemon-thread join that hangs us. Sys.exit would still wait.
    os._exit(0)


signal.signal(signal.SIGINT, _hard_exit)
signal.signal(signal.SIGTERM, _hard_exit)

# override=True so .env always wins over pre-existing shell env vars (e.g. an
# ANTHROPIC_BASE_URL inherited from Claude Code that would otherwise pin us to Anthropic).
load_dotenv(override=True)

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
UPLOADS = ROOT / "data" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Clip")


@app.get("/", response_class=HTMLResponse)
def index():
    return (FRONTEND / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {"ok": True, "has_anthropic_key": has_key}


@app.post("/api/process")
async def process(
    url: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    n_clips: int = Form(default=5),
    duration_preset: str = Form(default="standard"),
):
    if not url and not file:
        raise HTTPException(400, "Provide either url or file")
    if n_clips < 1 or n_clips > 10:
        raise HTTPException(400, "n_clips must be 1..10")
    if duration_preset not in ("short", "standard", "long"):
        raise HTTPException(400, "duration_preset must be short, standard, or long")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(400, "ANTHROPIC_API_KEY is not set. Edit .env and restart.")

    if file:
        # Save upload to disk before kicking the job off
        ext = Path(file.filename or "video.mp4").suffix or ".mp4"
        path = UPLOADS / f"{uuid.uuid4().hex}{ext}"
        with path.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
        source = str(path)
        label = file.filename or path.name
    else:
        source = url
        label = url

    job = jobs.create(label, n_clips, duration_preset)

    t = threading.Thread(target=pipeline.run, args=(job.id,), daemon=True)
    t.start()

    return {"id": job.id}


@app.get("/api/jobs")
def list_jobs():
    return [j.to_dict() for j in jobs.list_all()]


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    j = jobs.get(jid)
    if not j:
        raise HTTPException(404, "Not found")
    return j.to_dict()


@app.get("/api/clips/{clip_id}")
def download_clip(clip_id: str):
    # clip_id is "{job_id}-{nn}"; find it on disk
    job_id = clip_id.rsplit("-", 1)[0]
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    for c in job.clips:
        if c.id == clip_id and c.file and Path(c.file).exists():
            safe = c.title.replace("/", "_").replace("\\", "_")[:50] or clip_id
            return FileResponse(c.file, filename=f"{safe}.mp4", media_type="video/mp4")
    raise HTTPException(404, "Clip not ready or not found")


@app.get("/api/clips/{clip_id}/preview")
def preview_clip(clip_id: str):
    """Same as download but inline so the <video> tag can stream it."""
    job_id = clip_id.rsplit("-", 1)[0]
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404)
    for c in job.clips:
        if c.id == clip_id and c.file and Path(c.file).exists():
            return FileResponse(c.file, media_type="video/mp4")
    raise HTTPException(404)


@app.post("/api/jobs/{jid}/upload-all")
def upload_all_clips(jid: str):
    """Sequentially upload every renderable clip in the job. Returns counts —
    the per-clip status is on each Clip dataclass and visible in the next poll()."""
    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")

    from .youtube import upload as yt_upload
    privacy = os.environ.get("YOUTUBE_PRIVACY", "private").lower()
    tags = [t.strip() for t in os.environ.get("YOUTUBE_DEFAULT_TAGS", "shorts").split(",") if t.strip()]

    def run_bulk():
        for clip in job.clips:
            # Skip clips that already uploaded successfully. Retry the rest (including
            # 'failed' and 'skipped'), since the user pressed the button knowing this.
            if clip.youtube_status == "uploaded" and clip.youtube_id:
                continue
            if not clip.file or not Path(clip.file).exists():
                continue
            clip.youtube_status = "uploading"
            jobs.update(jid, clips=job.clips)
            try:
                description = f"{clip.hook}\n\nFrom a longer interview." if clip.hook else ""
                vid = yt_upload(Path(clip.file), title=clip.title, description=description,
                                tags=tags, privacy=privacy)
                clip.youtube_id = vid
                clip.youtube_status = "uploaded"
            except Exception as e:
                clip.youtube_status = "failed"
                clip.error = (clip.error or "") + f" | youtube: {type(e).__name__}: {e}"
            jobs.update(jid, clips=job.clips)

    # Run bulk uploads in a background thread so the HTTP response returns fast and
    # the UI can poll for per-clip progress as each one finishes (~10s each).
    threading.Thread(target=run_bulk, daemon=True).start()
    eligible = sum(1 for c in job.clips if c.file and c.youtube_status != "uploaded")
    return {"queued": eligible}


@app.post("/api/clips/{clip_id}/upload")
def upload_clip(clip_id: str):
    """User-triggered YouTube upload for one clip. Runs synchronously — uploads are
    fast (~10s for a 30s short on a decent connection) so blocking is fine."""
    job_id = clip_id.rsplit("-", 1)[0]
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    clip = next((c for c in job.clips if c.id == clip_id), None)
    if not clip or not clip.file or not Path(clip.file).exists():
        raise HTTPException(404, "Clip not ready")
    if clip.youtube_status == "uploaded" and clip.youtube_id:
        return {"youtube_id": clip.youtube_id, "youtube_status": "uploaded"}

    # Lazy-import so missing google deps don't break the server boot.
    from .youtube import upload as yt_upload

    clip.youtube_status = "uploading"
    jobs.update(job_id, clips=job.clips)
    try:
        privacy = os.environ.get("YOUTUBE_PRIVACY", "private").lower()
        tags = [t.strip() for t in os.environ.get("YOUTUBE_DEFAULT_TAGS", "shorts").split(",") if t.strip()]
        description = f"{clip.hook}\n\nFrom a longer interview." if clip.hook else ""
        vid = yt_upload(
            Path(clip.file),
            title=clip.title,
            description=description,
            tags=tags,
            privacy=privacy,
        )
        clip.youtube_id = vid
        clip.youtube_status = "uploaded"
        jobs.update(job_id, clips=job.clips)
        return {"youtube_id": vid, "youtube_status": "uploaded"}
    except Exception as e:
        clip.youtube_status = "failed"
        clip.error = (clip.error or "") + f" | youtube: {type(e).__name__}: {e}"
        jobs.update(job_id, clips=job.clips)
        raise HTTPException(500, f"Upload failed: {e}")
