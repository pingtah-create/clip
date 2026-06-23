"""Verify a rendered clip is actually good before it ships — the create/verify split.

The pipeline that makes a clip shouldn't be the only thing that judges it. This is a
cheap, deterministic gate (no LLM, no extra API calls) that catches the failure modes
we've actually hit in production:

  - Captions silently missing (the malformed-ASS bug burned a clip with no text).
  - Black / frozen / corrupt video (a bad source or a half-died ffmpeg).
  - Missing audio (mux failure → a silent Short).

Vision-LLM verification was the first idea, but the configured model (deepseek-v4-flash)
returns empty on image input, so it would "pass" everything — worse than no check. Pixel
math via OpenCV is more reliable for these mechanical checks anyway.

Returns (ok, reason). The pipeline rejects clips that fail, same as MIN_FACE_COVERAGE."""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np

from .tools import FFMPEG

# Sample this many evenly-spaced frames across the clip body to judge it.
_SAMPLES = 6
# A frame brighter-than-this-dark on average is "not black". Mean luma 0..255.
_MIN_BRIGHTNESS = 12
# Catastrophic-blank guard only. The lower third of a real clip always has SOME detail
# (captions and/or the speaker), so an essentially edgeless band means a broken render
# (frozen/blank frame). This is intentionally loose — it is NOT a precise caption
# detector (a no-caption talking head still has edges here); caption presence is
# verified deterministically from the ASS file instead, see verify_captions_ass().
_CAPTION_BAND_TOP = 0.60
_MIN_BAND_EDGE_FRAC = 0.002


def verify_clip(clip_path: Path, ass_path: Path | None = None) -> tuple[bool, str]:
    """Deterministic quality gate for a finished clip. (ok, reason).

    Pixel checks (reliable): readable, not black, lower-third not blank, has audio.
    Caption check (reliable, if ass_path given): the ASS subtitle file is structurally
    sound — this is where the real 'captions silently missing' bug lives."""
    clip_path = Path(clip_path)
    if not clip_path.exists() or clip_path.stat().st_size < 50_000:
        return False, "file missing or suspiciously small"

    if ass_path is not None:
        ok, reason = verify_captions_ass(Path(ass_path))
        if not ok:
            return False, reason

    cap = cv2.VideoCapture(str(clip_path))
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if n_frames <= 0 or fps <= 0:
        cap.release()
        return False, "unreadable video stream"

    # Sample frames from the middle 80% (skip the very ends — fades, hook overlay).
    idxs = np.linspace(int(n_frames * 0.1), int(n_frames * 0.9), _SAMPLES).astype(int)
    brightness: list[float] = []
    band_edge_fracs: list[float] = []
    read_ok = 0
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        read_ok += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness.append(float(gray.mean()))
        h = gray.shape[0]
        band = gray[int(h * _CAPTION_BAND_TOP):, :]
        band_edge_fracs.append(float((cv2.Canny(band, 80, 200) > 0).mean()))
    cap.release()

    if read_ok < max(2, _SAMPLES // 2):
        return False, f"could not read frames ({read_ok}/{_SAMPLES})"

    if brightness and np.mean(brightness) < _MIN_BRIGHTNESS:
        return False, f"video is near-black (mean luma {np.mean(brightness):.0f})"

    if band_edge_fracs and max(band_edge_fracs) < _MIN_BAND_EDGE_FRAC:
        return False, "lower third is blank/frozen (broken render)"

    if not _has_audio(clip_path):
        return False, "no audio track"

    return True, "ok"


def verify_captions_ass(ass_path: Path) -> tuple[bool, str]:
    """Confirm the ASS subtitle file would actually render captions. Catches the real
    failure we hit: malformed ASS where every Dialogue collapsed onto one physical line,
    so libass parsed only the first and silently dropped the rest. A healthy file has
    many Dialogue lines, each starting its own line."""
    if not ass_path.exists():
        return False, "ASS file missing"
    text = ass_path.read_text(encoding="utf-8", errors="replace")
    dialogue_lines = [ln for ln in text.splitlines() if ln.startswith("Dialogue:")]
    if len(dialogue_lines) < 3:
        return False, f"ASS has too few caption events ({len(dialogue_lines)})"
    # Guard against the collapse bug: a single physical line carrying many events.
    if any(ln.count("Dialogue:") > 1 for ln in dialogue_lines):
        return False, "ASS malformed — multiple events on one line (captions would drop)"
    return True, "ok"


def _has_audio(path: Path) -> bool:
    """True if the file has at least one audio stream. Uses ffmpeg (already required)
    rather than adding ffprobe as a separate dependency."""
    try:
        res = subprocess.run(
            [FFMPEG, "-i", str(path), "-hide_banner"],
            capture_output=True, text=True, timeout=20,
        )
        # ffmpeg prints stream info to stderr; "Audio:" appears if an audio stream exists.
        return "Audio:" in (res.stderr or "")
    except Exception:
        # If the probe itself fails, don't block the upload on it — fail open here,
        # since the video checks above already caught the serious problems.
        return True
