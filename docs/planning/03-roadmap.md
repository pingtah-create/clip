# 03 — Phased Roadmap

The full feature set, sequenced. Each phase lists **goal**, **scope (what we build)**, and
**how it works** for the non-obvious parts (landing page, auth, editor, billing, publishing,
autopilot). Phases are ordered so each is independently shippable and de-risks the next.

> Legend: 🆕 new build · ♻️ adapt existing `backend/` code · 🔌 third-party integration

---

## Phase 0 — Foundations

**Goal:** a monorepo, CI, and cloud accounts ready; the engine proven to run on Modal GPU.

**Scope**
- 🆕 Monorepo layout: `web/` (Next.js), keep `backend/`, add `infra/` (Modal), keep `docs/`.
- 🆕 CI (GitHub Actions): web lint/typecheck; pipeline smoke test on a short sample clip.
- 🔌 Provision accounts: Vercel, Modal, Postgres host, R2, Stripe (test mode), auth provider.
- ♻️ Package `pipeline.py` as a Modal function; render one clip end-to-end on GPU from a URL.
- 🆕 Minimal test scaffolding (there is none today) around `select`/`verify` pure logic.

**How it works:** Modal builds a container image with ffmpeg + the `requirements.txt` deps +
CUDA Whisper. A test invocation takes a YouTube URL, runs the existing stages, and writes a
clip to R2. This proves the single hardest integration before any UI exists.

---

## Phase 1 — Cloud MVP (auth + upload → clips → download)

**Goal:** a logged-in stranger can turn a video into downloadable clips. No billing, no editor.

**Scope**
- 🔌 **Auth** — sign up / log in / sessions; a `users` (+ `orgs`) record on first login.
- 🆕 **Postgres state** — `projects`, `jobs`, `clips` tables replace the in-process dict.
- 🆕 **API** — `POST /api/process` writes a job + enqueues (no more background thread);
  `GET /api/jobs/{id}` reads status from Postgres; auth-guarded.
- ♻️ **Worker** — Modal function runs the pipeline, streams stage progress back via API callback.
- 🆕 **Storage** — signed-URL direct upload for files; yt-dlp path for URLs; clips saved to R2.
- 🆕 **Dashboard (Next.js app)** — new project (URL/upload) → progress → clip grid with
  virality score → download. Retire the legacy `frontend/`.

**How auth works:** the Next.js middleware protects `(app)` routes; on request it attaches a
session token the FastAPI API verifies (JWKS/JWT). No password handling in our code — the
provider owns it. First authenticated request upserts the user and a personal org.

**Definition of done:** end-to-end for real accounts; job survives server restart (it's in
Postgres, unlike today's web UI which loses its index).

---

## Phase 2 — The Editor & parity core

**Goal:** clips are editable in-browser, not take-it-or-leave-it renders.

**Scope**
- ♻️ **Editable captions** — `captions.py` also emits **cue data as JSON** (words, timings,
  styles) alongside the burned `.ass`. Editor lets users fix text, retime, restyle, change
  emphasis colors; re-render applies edits.
- 🆕 **Caption editor UI** — transcript-synced editor with live preview.
- 🆕 **Trim & boundaries** — adjust clip start/end (snap to Whisper word edges, as `select.py`
  already does server-side).
- ♻️ **Reframe controls** — choose 9:16 / 1:1 / 16:9; nudge the crop; expose `REFRAME_ZOOM_OUT`.
- ♻️ **Multi-language** — surface Whisper language selection/auto-detect in the UI.
- 🆕 **Virality score UI** — show the score + hook strength per clip, sorted best-first (the
  data already exists from `select.py`).

**How the editor works:** the player plays the *source* segment with an ASS/canvas caption
overlay driven by the JSON cue data — so edits preview instantly without a re-render. "Export"
triggers a lightweight re-render job (captions/trim only) rather than the full pipeline when
possible.

---

## Phase 3 — Monetization (accounts, plans, credits, billing)

**Goal:** we can charge, meter usage, and gate features by plan.

**Scope**
- 🔌 **Stripe** — products/prices for Free / Starter / Pro / Business; customer portal.
- 🆕 **Credit metering** — 1 credit = 1 source-minute (the OpusClip model, and it matches our
  cost driver). Balance checked before enqueue; decremented on successful render.
- 🆕 **Plan gates** — watermark + short retention + limited minutes on Free; watermark-free,
  more minutes, all aspect ratios, scheduler on paid.
- 🆕 **Usage dashboard** — minutes used, credits left, invoices.
- 🆕 **Watermark** — a caption/overlay branch in `captions.py`/`reframe.py` for the free tier.

**How billing works:** Stripe Checkout for plan purchase; a webhook updates the org's
`subscription` + monthly credit grant. Metered add-on minutes reported to Stripe usage records.
Retention/watermark are read from the org's plan on each render. See
[05-pricing-billing.md](./05-pricing-billing.md).

**Fairness note:** avoid OpusClip's most-complained-about behavior (projects deleted 3 days
after cancel) — keep rendered clips downloadable for a grace period after downgrade/cancel.

---

## Phase 4 — Multi-platform publishing

**Goal:** publish and schedule to the major short-form platforms from inside Clip.

**Scope**
- ♻️ **YouTube** — already have `youtube.py`; move to **per-user OAuth tokens** (not one local
  token file), store encrypted.
- 🔌 **TikTok** — Content Posting API (app review required; treat as its own sub-milestone).
- 🔌 **Instagram** — Reels via the Graph API (Business/Creator accounts).
- 🆕 **Connected accounts** — OAuth connect/disconnect per platform, per org.
- 🆕 **Scheduler** — pick platforms + time; a scheduled job posts the rendered clip.

**How publishing works:** users connect a social account via OAuth; we store refresh tokens
encrypted and mint access tokens at post time. Publishing is a queued job with retries and
per-platform rate-limit handling. The `youtube_token.json` model becomes per-user DB rows.

**Reality check:** TikTok/Instagram API access requires app review and adherence to their
content policies — this is calendar time, not just code. Ship YouTube first, others as approved.

---

## Phase 5 — Differentiators & advanced features

**Goal:** the reasons to pick us over OpusClip.

**Scope**
- ♻️🆕 **Autopilot channels** — productize `daemon.py`: per-org config (sources from RSS/search,
  cadence, niche, connected account, score floor) stored in Postgres; a scheduled worker runs
  discover → clip → post unattended. Dashboard shows the autonomous history (today's
  `processed.json`, but per-account and queryable).
- ♻️🆕 **Per-account learning loop** — generalize `top_performers.json`: pull real view stats
  from the connected channel, feed the best-performing clips back into that org's picker prompt.
- 🆕 **Niche style presets** — swappable picker "voices" (finance/sports/comedy), extending the
  single `style.md` into selectable, per-org presets.
- 🆕 **Brand kits** — fonts, colors, logo, intro/outro applied at caption/reframe time.
- 🆕 **Team workspace** — org roles (owner/editor/viewer), seats, shared projects/brand kits.
- 🔌🆕 **AI B-roll** — insert stock or generated cutaways on keywords/silences.
- 🆕 **Public API + keys** — the pipeline as an API for developers; rate-limited, metered.

**How Autopilot works:** it's the daemon, but every knob that's an env var today
(`DAEMON_*`, `channels.txt`, `queries.txt`, `style.md`) becomes per-org DB config, and the
"post" step uses that org's connected accounts and credit balance. First-run seeding
(`FIRST_RUN_SEEDS_ONLY`) still prevents backfilling a busy channel.

---

## Phase 6 — Marketing site & launch

**Goal:** a site that converts, and the operational readiness to open the doors.

**Scope**
- 🆕 **Landing page** — hero (paste-a-URL demo), social proof, feature sections
  (ClipAnything-style genre grid, ReframeAnything, editor, Autopilot as the hero differentiator),
  CTA to sign up. SSG for speed/SEO.
- 🆕 **Pricing page** — the plans from Phase 3, comparison table, FAQ (address the "clips vanish
  on cancel" fear head-on).
- 🆕 **Blog / SEO** — programmatic + editorial content ("turn podcast into shorts", niche guides);
  the acknowledged real moat since the engine is commodity.
- 🆕 **Docs** — for the public API and for using the app.
- 🆕 **Auth pages** — branded sign-in/up, email verification, password reset (mostly provider UI,
  themed).
- 🆕 **Analytics + funnels** — product analytics, conversion tracking, error monitoring.
- 🆕 **Legal/ops** — ToS, privacy, acceptable-use (copyright/DMCA), rate limits, abuse handling.

**How the landing demo works:** an unauthenticated "try it" that runs a single short clip on a
capped queue → gated behind sign-up to see/download results. Converts curiosity into an account
without giving away unlimited free GPU.

---

## End state — what exists after Phase 6

By the end of Phase 6 the product is a credible OpusClip alternative, plus our wedge:

- **Full parity floor** (doc 09 "must-have"): auth + accounts, upload/URL ingest, AI clip
  selection with virality scores, speaker-tracked reframe in all aspect ratios, editable
  animated captions, trim/timeline editing, title/hashtag generation, freemium + watermark +
  credit billing + retention tiers, YouTube/TikTok/IG publishing + scheduler, and a marketing
  site (landing, pricing, blog, docs).
- **Differentiators Opus doesn't have**: Autopilot channels, per-account learning loop, niche
  style presets, fairer retention on cancel.
- **Consciously deferred beyond Phase 6** (doc 09 "defer" list — gaps vs Opus we accept at
  launch): ClipAnything-style non-talking-head genres (our pipeline is face-gated until the
  Phase 5 item lands), AI voice-over, video upscaling, real-time trend analysis, Drive/Vimeo/
  Zoom import, MCP/Zapier, SSO/enterprise. None are needed for a competitive launch.

## Sequencing rationale

- **0→1** proves the riskiest integration (engine on Modal, statelessly) before UI investment.
- **Editor (2) before billing (3)** so the paid product is actually worth paying for.
- **Billing (3) before publishing (4)** so revenue starts before the slow platform-review work.
- **Differentiators (5)** once parity + revenue exist — this is where we pull ahead.
- **Marketing (6)** built alongside but launched last, when the product can back the promises.
  (Landing page + waitlist can be pulled earlier if we want to validate demand first — a small,
  low-risk reorder.)

## Sequencing decision (resolved 2026-07-02)

**Marketing stays at Phase 6** — no public landing/waitlist pulled forward. No public presence
until the product can back the promises; demand risk is accepted in exchange for not building
marketing twice. (Phase 0's "landing + waitlist" kickoff task in doc 12 is therefore dropped.)
