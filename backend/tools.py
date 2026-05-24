"""Resolve external tool paths once, at import time.

The server process inherits its PATH from however uvicorn was launched, which on Windows
often misses the venv's Scripts dir AND any PATH entries added by winget after the parent
shell started. Resolving here avoids 'FileNotFoundError [WinError 2]' surprises later."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def _find_ffmpeg() -> str:
    # 1. Already on PATH — works on any OS, any user.
    p = shutil.which("ffmpeg")
    if p:
        return p
    # 2. Common winget install location — resolves under whichever user is signed in,
    # so it works on a friend's machine without hardcoding "Ping".
    import os
    user_packages = Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"))
    if user_packages.exists():
        candidates = list(user_packages.glob("Gyan.FFmpeg_*/ffmpeg-*-full_build/bin/ffmpeg.exe"))
        if candidates:
            return str(candidates[0])
    # 3. Last resort — let subprocess fail with a clearer error.
    return "ffmpeg"


FFMPEG: str = _find_ffmpeg()

# yt-dlp is a pip package — call via the current interpreter so PATH doesn't matter.
YT_DLP_CMD: list[str] = [sys.executable, "-m", "yt_dlp"]
