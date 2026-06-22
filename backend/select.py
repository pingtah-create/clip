"""Ask Claude to pick the N most viral-worthy moments from a transcript.

Outputs a list of {start, end, title, hook, score} dicts. Times are seconds (float).
We snap the model's chosen boundaries to word boundaries from the transcript so the
clip never starts mid-syllable."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from anthropic import Anthropic

from .transcribe import Segment

STYLE_FILE = Path(__file__).resolve().parent.parent / "style.md"
TOP_PERFORMERS_FILE = Path(__file__).resolve().parent.parent / "data" / "top_performers.json"
TOP_PERFORMERS_FILE = Path(__file__).resolve().parent.parent / "data" / "top_performers.json"


@dataclass
class ClipPick:
    start: float
    end: float
    title: str
    hook: str
    score: int
    hook_strength: int = 0


# Clips whose opening line scores below this are dropped — a weak first second tanks
# Shorts retention no matter how good the rest is. Tunable via MIN_HOOK_STRENGTH env.
MIN_HOOK_STRENGTH = int(os.environ.get("MIN_HOOK_STRENGTH", "55"))


# User-facing duration presets. Each maps to a (min, max) seconds range that's
# stuffed into Claude's prompt AND used to discard out-of-range clips post-hoc.
DURATION_PRESETS: dict[str, tuple[int, int]] = {
    "short": (15, 30),     # TikTok sweet spot — fastest scroll-stoppers
    "standard": (30, 60),  # YouTube Shorts max, Reels comfort zone
    "long": (60, 90),      # Reels + Shorts long-format, more developed ideas
}


BASE_SYSTEM = """You are a viral-clip producer for TikTok/Reels/Shorts. Your ONE job is to find \
moments that stop a thumb mid-scroll in the first second. On Shorts, ~70% of viewers leave \
in the first 2 seconds — the opening line is everything. Be ruthless about it.

THE HOOK TEST (a clip's first spoken line must pass at least one):
- Bold/contrarian claim: "I haven't bought a stock in twenty years."
- Surprising number or stakes: "I lost $40 million in a single afternoon."
- A pattern interrupt or curiosity gap: "Everyone gets this exact thing wrong."
- A direct, provocative question: "Why do smart people stay poor?"

The first line must NOT be: a greeting, throat-clearing ("So...", "Well...", "You know..."),
context-setting, a question being asked TO the speaker, or a slow wind-up. If the strong line
comes 8 seconds in, START THERE — cut everything before it.

A great clip also:
- Delivers ONE complete idea — states it, supports it, lands it. Never trails off.
- Is self-contained — no "as I said earlier", no unresolved pronouns.
- Ends on a punchline or payoff, not mid-thought.

ENGAGEMENT BIAS: Shorts get promoted by likes and COMMENTS, not just views. Strongly
prefer moments that make a viewer want to react — a hot take, a claim people will argue
with, a "most people are wrong about X", a surprising or divisive opinion, a number that
sounds unbelievable. A clip people DISAGREE with or feel compelled to debate beats a
clip of pleasant, agreeable wisdom. When choosing between two clips, pick the one that
would get more comments. Avoid clips that are merely informative-but-forgettable.

PROVEN WINNER PATTERN (from real view data): our single best clip combined a SPECIFIC
NUMBER with a BOLD FUTURE PREDICTION ("one nuclear stat shows how far behind we are",
"75% cost drop no one sees coming"). Forward-looking claims with a concrete, surprising
stat about where things are HEADED outperform retrospective wisdom about the past.
Prioritize: future predictions, surprising statistics, "X% by year Y" claims, "nobody
sees this coming" framing. These clip far better than backward-looking life lessons.

You return strict JSON only. No prose, no markdown fences."""


def _system_prompt() -> str:
    """Load BASE_SYSTEM + the user's style.md + a performance-feedback block built
    from past clips' real view counts. The feedback teaches the picker which hooks
    actually earn views on THIS channel, so it gets better over time."""
    prompt = BASE_SYSTEM
    if STYLE_FILE.exists():
        style = STYLE_FILE.read_text(encoding="utf-8").strip()
        if style:
            prompt += "\n\n--- Channel-specific style ---\n\n" + style

    feedback = _top_performers_block()
    if feedback:
        prompt += feedback
    return prompt


def _top_performers_block() -> str:
    """Build a prompt fragment from data/top_performers.json (written by the daemon's
    feedback loop). Empty string if the file is missing or empty — so manual web-UI
    runs without daemon history behave exactly as before."""
    if not TOP_PERFORMERS_FILE.exists():
        return ""
    try:
        top = json.loads(TOP_PERFORMERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not top:
        return ""
    lines = [f'- "{t["title"]}" ({t.get("views", 0)} views) — hook: {t.get("hook", "")}'
             for t in top[:8]]
    return (
        "\n\n--- What actually performed on this channel (highest-viewed past clips) ---\n"
        "Bias your picks and hooks toward what these had in common — the topics, "
        "phrasing, and hook styles that earned the most views:\n\n" + "\n".join(lines)
    )


USER_TEMPLATE = """Below is a transcript with [HH:MM:SS.mmm] timestamps. Pick the {n} \
strongest clips by the criteria in your instructions. Return JSON in exactly this shape:

{{
  "clips": [
    {{
      "start": "HH:MM:SS.mmm",
      "end": "HH:MM:SS.mmm",
      "title": "Short scroll-stopping title (max 60 chars)",
      "hook": "The actual opening line of the clip, paraphrased (max 70 chars)",
      "hook_strength": 1-100,
      "score": 1-100
    }}
  ]
}}

Sort by score descending. Rules:
- Each clip MUST be {dur_min}-{dur_max} seconds. Aim for the middle of this range.
- start/end MUST be timestamps that appear in the transcript below.
- Do not overlap clips.
- Prefer variety of topics over near-duplicates.
- HOOK RULE: the first sentence at `start` must itself be the hook — a bold claim,
  surprising fact, or question. NEVER start on lead-in ("So...", "Yeah, well...",
  "The thing is...", "I mean...") or on a question being asked to the speaker. If
  the speaker's strong line is preceded by such filler, set `start` to AFTER the filler.
- The `hook` field must be the actual opening line of the clip (paraphrased to <=70
  chars), not a summary of the whole clip. It will be shown on screen for the first
  ~1.5s as a text overlay, so make it scroll-stopping on its own.
- `hook_strength` (1-100): rate ONLY the first spoken line against THE HOOK TEST in
  your instructions. Be harsh — a clip that opens with any wind-up scores below 50.
  This is separate from `score` (overall quality). A clip can be insightful but have
  a weak opening; say so honestly here.
- TITLE RULE: the `title` becomes the YouTube Shorts title, so it must stop a scroll.
  Max 60 chars. Lead with the speaker's last name when notable ("Ackman: ...").
  Our real view data shows ONE title style wins: a CURIOSITY GAP aimed at the viewer
  ("you"/"your"), opening a loop the clip then closes. Plain topic statements get ~0
  views. Use this pattern:
  WINNERS (curiosity gap + "you"):
    "Ackman: The #1 Thing You're Not Prepared For"   (our top performer)
    "The Mistake That Costs You Everything"
    "Why You're Poorer Than You Think"
  LOSERS (neutral topic statements — avoid):
    "Marks: The Truth About Market Volatility"
    "US Is No Longer a Safe Haven"
    "Macro Funds Return Just 2.8% a Year"
  Never reuse the source video's title. Write a fresh one from the clip's content.

Transcript:
{transcript}"""


def pick_clips(
    transcript: str,
    segments: list[Segment],
    n: int,
    duration_preset: str = "standard",
) -> list[ClipPick]:
    # The Anthropic SDK reads ANTHROPIC_API_KEY automatically.
    # Setting ANTHROPIC_BASE_URL redirects all calls — that's how DeepSeek's Anthropic-compat
    # endpoint works (https://api.deepseek.com/anthropic). No SDK swap needed.
    client = Anthropic()
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    dur_min, dur_max = DURATION_PRESETS.get(duration_preset, DURATION_PRESETS["standard"])
    msg = client.messages.create(
        model=model,
        # DeepSeek V4 emits a `thinking` block before the `text` answer. On long
        # transcripts (1hr+ podcasts) the thinking phase alone can burn 8k+ tokens,
        # leaving no room for the JSON. 16k gives the thinking plenty of room while
        # still being well below DeepSeek's 65k cap. Anthropic models silently cap
        # at their own limit, so this is harmless on Claude.
        max_tokens=16000,
        system=_system_prompt(),
        messages=[{"role": "user", "content": USER_TEMPLATE.format(
            n=n, transcript=transcript, dur_min=dur_min, dur_max=dur_max,
        )}],
    )
    # DeepSeek returns multiple content blocks (thinking + text); only `text` carries
    # the JSON answer. Filter on type AND non-None text so a malformed block doesn't
    # raise TypeError in the join.
    raw = "".join(b.text for b in msg.content if b.type == "text" and b.text).strip()

    # Defensive: strip ```json fences if the model adds them despite instructions
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

    if not raw:
        # Most likely cause: thinking-block models burned the whole token budget on
        # internal reasoning, leaving no room for the text block.
        block_types = [b.type for b in msg.content]
        raise RuntimeError(
            f"Model returned no text (model={model}, stop_reason={msg.stop_reason}, "
            f"blocks={block_types}). If stop_reason='max_tokens', raise max_tokens further."
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Some models (notably DeepSeek) occasionally wrap the JSON in prose like
        # "Here are the clips: {...}". Extract the first {...} block and retry.
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise RuntimeError(
                f"Model returned non-JSON output (model={model}). First 300 chars:\n{raw[:300]}"
            )
        data = json.loads(match.group(0))
    picks = []
    # Allow ~20% slop on the upper bound since word-snapping can extend the end
    # past the model's chosen timestamp; under-min we keep tight.
    max_allowed = dur_max * 1.2
    for c in data.get("clips", []):
        start = _parse_ts(c["start"])
        end = _parse_ts(c["end"])
        start, end = _snap_to_words(start, end, segments)
        dur = end - start
        if dur < max(5, dur_min * 0.7) or dur > max_allowed:
            continue  # outside the requested duration window
        hook_strength = int(c.get("hook_strength", 0))
        # Drop clips with a weak opening line — a soft first second kills retention.
        # If the model didn't return hook_strength at all (0), don't filter (back-compat).
        if hook_strength and hook_strength < MIN_HOOK_STRENGTH:
            continue
        picks.append(ClipPick(
            start=start,
            end=end,
            title=c.get("title", "Untitled")[:80],
            hook=c.get("hook", ""),
            score=int(c.get("score", 0)),
            hook_strength=hook_strength,
        ))
    # Sort strongest-hook-first within the kept set so the daemon's "top N" are the
    # most scroll-stopping, not just the highest overall quality.
    picks.sort(key=lambda p: (p.hook_strength, p.score), reverse=True)
    return picks


def _parse_ts(s: str) -> float:
    parts = s.strip().split(":")
    if len(parts) == 3:
        h, m, sec = parts
    elif len(parts) == 2:
        h = "0"; m, sec = parts
    else:
        return float(s)
    return int(h) * 3600 + int(m) * 60 + float(sec)


def _snap_to_words(start: float, end: float, segments: list[Segment]) -> tuple[float, float]:
    """Move start to the nearest word-start <= requested, end to nearest word-end >= requested.
    This avoids cutting mid-syllable, since whisper word boundaries are tighter than segments."""
    all_words = [w for s in segments for w in s.words]
    if not all_words:
        return start, end

    snapped_start = start
    snapped_end = end
    # Nearest word-start at or before `start`. Bias +0.02 INTO the word, not before it —
    # any leading silence reads as "dead air" on a vertical short and kills retention.
    candidates = [w.start for w in all_words if w.start <= start + 0.2]
    if candidates:
        snapped_start = max(0.0, candidates[-1] + 0.02)
    # Nearest word-end at or after `end`
    candidates = [w.end for w in all_words if w.end >= end - 0.2]
    if candidates:
        snapped_end = candidates[0] + 0.1
    return snapped_start, snapped_end
