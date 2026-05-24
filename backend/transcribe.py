"""faster-whisper transcription with word-level timestamps.

The model is loaded lazily and kept in a module-level cache so subsequent jobs reuse it
instead of paying the load cost again."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word]


_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        size = os.environ.get("WHISPER_MODEL", "small")
        # Default to CPU + int8: works on any Windows machine without CUDA installed.
        # For NVIDIA users: set WHISPER_DEVICE=cuda and WHISPER_COMPUTE=float16 in .env.
        # "auto" is avoided because it half-detects GPUs and then crashes when CUDA libs are missing.
        device = os.environ.get("WHISPER_DEVICE", "cpu")
        compute = os.environ.get("WHISPER_COMPUTE", "int8")
        _model = WhisperModel(size, device=device, compute_type=compute)
    return _model


def transcribe(audio: Path, progress=None) -> list[Segment]:
    """Returns segments with word-level timing. `progress` is called as (done_seconds, total_seconds)."""
    model = _get_model()
    segments_iter, info = model.transcribe(
        str(audio),
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    total = info.duration or 0.0

    out: list[Segment] = []
    for seg in segments_iter:
        words = [
            Word(start=w.start, end=w.end, text=w.word)
            for w in (seg.words or [])
            if w.start is not None and w.end is not None
        ]
        out.append(Segment(start=seg.start, end=seg.end, text=seg.text.strip(), words=words))
        if progress and total:
            progress(min(seg.end, total), total)

    return out


def segments_to_compact_transcript(segments: list[Segment]) -> str:
    """Build a transcript with [HH:MM:SS] timestamps for Claude. Compact, no per-word noise."""
    lines = []
    for s in segments:
        ts = _fmt(s.start)
        lines.append(f"[{ts}] {s.text}")
    return "\n".join(lines)


def _fmt(t: float) -> str:
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"
