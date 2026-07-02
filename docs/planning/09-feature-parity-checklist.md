# 09 — Feature Parity Checklist (vs opus.pro, exhaustive)

Every feature found on opus.pro's homepage + pricing page, mapped to our status and roadmap
phase. **Legend:** ✅ have · 🟡 partial · ❌ missing · ⭐ = our priority selling point.

> **Our #1 priority is automated clip generation (Autopilot).** OpusClip's closest analog is
> "auto-import from verified YouTube accounts" + a scheduler — it still needs a human to review
> and it only pulls *your own* channel. Full autonomous **discover → clip → score → post** with a
> per-account learning loop is the thing we do that they don't. Everything else on this list is
> parity we build to be *credible*; the automation is what we build to *win*.

## A. Ingest / import
| Feature | Opus | Us | Phase |
|---|---|---|---|
| Local upload (up to 10GB) | ✅ | 🟡 (works locally) | 1 |
| YouTube URL | ✅ | ✅ (`download.py`) | 1 |
| Google Drive / Vimeo / Zoom / Rumble / StreamYard | ✅ | ❌ | 5+ |
| Auto-import from connected channel | ✅ | 🟡 daemon RSS/search | 5 ⭐ |

## B. Clip selection (core AI)
| Feature | Opus | Us | Phase |
|---|---|---|---|
| Highlight detection | ✅ | ✅ (`select.py`) | have |
| **ClipAnything** — any genre (gaming/sports/vlog) | ✅ | ❌ face-gated | 5 |
| Curation modes: spoken word / visual / sound / emotion / genre | ✅ | 🟡 spoken-word only | 2–5 |
| Virality score (0–100) | ✅ | ✅ score + hook_strength | 2 |
| Reprompt clipping (re-curate by prompt) | ✅ | ❌ | 2 |
| Auto hook | ✅ | ✅ (`Hook` overlay) | have |

## C. Reframe / video
| Feature | Opus | Us | Phase |
|---|---|---|---|
| **ReframeAnything** — object-tracked reframe | ✅ | ✅ (`reframe.py`, speaker-tracked) | have |
| All aspect ratios (9:16 / 1:1 / 16:9) | ✅ | 🟡 9:16 only | 2 |
| Custom reframe / manual nudge | ✅ | ❌ | 2 |
| Video upscaling | ✅ | ❌ | 5+ |

## D. Captions & overlays
| Feature | Opus | Us | Phase |
|---|---|---|---|
| Auto captions (~97%) | ✅ | ✅ (`captions.py`) | have |
| Animated caption templates | ✅ | 🟡 one karaoke style | 2 |
| Editable captions (text/timing/style) | ✅ | ❌ burned-in only | 2 |
| Auto emoji / keyword highlights | ✅ | 🟡 emphasis coloring | 2 |
| Text overlays | ✅ | ❌ | 2 |
| Multi-language transcription (25+) | ✅ | 🟡 Whisper can, not exposed | 2 |

## E. Editing extras
| Feature | Opus | Us | Phase |
|---|---|---|---|
| Text & timeline editor (AI editor) | ✅ | ❌ | 2 |
| Filler-word / pause removal | ✅ | ❌ | 5 |
| AI voice-over | ✅ | ❌ | 5+ |
| AI B-Roll (generated) + stock B-Roll | ✅ | ❌ | 5 |
| Clip title / description / hashtag generator | ✅ | ❌ | 4 |

## F. Publishing & distribution
| Feature | Opus | Us | Phase |
|---|---|---|---|
| Publish to YouTube Shorts | ✅ | ✅ (`youtube.py`) | have→4 |
| Publish to TikTok / Instagram | ✅ | ❌ (audit-gated) | 4 |
| Social scheduler / publishing calendar | ✅ | ❌ | 4 |
| **Fully autonomous discover→clip→post** | ❌ | 🟡 daemon | 5 ⭐ |
| **Per-account learning loop** | 🟡 aggregate | 🟡 top_performers | 5 ⭐ |

## G. Team / brand / business
| Feature | Opus | Us | Phase |
|---|---|---|---|
| Brand templates (font/color/logo/intro/outro) | ✅ | ❌ | 5 |
| Team workspace + member permissions | ✅ | ❌ | 5 |
| Clip analytics | ✅ | ❌ | 5 |
| Real-time trend analysis | ✅ | ❌ | 5+ |

## H. Platform / enterprise / dev
| Feature | Opus | Us | Phase |
|---|---|---|---|
| Video Editing API / Scheduler API | ✅ (Business) | ❌ | 5 |
| MCP connector / Zapier / CMS integration | ✅ | ❌ | 5+ |
| SSO / license mgmt / custom onboarding | ✅ | ❌ | later |
| Invoice / ACH payment | ✅ | ❌ | later |

## I. Account / monetization / infra
| Feature | Opus | Us | Phase |
|---|---|---|---|
| Freemium + watermark on free | ✅ | ❌ | 3 |
| Credit/minute metering | ✅ | ❌ | 3 |
| Tiered storage/retention | ✅ (3d free / 29d starter) | ❌ | 3 |
| Email OTP / auth security | ✅ | ❌ | 1 |
| Processing-speed tiers (priority queue) | ✅ | ❌ | 3 |

## Parity gaps summary (what we must build to be credible)
**Must-have for launch (parity floor):** editable captions + animated templates (D), all aspect
ratios (C), timeline editor (E), title/hashtag generator (F), TikTok/IG publish + scheduler (F),
freemium/watermark/credits/retention (I), auth (I).
**Defer (nice-to-have):** AI voice-over, upscaling, B-roll, trend analysis, MCP/Zapier, SSO.
**Our wedge (build well, market hard):** ⭐ Autopilot autonomy + learning loop (F/A).

## Notable insight from their pricing
OpusClip meters on **processing speed + import sources + AI modes + storage duration + team
seats**, NOT primarily on clip count — reinforcing our source-minute credit model (doc 05). Their
free tier is deliberately *useful but sticky-limited* (watermark + 3-day expiry) to force upgrade;
we mirror the mechanic but soften retention as a trust differentiator (doc 07).
