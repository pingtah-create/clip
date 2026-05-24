"""Orchestrates one job from input to finished vertical clips with captions."""

from __future__ import annotations

import os
import shutil
import traceback
from pathlib import Path

from . import jobs
from .captions import burn, write_ass, words_in_range
from .download import extract_audio, fetch
from .reframe import reframe
from .select import pick_clips
from .transcribe import segments_to_compact_transcript, transcribe

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"


def run(job_id: str) -> None:
    job = jobs.get(job_id)
    if not job:
        return

    work = DATA_ROOT / "jobs" / job_id
    clips_dir = DATA_ROOT / "clips" / job_id
    work.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Download / normalize
        jobs.update(job_id, status="downloading", progress=0.02, message="Fetching video")
        video = fetch(job.source, work)

        # 2. Audio
        jobs.update(job_id, status="transcribing", progress=0.10, message="Extracting audio")
        audio = extract_audio(video, work / "audio.wav")

        # 3. Transcribe (longest step — give it the biggest chunk of the progress bar)
        def whisper_progress(done, total):
            frac = 0.10 + 0.55 * (done / total if total else 0)
            jobs.update(job_id, progress=frac, message=f"Transcribing {int(done)}/{int(total)}s")

        segments = transcribe(audio, progress=whisper_progress)
        if not segments:
            raise RuntimeError("Transcription returned nothing")

        transcript = segments_to_compact_transcript(segments)
        (work / "transcript.txt").write_text(transcript, encoding="utf-8")

        # 4. Ask Claude for clips
        jobs.update(job_id, status="selecting", progress=0.68, message="Asking Claude for the best moments")
        picks = pick_clips(transcript, segments, job.n_clips, job.duration_preset)
        if not picks:
            raise RuntimeError("Claude returned no clips")

        job.clips = [
            jobs.Clip(
                id=f"{job_id}-{i:02d}",
                title=p.title, hook=p.hook, score=p.score,
                start=p.start, end=p.end, duration=p.end - p.start,
            )
            for i, p in enumerate(picks)
        ]
        jobs.update(job_id, clips=job.clips)

        # 5. Render each clip (reframe + captions)
        per = 0.30 / max(len(picks), 1)
        for i, (pick, meta) in enumerate(zip(picks, job.clips)):
            meta.status = "rendering"
            jobs.update(job_id, status="rendering", message=f"Rendering clip {i+1}/{len(picks)}: {meta.title}")
            try:
                clip_dir = work / f"clip_{i:02d}"
                clip_dir.mkdir(exist_ok=True)

                vertical = clip_dir / "vertical.mp4"
                reframe(video, pick.start, pick.end, vertical)

                ass = write_ass(
                    words_in_range(segments, pick.start, pick.end),
                    clip_start=pick.start,
                    ass_path=clip_dir / "subs.ass",
                    hook=pick.hook,
                )

                final = clips_dir / f"{meta.id}.mp4"
                burn(vertical, ass, final)

                meta.file = str(final)
                meta.status = "done"

                # Auto-upload to YouTube if enabled AND this clip beat the score threshold.
                # Runs inline so a failure surfaces on the same Clip's youtube_status; the
                # outer try/except still catches it and the clip itself stays "done".
                if _should_upload(meta):
                    _try_upload(meta, job_id, job.clips)
            except Exception as e:
                meta.status = "failed"
                meta.error = str(e)
            finally:
                jobs.update(job_id, progress=min(0.98, 0.68 + per * (i + 1)), clips=job.clips)

        ok = sum(1 for c in job.clips if c.status == "done")
        jobs.update(
            job_id,
            status="done" if ok else "failed",
            progress=1.0,
            message=f"Finished — {ok}/{len(job.clips)} clips ready",
        )

    except Exception as e:
        jobs.update(
            job_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            message=traceback.format_exc().splitlines()[-1],
        )


def _should_upload(clip: jobs.Clip) -> bool:
    if os.environ.get("YOUTUBE_AUTO_UPLOAD", "false").lower() != "true":
        return False
    try:
        threshold = int(os.environ.get("YOUTUBE_MIN_SCORE", "85"))
    except ValueError:
        threshold = 85
    return clip.score >= threshold


def _try_upload(clip: jobs.Clip, job_id: str, all_clips: list[jobs.Clip]) -> None:
    """Push one rendered clip to YouTube. Failure is non-fatal — clip stays 'done',
    only youtube_status flips to 'failed'."""
    # Imported lazily so a missing google library doesn't break runs without auto-upload.
    from .youtube import upload

    clip.youtube_status = "uploading"
    jobs.update(job_id, clips=all_clips, message=f"Uploading to YouTube: {clip.title}")
    try:
        privacy = os.environ.get("YOUTUBE_PRIVACY", "private").lower()
        tags = [t.strip() for t in os.environ.get("YOUTUBE_DEFAULT_TAGS", "shorts").split(",") if t.strip()]
        description = f"{clip.hook}\n\nFrom a longer interview." if clip.hook else ""
        vid = upload(
            Path(clip.file),
            title=clip.title,
            description=description,
            tags=tags,
            privacy=privacy,
        )
        clip.youtube_id = vid
        clip.youtube_status = "uploaded"
    except Exception as e:
        clip.youtube_status = "failed"
        clip.error = (clip.error or "") + f" | youtube: {type(e).__name__}: {e}"
