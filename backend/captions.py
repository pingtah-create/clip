"""Generate big, centered, word-by-word "karaoke-highlighted" captions in ASS format,
then burn them into a video with ffmpeg."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .tools import FFMPEG
from .transcribe import Segment, Word


# Punchy Shorts captions: few words on screen at once, BIG, with the active word
# highlighted. This is the Hormozi/viral-Shorts style (vs. dense movie-subtitle text)
# — 2 words per line × up to 2 lines = max 4 words visible, so each word is large and
# the eye isn't split across a paragraph. Cues hold still; only the active word animates.
WORDS_PER_LINE = 2
MAX_WORDS_PER_CUE = 4
# A pause longer than this starts a fresh cue, so old text doesn't linger.
MAX_GAP_WITHIN_CUE = 1.0

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
Style: Default,Arial Black,88,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,7,3,2,60,60,360,1
Style: Hook,Arial Black,64,&H0000FFFF,&H000000FF,&H00000000,&HA0000000,1,0,0,0,100,100,0,0,1,6,3,8,80,80,340,1

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
    # Group words into stable cues (a fixed block of text that holds still on screen).
    # Within a cue we emit one event per active word, but the BLOCK never fades or
    # redraws — only the highlighted word changes color/scale. The static surrounding
    # text stays rock-steady, which is what reads as "smooth" vs. the old per-word
    # fade that flickered the whole block every word.
    cues = _group_words(words)
    for cue in cues:
        cue_start = cue[0].start - clip_start
        cue_end = cue[-1].end - clip_start + 0.3
        for ai, active in enumerate(cue):
            color = _emphasis_color(active.text)
            parts = []
            for wi, w in enumerate(cue):
                t = _escape_ass(w.text)
                if wi == ai:
                    # Active word: colored, bold, gentle 100→110% scale over 200ms —
                    # a smooth settle rather than a snap, so consecutive active words
                    # ease into emphasis instead of popping abruptly.
                    parts.append(r"{\c" + color + r"\b1\fscx100\fscy100"
                                 r"\t(0,200,\fscx110\fscy110)}" + t +
                                 r"{\c&HFFFFFF&\b0\fscx100\fscy100}")
                else:
                    # Already-spoken or upcoming: plain white, full opacity, steady.
                    parts.append(t)
            # Line-break every WORDS_PER_LINE so the cue is a tidy stacked block.
            chunks = []
            for k, p in enumerate(parts):
                chunks.append(p)
                if (k + 1) < len(parts):
                    chunks.append(r"\N" if (k + 1) % WORDS_PER_LINE == 0 else " ")
            text = "".join(chunks)

            seg_start = max(cue_start, active.start - clip_start - 0.02)
            seg_end = (cue[ai + 1].start - clip_start) if ai + 1 < len(cue) else cue_end
            if seg_end <= seg_start:
                continue
            # Smooth transitions at the seams only:
            #  - first word of a cue fades IN (180ms) so the block eases onto screen
            #  - last word's event is extended ~180ms past the cue so it overlaps the
            #    next cue's fade-in (crossfade) instead of a hard cut to blank, and
            #    fades OUT over 180ms.
            #  - mid-cue words: no fade — the block holds rock-steady while the
            #    highlight slides, which is what reads as smooth.
            if ai == 0 and len(cue) > 1:
                fade = r"{\fad(180,0)}"
                seg_end_padded = seg_end
            elif ai == len(cue) - 1:
                fade = r"{\fad(0,180)}"
                seg_end_padded = seg_end + 0.18   # overlap into the next cue for a crossfade
            else:
                fade = ""
                seg_end_padded = seg_end
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
