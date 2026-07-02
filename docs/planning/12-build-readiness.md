# 12 — Build Readiness (go / no-go)

The synthesis doc. Answers: *is the planning complete enough to start building, and what's the
first thing we build?* Read after 00–11.

## Confidence verdict

**Are we ready to start building? — Yes, for the scoped version. No, for the "full OpusClip clone."**

- The **engine** is proven (`backend/`), the **stack** is decided (Next.js + FastAPI + Modal +
  Postgres + R2), the **economics** work (~94% margin, doc 06), the **feature gap** is mapped to
  the checkbox (doc 09), the **GTM** is a known-good playbook (doc 10), and the **brand/theme** is
  specified (doc 11).
- The **honest blocker is not readiness — it's scope.** Building all of doc 09 before validating
  demand is the failure mode (saturated market, doc 08). Build the **wedge** first.

**Recommended first build = the scope correction from doc 08:**
Niche (finance) **clip autopilot** on **owned/licensed content**, YouTube-only publishing, web MVP,
DeepSeek picker, split CPU/GPU workers — marketed on automation + fairness, grown via the
watermark viral loop + affiliates.

## Planning completeness checklist

| Area | Doc | Status |
|---|---|---|
| Vision / users / value | 00 | ✅ |
| Architecture | 01 | ✅ |
| Tech stack | 02 | ✅ (3 provider picks still open) |
| Roadmap / phases | 03 | ✅ |
| Data model | 04 | ✅ |
| Pricing / billing | 05 | ✅ (prices pending Phase-0 cost measure) |
| Unit economics | 06 | ✅ |
| Positioning / selling points | 07 | ✅ |
| Feasibility / gaps | 08 | ✅ |
| Feature parity checklist | 09 | ✅ |
| Growth / marketing | 10 | ✅ |
| Brand / theme / design system | 11 | ✅ |

**Planning is complete.** What remains are *decisions* and *measurements*, not more planning.

## Decisions that blocked Phase 0 — ALL RESOLVED (2026-07-02)

1. **Scope: niche-autopilot wedge.** Finance-niche clip Autopilot, YouTube-only publishing first;
   grow toward the full Phase 0–6 parity roadmap once the wedge validates.
2. **Content-rights model: owned/licensed only.** Users clip their own uploads and their own
   connected channels (or explicitly licensed feeds). No arbitrary-URL clipping on the hosted
   product — kills doc 08 GAP 2. Autopilot runs on the user's own long-form content.
3. **Providers: Clerk (auth) + Supabase (Postgres) + R2 (storage).** Locked in doc 02.
4. **Name: Clipilot — approved.** Next action: verify/grab domain (clipilot.com/.ai) and social
   handles before anything public.
5. **Marketing timing: stays at Phase 6.** No landing/waitlist pulled forward (doc 03).

## Phase 0 kickoff (unblocked — the concrete first tasks)

1. **Validate the name** — domain + trademark + handles for Clipilot (doc 11 §8).
2. **Measure real cost** — one Modal GPU run on a sample video → actual $/source-minute; lock
   prices in doc 05 (doc 06 action item).
3. **Monorepo scaffold** — add `web/` (Next.js + shadcn/ui + design tokens from doc 11 §5),
   `infra/` (Modal), keep `backend/`; wire CI (lint/typecheck + pipeline smoke test).
4. **Engine on Modal** — package `pipeline.py` as a Modal function; render one clip end-to-end
   from a URL, GPU transcription, output to R2. *(The single riskiest integration — de-risk first.)*
5. **Split CPU/GPU** — prove the cost lever (doc 06): transcription on GPU, reframe/caption on CPU.
6. **Eval harness** — fixed sample videos + a way to rate clip quality & time-to-first-clip, so we
   can benchmark vs Opus/Reap (doc 08 GAP 8) and catch regressions.

*(A landing + waitlist task was considered here but dropped — marketing stays at Phase 6 per the
resolved decision above.)*

## What "done with Phase 0" looks like
One command renders a real clip from a URL on Modal to R2 within a measured cost, and we have a
name we own and a price we can defend. That's the green light for Phase 1 (doc 03).

## Standing risks to keep visible (from doc 08)
Market saturation · content-rights/copyright on the autopilot model · TikTok/IG audit lead time ·
acquisition cost in a crowded field. None block *building*; all shape *scope and sequencing*.

---

### The one-line recommendation
**Approve the niche-autopilot scope, lock the 5 decisions above, and start Phase 0 with the Modal
engine spike + the landing/waitlist.** The planning is done; the next move is a small, measurable
build that de-risks cost and validates demand before we invest in the full parity surface.
