"""Generate big, centered, word-by-word "karaoke-highlighted" captions in ASS format,
then burn them into a video with ffmpeg."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .tools import FFMPEG
from .transcribe import Segment, Word


# Sliding-window captions: the active word is always rendered on the middle line,
# with N words of context above (already-spoken, dimmed) and N words below (upcoming,
# dimmed). The frame position never changes — only the highlighted word slides through
# the window. This is what makes TikTok-style captions feel stable instead of jumping.
WORDS_BEFORE = 4   # past words shown above the active word
WORDS_AFTER = 4    # upcoming words shown below the active word

# ASS colors are &HBBGGRR& (BGR, not RGB). Each entry: (primary, label).
_COLOR_DEFAULT = r"&H00F0FF&"   # yellow — the standard active-word pop
_COLOR_MONEY = r"&H00FF66&"     # green — numbers, dollars, percentages
_COLOR_SHOCK = r"&H3030FF&"     # red — emotional / negation / superlatives

# Regex-classified emphasis. Cheap, no LLM call. Tuned for finance/investor content
# per style.md (numbers and shock words land hardest on this audience).
_MONEY_RE = re.compile(r"^\$?\d[\d,.]*[%kmbKMB]?\$?$|^\$\d", re.UNICODE)
_SHOCK_WORDS = {
    "never", "always", "destroyed", "lost", "crushed", "killed", "doubled",
    "tripled", "exploded", "crashed", "wrong", "wrong.", "stupid", "insane",
    "ridiculous", "huge", "massive", "biggest", "worst", "best", "every",
    "nothing", "everything", "nobody", "everyone",
}


def _emphasis_color(text: str) -> str:
    """Pick the active-word color based on the word itself. Falls back to yellow."""
    t = text.strip().lower().strip(",.!?;:\"'")
    if _MONEY_RE.match(t):
        return _COLOR_MONEY
    if t in _SHOCK_WORDS:
        return _COLOR_SHOCK
    return _COLOR_DEFAULT


def words_in_range(segments: list[Segment], start: float, end: float) -> list[Word]:
    out = []
    for s in segments:
        for w in s.words:
            if w.end <= start or w.start >= end:
                continue
            out.append(Word(start=max(w.start, start), end=min(w.end, end), text=w.text.strip()))
    return out


HOOK_DURATION = 2.2   # seconds the hook overlay stays on screen — long enough to read
HOOK_FADE_MS = 200    # fade in/out for the hook


def write_ass(
    words: list[Word],
    clip_start: float,
    ass_path: Path,
    hook: str | None = None,
    video_w: int = 1080,
    video_h: int = 1920,
) -> Path:
    """Each cue contains up to MAX_WORDS_PER_CUE words; the current word is highlighted yellow.
    If `hook` is given, render it as a big top-of-frame overlay for the first ~1.6s."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,56,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,2,80,80,320,1
Style: Hook,Arial Black,96,&H0000FFFF,&H000000FF,&H00000000,&HA0000000,1,0,0,0,100,100,0,0,1,8,3,8,60,60,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header]
    if hook:
        lines.append(_hook_dialogue(hook))

    # Sliding window: one Dialogue event per spoken word. The window holds the active
    # word plus WORDS_BEFORE past words (line 1, dimmed) and WORDS_AFTER upcoming words
    # (line 3, dimmed). Active word is line 2, fully bright + colored + scaled.
    # The 3-line block stays anchored to the same screen position the whole clip.
    n = len(words)
    for idx, active in enumerate(words):
        before = words[max(0, idx - WORDS_BEFORE): idx]
        after = words[idx + 1: idx + 1 + WORDS_AFTER]

        before_text = " ".join(_escape_ass(w.text) for w in before)
        after_text = " ".join(_escape_ass(w.text) for w in after)
        color = _emphasis_color(active.text)
        # Active word: yellow/green/red + bold + soft bounce 95→115% scale. 280ms
        # ramp reads as a slow "settle" rather than a snap — the longer ramp lets
        # consecutive active words crossfade visually instead of pinging in/out.
        active_tag = (
            r"{\c" + color + r"\b1\fscx95\fscy95"
            r"\t(0,280,\fscx115\fscy115)}"
        )
        active_text = active_tag + _escape_ass(active.text)

        # Past words: white but 60% alpha (dimmed). Upcoming: same dim treatment.
        # \alpha&H66& = ~40% transparent. Reset to opaque on the active line.
        dim_open = r"{\alpha&H66&\b0\fscx100\fscy100}"
        active_open = r"{\alpha&H00&}"
        parts = []
        if before_text:
            parts.append(dim_open + before_text)
        parts.append(active_open + active_text)
        if after_text:
            parts.append(dim_open + after_text)
        text = r"\N".join(parts)

        seg_start = max(0.0, active.start - clip_start - 0.02)
        if idx + 1 < n:
            seg_end = words[idx + 1].start - clip_start
        else:
            seg_end = active.end - clip_start + 0.2
        if seg_end <= seg_start:
            continue
        # Longer per-event fade (140ms in/out) + 140ms overlap with neighbors gives
        # a true crossfade between consecutive words — each fade-out runs while the
        # next word's fade-in is already underway, so the caption block visually
        # flows instead of ticking.
        seg_end_padded = seg_end + 0.14
        fade = r"{\fad(140,140)}"
        lines.append(
            f"Dialogue: 0,{_ts(seg_start)},{_ts(seg_end_padded)},Default,,0,0,0,,{fade}{text}\n"
        )

    ass_path.write_text("".join(lines), encoding="utf-8")
    return ass_path


def burn(video: Path, ass: Path, out: Path) -> Path:
    """Burn the ASS file into video. Escapes the Windows path for ffmpeg's libass filter."""
    # libass on Windows needs single-quoted path with backslashes escaped and ':' escaped
    ass_esc = str(ass).replace("\\", "/").replace(":", r"\:")
    cmd = [
        FFMPEG, "-y", "-i", str(video),
        "-vf", f"ass='{ass_esc}'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


def _hook_dialogue(hook: str) -> str:
    """A single ASS event in the Hook style: top of frame, big yellow, with a punchy
    scale-in pop + fade so it slams onto screen in the first frame instead of drifting."""
    text = _escape_ass(hook.strip().upper())
    # Wrap long hooks onto 2 lines at the nearest space past the midpoint
    if len(text) > 28:
        mid = len(text) // 2
        space = text.find(" ", mid)
        if space != -1:
            text = text[:space] + r"\N" + text[space + 1:]
    fade = rf"{{\fad({HOOK_FADE_MS},{HOOK_FADE_MS})}}"
    # Scale-in pop: start at 70% and overshoot to 100% over 220ms. The overshoot read
    # ("bigger then settle") is what makes the eye snap to it — pure fade is too passive.
    pop = r"{\fscx70\fscy70\t(0,220,\fscx100\fscy100)}"
    return f"Dialogue: 1,{_ts(0)},{_ts(HOOK_DURATION)},Hook,,0,0,0,,{fade}{pop}{text}\n"


def _group_words(words: list[Word]) -> list[list[Word]]:
    cues: list[list[Word]] = []
    current: list[Word] = []
    for w in words:
        if not current:
            current.append(w); continue
        gap = w.start - current[-1].end
        if len(current) >= MAX_WORDS_PER_CUE or gap > MAX_GAP_WITHIN_CUE:
            cues.append(current)
            current = [w]
        else:
            current.append(w)
    if current:
        cues.append(current)
    return cues


def _ts(t: float) -> str:
    if t < 0:
        t = 0
    h = int(t // 3600); m = int((t % 3600) // 60); s = t - h * 3600 - m * 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _escape_ass(s: str) -> str:
    return s.replace("{", r"\{").replace("}", r"\}")
