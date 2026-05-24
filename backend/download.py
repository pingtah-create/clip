"""Fetch the input video. Accepts either a URL (yt-dlp) or a path to an already-uploaded file."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .tools import FFMPEG, YT_DLP_CMD


def is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def fetch(source: str, out_dir: Path) -> Path:
    """Returns the path to the local video file (mp4, h264/aac, suitable for downstream)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    if not is_url(source):
        # Uploaded file path
        src = Path(source)
        if not src.exists():
            raise FileNotFoundError(source)
        # Normalize to mp4 in our workspace so downstream is predictable
        dst = out_dir / "source.mp4"
        _normalize(src, dst)
        return dst

    # YouTube / other URL via yt-dlp
    template = str(out_dir / "source.%(ext)s")
    # Prefer mp4-compatible streams to avoid an extra remux
    cmd = [
        *YT_DLP_CMD,
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format", "mp4",
        "--ffmpeg-location", FFMPEG,
        "-o", template,
        "--no-playlist",
        "--no-progress",
        source,
    ]
    subprocess.run(cmd, check=True)

    # yt-dlp produced source.mp4 (or .mkv if it had to fall back)
    for ext in ("mp4", "mkv", "webm"):
        p = out_dir / f"source.{ext}"
        if p.exists():
            if ext != "mp4":
                dst = out_dir / "source.mp4"
                _normalize(p, dst)
                p.unlink(missing_ok=True)
                return dst
            return p

    raise RuntimeError("yt-dlp finished but no output file was found")


def _normalize(src: Path, dst: Path) -> None:
    """Transcode to h264+aac mp4. Slower but everything downstream assumes this."""
    cmd = [
        FFMPEG, "-y", "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(dst),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def extract_audio(video: Path, out: Path) -> Path:
    """16kHz mono wav — what faster-whisper wants. Much faster to load than re-decoding mp4."""
    cmd = [
        FFMPEG, "-y", "-i", str(video),
        "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(out),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out
