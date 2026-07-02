# 08 — Feasibility & Planning Gaps (the honest read)

This doc exists to counter optimism bias in the rest of the plan. The other docs describe *how*
to build it; this one asks *should we, and what did we ignore.*

## Feasibility verdict

| Question | Verdict | Why |
|---|---|---|
| Can we build the clip engine? | ✅ Done | Exists in `backend/`, works. |
| Can we wrap it as a multi-tenant SaaS? | 🟡 Yes, but big | 6–12 months of productization for a small team; large surface area (auth, billing, editor, publishing, marketing, ops). Not hard, just *a lot*. |
| Can we compete with Opus commercially, head-on? | 🔴 Low probability | Saturated market + legal exposure + distribution war vs. funded incumbents. |
| Can we win a narrow niche with Autopilot? | 🟡 Plausible | The only realistic wedge — and even it has a legal caveat (below). |

**Bottom line:** the constraint was never engineering. It's **market saturation, content rights,
platform gatekeeping, and distribution.** Build for a niche or don't build.

## Critical gaps the earlier planning ignored

### GAP 1 — Competitive reality (we only benchmarked OpusClip)
The market has 10+ serious players: **Reap, Vizard, Submagic, Klap, Munch, Descript, VEED,
CapCut, Riverside, quso, WayinVideo.** Reap beats OpusClip on time-to-first-clip (4–5 min vs
~25 min on a 90-min podcast); Submagic wins on animated captions + B-roll; Klap is mobile-first.
Reviews say the tools are converging and viral-scoring is table stakes. **Implication:** feature
parity is the floor, not a strategy. We need a wedge that isn't "same as Opus."
→ *Action:* a real competitor teardown (features/price/positioning) before committing to build.

### GAP 2 — Content rights & copyright (the plan's biggest contradiction)
Downloading others' YouTube videos via yt-dlp **violates YouTube ToS**, and **auto-clipping and
reposting content you don't own is commercial-scale copyright infringement** — the exact thing
rights-holders pursue. OpusClip avoids this because *users upload their own content*. **Our
Autopilot wedge — auto-clipping other people's podcasts — is the legally riskiest thing in the
whole plan.**
→ *Action / likely pivot:* Autopilot should operate on content the user **owns or has explicit
rights/permission to** (their own channel, licensed feeds, partnerships), not arbitrary URLs.
This reframes the product and must be decided before Phase 5. Add ToS, AUP, DMCA agent, takedown
flow before any public launch.

### GAP 3 — Platform publishing is gated and slow
TikTok Content Posting API needs an **audit (2–6 weeks, rejections add 1–2 weeks)**; **unaudited
= private-only posts, and you can't test with real users until you pass.** Instagram Reels needs
Business/Creator accounts + Graph API review. Per-creator daily post caps (~15/day) apply.
→ *Action:* start the TikTok/IG app-review process *early and in parallel* (it's calendar time,
not code); ship YouTube-only first; don't promise multi-platform on the landing page until audited.

### GAP 4 — No resourcing / timeline / who-builds-this
The plan never states team size, timeline, or budget. Honest estimate for a **solo dev**: this is
a **9–18 month** effort to a credible paid launch, most of it *not* the engine (editor UI,
billing, publishing audits, marketing, support). With **1–2 additional people** (a frontend dev
and a growth/marketer), 4–6 months is plausible.
→ *Action:* decide the team and the time budget; if solo and part-time, scope down hard (see
"recommended scope" below).

### GAP 5 — Customer acquisition (the actual hard part)
Margins are great (~94%), so the business is **gated by acquisition, not compute** — yet there's
no CAC model, channel strategy, content/SEO plan, or marketing budget. In a saturated market, CAC
is the whole game.
→ *Action:* a GTM plan with target channel (SEO? niche communities? affiliate?), a CAC:LTV target,
and a monthly marketing budget. This deserves its own doc before building.

### GAP 6 — Trust & Safety / abuse / moderation
A hosted service ingesting arbitrary URLs must handle: illegal content scanning, abuse/rate
limiting, copyright takedowns, and account bans. None of this is planned.
→ *Action:* minimum viable T&S (rate limits, AUP, report/takedown path) as a launch blocker.

### GAP 7 — Data privacy & compliance
We store users' videos, transcripts (PII), and OAuth tokens. GDPR/CCPA, a privacy policy, a DPA,
data-retention/deletion, and token encryption are all required, not optional.
→ *Action:* privacy policy + retention/deletion + encryption in Phase 3 (billing) at latest.

### GAP 8 — Quality evaluation (how do we know we're competitive?)
Competitors publish head-to-head benchmarks (Reap tested 9 tools). We have no way to *measure*
clip quality objectively or track regressions. `verify.py` checks correctness, not craft.
→ *Action:* a lightweight eval harness (a fixed set of source videos, human-rated clip quality,
time-to-first-clip) to benchmark against Opus/Reap and catch regressions.

### GAP 9 — YouTube API at multi-user scale
Current upload uses one local OAuth token (6 uploads/day quota). Multi-user means each user
connects *their own* account (their own quota), but our Google Cloud project still needs
**API audit/verification** for many external users, and download-via-yt-dlp remains a ToS gray area.
→ *Action:* Google OAuth app verification; per-user encrypted tokens (already in the data model).

### GAP 10 — Reliability / scaling engineering
Cold starts are costed but there's no SLO, queue backpressure policy, retry/failure UX, or status
page. Fine for MVP, needed before charging.

### GAP 11 — Speaker diarization / multi-speaker
`reframe.py` follows "whoever's mouth moves," but there's no true diarization. For interviews this
causes wrong-speaker crops. Competitors handle multi-speaker layouts (split screen).
→ *Action:* evaluate diarization (e.g. pyannote) as a quality feature; note it adds cost.

### GAP 12 — Mobile
Klap and others are mobile-first; creators clip on phones. We're web-only (listed as a non-goal,
but the market may not accept that long-term).

## Recommended scope correction

Given all of the above, the highest-probability path is **not** "OpusClip clone for everyone":

1. **Narrow to a niche + owned/licensed content.** Autopilot for creators clipping *their own*
   long-form (or explicitly partnered feeds) — kills the copyright risk and gives a real wedge.
2. **YouTube-only publishing at first.** Defer TikTok/IG until audits clear.
3. **Web MVP, no mobile, DeepSeek picker, split CPU/GPU workers** — cheapest credible product.
4. **Prove demand before parity.** Landing + waitlist + the eval harness before building the
   editor/billing surface.

This turns a low-probability moonshot into a scoped, testable bet. Everything in docs 00–07 still
applies — this doc just says *don't build all of it before validating the wedge.*
