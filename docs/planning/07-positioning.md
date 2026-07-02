# 07 — Positioning & Selling Points vs OpusClip

## The honest starting point

The clipping **engine is a commodity** — Whisper + an LLM picker + ffmpeg/mediapipe/libass.
OpusClip's moat is **not** technology; it's **distribution, brand (16M users), and integrations**.
So "we have the same features" is table stakes, not a reason to switch. We need reasons a specific
buyer picks *us*. Ranked strongest → weakest:

## Tier 1 — Real, defensible differentiators

### 1. Autopilot (fully autonomous channels) — our headline
OpusClip finds clips; a human still curates and schedules. **We already run the full loop
unattended**: discover (RSS/search) → clip → score → post on a cadence. Productized (from
`daemon.py`), this is a **different product category** — "a channel that grows itself," not "an
editing tool." Nobody in the mainstream competitor set sells this.
- *Who buys it:* operators who want a niche channel without doing the work; agencies running many
  channels.
- *Why it's defensible:* it's a workflow + trust bet, not a feature checkbox — hard to bolt onto a
  human-in-the-loop editor.

### 2. Vertical focus (start with finance/investing)
Your existing `style.md`, `channels.txt`, `queries.txt` are already tuned for finance. A tool that
is *demonstrably best* at one niche beats a generalist for that niche's creators (better hooks,
right vocabulary, niche-aware scoring). Land a vertical, then expand.
- *Why it works:* OpusClip must stay general; a vertical wedge is where a small player wins.

### 3. Per-account learning loop
`top_performers` feedback, but scoped per connected channel — selection tunes to *that* audience's
real view stats over time. "Gets better the more you post" is a retention story competitors don't
tell.

## Tier 2 — Fairness & trust plays (cheap to build, resonate in reviews)

### 4. We don't hold your clips hostage
OpusClip's most-cited complaint: **projects vanish 3 days after you cancel.** We keep rendered
clips downloadable through a grace period. Put this *on the pricing page* as a direct contrast.

### 5. Charge only for successful renders
Failed jobs / `verify`-rejected clips don't burn credits. Transparent metering (append-only
ledger) — again, a stated contrast to credit-per-source-minute-regardless anxiety.

### 6. Pricing flexibility our cost structure allows
Margins are ~85–95% (see [06-unit-economics.md](./06-unit-economics.md)), so we have room to:
- offer a **more generous free/entry tier**, or
- a **flat "unlimited-ish" niche plan**, or
- a **self-host / BYO-key** option for power users (a segment OpusClip can't serve).
Pick one as a wedge; don't do all three.

## Tier 3 — Parity features (needed to be credible, not to win)
Editable captions, virality score, multi-aspect reframe, brand kits, team workspace, scheduler,
multi-language, API, B-roll. We build these so we're not disqualified — but they don't sell against
an incumbent that already has them and more polish. Treat as cost of entry.

## What we will NOT claim
- "Better AI clip detection." Unprovable and probably untrue vs a company optimizing it full-time.
- "Cheaper because our tech is cheaper." Compute is cheap for everyone; this isn't a real edge.
- Head-to-head on the general market. That's a distribution/capital fight we lose today.

## Go-to-market wedge (one sentence)
**"The autopilot that grows a [finance] short-form channel for you"** — sell the *outcome*
(a growing channel) to a *specific niche*, powered by autonomy + a learning loop, with fair,
transparent pricing. Expand to more niches and the manual editor market only after that wedge lands.

## One-line positioning options (for the landing hero — to pick later)
- "Put your clips on autopilot." (outcome + differentiator)
- "The AI clip channel that runs itself."
- "Long video in. Growing channel out. Hands off."
