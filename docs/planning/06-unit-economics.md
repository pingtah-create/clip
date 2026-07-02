# 06 — Unit Economics (cost & profit ratio)

**All numbers are estimates to validate in Phase 0** with a real Modal run on a sample video.
They're grounded in current public pricing (sources at bottom), but treat them as a model, not a
quote. The rule stands: **credit price must exceed fully-loaded cost per source-minute.**

## The cost drivers

| Driver | What it scales with | Notes |
|---|---|---|
| **GPU time (Modal)** | source-minutes (transcription) + clip-minutes (reframe/burn) | Dominant variable cost. Transcription ≈ 55% of pipeline time. |
| **LLM select** | transcript length (source-minutes) | Cheap on DeepSeek, ~5× more on Claude Sonnet. Already swappable. |
| **Storage/egress** | clips stored + downloaded | Near-zero on **R2 (no egress fees)**; real on S3. |
| **Cold starts** | jobs-at-low-volume | Modal scales to zero → each job may eat 20–40s of GPU spin-up + model load. Dominates at low volume, amortizes at scale. |

## Reference job: 60-min podcast → 8 clips

GPU pricing used: Modal **L4 @ $0.000222/sec** (~$0.80/hr); apply ~1.25× US regional multiplier.
Whisper `small` at ~20× real-time (large-v3 ~10× → roughly double the transcription time/cost).

| Stage | GPU seconds (naive single-worker) |
|---|---|
| Cold start + model load | ~30 |
| Transcribe (small, 20× RTF) | ~180 |
| Select (LLM call, GPU idle-but-allocated) | ~20 |
| Reframe 8 clips (~6 min video, CPU-bound) | ~575 |
| Captions + ffmpeg burn | ~150 |
| Download / upload / misc | ~45 |
| **Total** | **~1000s (~16 min)** |

**Cost of this job:**
- GPU: 1000s × $0.000222 × 1.25 ≈ **$0.28**
- LLM select: **$0.01** (DeepSeek-flash) to **$0.07** (Claude Sonnet, ~12k in / 2k out)
- Storage/egress (R2): **~$0.01**
- **Total ≈ $0.30 (DeepSeek) to $0.36 (Claude)** → **~$0.005–0.006 per source-minute**

## Profit ratio

At an OpusClip-style effective price of **~$0.10/source-minute** (Starter $15 / 150 min):

| | Per source-minute | 60-min job |
|---|---|---|
| Revenue (plan value) | ~$0.100 | ~$6.00 |
| Cost | ~$0.006 | ~$0.36 |
| **Gross margin** | **~94%** | **~94%** |

Even the **Free tier** (60 min/mo) costs us **~$0.35/user/month** — a cheap acquisition
loss-leader, *if* we cap abuse (rate limits + watermark + sign-up gate on the landing demo).

> Takeaway: **compute is not the constraint.** The ~85–95% gross margin is why OpusClip gives
> away 60 free minutes and still profits. Our real costs are LLM model choice, cold starts at low
> volume, and — the big ones — **marketing, support, and platform/abuse handling**, not GPU.
> Pricing power comes from features/brand, not from a compute-cost advantage.

## Cost levers (how we protect margin / can undercut Opus)

1. **Split CPU stages off the GPU.** Reframe/captions/burn are CPU-bound (mediapipe/opencv/ffmpeg)
   but currently would hold a GPU. Run transcription on GPU, then hand the clip render to a cheap
   **CPU worker** → cuts GPU time ~60–70%. Biggest single lever. (Architecture note for Phase 1.)
2. **Whisper model size.** `small` vs `large-v3` roughly doubles transcription cost; pick per plan
   (large-v3 as a paid "high accuracy" toggle).
3. **DeepSeek-flash for select** (already supported) — ~5× cheaper than Claude for the picker,
   with the option to offer Claude as a premium quality tier.
4. **Keep-warm vs scale-to-zero** — scale-to-zero saves idle cost but adds cold-start GPU per job;
   flip to a warm pool once steady volume justifies it.
5. **R2 over S3** — no egress fees on a download-heavy product.

## Break-even sketch

Fixed monthly costs at MVP scale (Vercel + Postgres + Modal minimums + auth + domain +
monitoring) ≈ low **hundreds of $/mo**. At ~94% margin, a handful of Starter subscribers
(~$15/mo) covers infra; the business is gated by **acquisition**, not compute. This is the number
to pressure-test in Phase 0, then revisit prices in [05-pricing-billing.md](./05-pricing-billing.md).

## Sources
- Modal GPU pricing — https://modal.com/pricing (L4 ~$0.000222/s, A10 ~$0.000306/s, A100 ~$0.000583/s; regional/non-preemption multipliers)
- faster-whisper throughput — https://github.com/SYSTRAN/faster-whisper (≈4× faster than openai/whisper; large-v3 INT8 ~35× RTF on L40S, lower on smaller GPUs)
- OpusClip pricing reference — https://www.opus.pro/pricing
