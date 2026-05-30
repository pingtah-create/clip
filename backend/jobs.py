"""In-memory job store. Persistence isn't worth the complexity for a personal tool —
if the process dies mid-job, just re-run. Each job's outputs live on disk under data/jobs/<id>/."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Clip:
    id: str
    title: str
    hook: str
    score: int
    start: float
    end: float
    duration: float
    file: str | None = None   # absolute path to final mp4
    status: str = "pending"   # pending | rendering | done | failed
    error: str | None = None
    youtube_id: str | None = None        # set after a successful upload
    youtube_status: str = "skipped"      # skipped | uploading | uploaded | failed
    face_coverage: float = 1.0           # fraction of the clip with a visible speaker


@dataclass
class Job:
    id: str
    source: str               # URL or original filename
    n_clips: int
    duration_preset: str = "standard"   # short | standard | long — see select.DURATION_PRESETS
    created_at: float = field(default_factory=time.time)
    status: str = "queued"    # queued | downloading | transcribing | selecting | rendering | done | failed
    progress: float = 0.0     # 0..1
    message: str = ""
    error: str | None = None
    clips: list[Clip] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def create(source: str, n_clips: int, duration_preset: str = "standard") -> Job:
    jid = uuid.uuid4().hex[:12]
    job = Job(id=jid, source=source, n_clips=n_clips, duration_preset=duration_preset)
    with _lock:
        _jobs[jid] = job
    return job


def get(jid: str) -> Job | None:
    with _lock:
        return _jobs.get(jid)


def update(jid: str, **fields) -> None:
    with _lock:
        j = _jobs.get(jid)
        if not j:
            return
        for k, v in fields.items():
            setattr(j, k, v)


def list_all() -> list[Job]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
