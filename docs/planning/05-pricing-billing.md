# 05 — Pricing & Billing

## The cost we're pricing against

The dominant variable cost is **GPU time**, and transcription (`transcribe.py`) is ~55% of the
pipeline. Cost scales with **source-minutes processed**, not clips produced — so we meter the
same way OpusClip does: **1 credit = 1 minute of source video**, charged on what goes *in*,
regardless of how many clips come out. This keeps our price aligned with our cost.

**Action item (Phase 0):** measure real Modal GPU seconds + $ per source-minute on a
representative sample. Every price below is a *placeholder* until that number exists; the rule is
**credit price > fully-loaded cost/source-minute** (GPU + LLM select + storage/egress).

> The full cost/profit model — ~$0.006/source-minute cost, ~94% gross margin, and the cost
> levers — lives in [06-unit-economics.md](./06-unit-economics.md). This doc covers how we
> *charge*; that doc covers what it *costs us*.

## Plans (placeholder — mirror OpusClip's shape, undercut on fairness)

| Plan | Price | Monthly minutes | Key gates |
|---|---|---|---|
| **Free** | $0 | ~60 min | Watermarked, short retention, 9:16 only, no scheduler |
| **Starter** | ~$15/mo | ~150 min | Watermark-free, virality scores, all AI modes, basic publishing |
| **Pro** | ~$29/mo | more | All aspect ratios, scheduler, team seat, B-roll, Autopilot |
| **Business** | custom | volume | API, more seats, priority queue, brand kits |

Add-on minutes billed as **metered usage** beyond the plan allotment.

## Our fairness differentiators (deliberate anti-OpusClip)

- **Grace period on cancel/downgrade** — rendered clips stay downloadable for a window instead
  of vanishing in 3 days (OpusClip's #1 complaint). Sales point on the pricing page.
- **Credits reflect work done** — failed renders (engine error, `verify` rejection) are **not**
  charged; only successful clips decrement the ledger.

## How billing works (Phase 3)

1. **Purchase** — Stripe Checkout for a plan → webhook sets `subscriptions.plan` +
   `status` + grants `monthly_credits` (a `credit_ledger` `+delta`).
2. **Pre-flight** — before enqueue, API checks `balance ≥ ceil(source_duration_min)`; if not,
   block with an upgrade prompt (Free) or meter the overage (paid).
3. **Charge on success** — on successful render the worker reports actual source-minutes; API
   writes a `-delta` to `credit_ledger` and, for overage, a Stripe usage record.
4. **Renewal** — monthly period rollover grants fresh credits; unused credits policy (roll over
   vs. reset) is a business decision — default **reset** to match the category.
5. **Portal** — Stripe customer portal for plan changes, invoices, cancel.

## Metering integrity

- `credit_ledger` is **append-only** (an event log) → auditable balance and no lost/double
  charges. Balance is `SUM(delta)`, never a mutable counter.
- Idempotency: each render reports with the `job_id`; the ledger insert is unique per job to
  prevent double-charging on worker retries.

## Open decisions

- Exact prices + minute allotments — **blocked on the Phase-0 cost measurement.**
- Credit rollover: reset monthly (default) vs. accumulate.
- Free-tier watermark style + retention length (address in Phase 3 alongside the watermark render
  branch).
- Annual discount (OpusClip pushes yearly) — likely yes, decide at launch.
