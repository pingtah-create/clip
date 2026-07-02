# Clip → SaaS: Planning Docs

This folder is the planning source of truth for turning **Clip** (a working single-user,
local clipping pipeline) into a hosted, multi-tenant product comparable to
[opus.pro](https://www.opus.pro) — with all of its features plus our own differentiators.

**Status: planning only.** No product code is written from these docs until each phase is
approved. The existing `backend/` pipeline is the reusable core; everything here wraps it.

## Read in this order

1. [00-vision-prd.md](./00-vision-prd.md) — what we're building, for whom, and why we win.
2. [01-architecture.md](./01-architecture.md) — target system: components, data flow, how the
   existing pipeline is reused, how Modal GPU workers fit.
3. [02-tech-stack.md](./02-tech-stack.md) — chosen stack (Next.js + FastAPI + Modal + Postgres)
   and the rationale / alternatives.
4. [03-roadmap.md](./03-roadmap.md) — **the detailed phased plan**: every feature (landing page,
   auth, editor, billing, publishing, autopilot…) broken into phases with scope and how each works.
5. [04-data-model.md](./04-data-model.md) — the Postgres schema that replaces in-process state.
6. [05-pricing-billing.md](./05-pricing-billing.md) — plans, the credit model, Stripe metering.
7. [06-unit-economics.md](./06-unit-economics.md) — **cost & profit ratio**: real GPU/LLM cost
   model, ~85–95% gross margin, and the levers that protect it.
8. [07-positioning.md](./07-positioning.md) — **selling points vs OpusClip**, ranked by how
   defensible they are, and the go-to-market wedge.
9. [08-feasibility-and-gaps.md](./08-feasibility-and-gaps.md) — **read this before building.**
   The honest feasibility verdict, the 12 gaps the rest of the planning ignored (market
   saturation, copyright, platform audits, GTM, T&S…), and a recommended scope correction.
10. [09-feature-parity-checklist.md](./09-feature-parity-checklist.md) — exhaustive checkbox map
    of every opus.pro feature vs. our status and phase; our automation wedge flagged ⭐.
11. [10-growth-marketing-playbook.md](./10-growth-marketing-playbook.md) — how OpusClip actually
    won (funding, viral watermark loop, affiliates, weekly shipping) → our low-capital GTM copy.
12. [11-product-theme-and-brand.md](./11-product-theme-and-brand.md) — name (**Clipilot**),
    positioning, brand voice, visual identity, design-token system, marketing-site theme, and
    named clip/caption output presets.
13. [12-build-readiness.md](./12-build-readiness.md) — **the go/no-go synthesis**: planning
    completeness checklist, the 5 decisions that block Phase 0, and the concrete Phase-0 kickoff.

## The one-paragraph pitch

The hard part — the AI clipping **engine** (transcribe → LLM highlight selection →
active-speaker 9:16 reframe → karaoke captions → verify) — already exists in `backend/` and
works. This is a *productization* effort, not an ML effort: put that engine behind accounts,
a queue, GPU workers, an editor UI, publishing integrations, billing, and a marketing site.
Our edge over OpusClip is **Autopilot** (fully autonomous discover-clip-post, from the existing
daemon) and a **per-account learning loop** that improves clip selection from real view stats.

## Decisions locked

- **Frontend + marketing:** Next.js (React).
- **Engine/API:** keep Python / FastAPI, reuse `backend/`.
- **GPU workers:** Modal (serverless, pay-per-second, scales to zero).
- **Scope:** full feature parity with OpusClip + differentiators, delivered in phases.

## Decisions still open

Tracked at the bottom of [02-tech-stack.md](./02-tech-stack.md): auth provider, Postgres host,
object-storage provider, and the exact free-tier watermark policy.
