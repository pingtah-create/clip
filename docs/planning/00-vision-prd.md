# 00 — Vision & Product Requirements

## Vision

The fastest way to turn any long video into a set of high-performing short clips — and,
uniquely, the only tool that can run that loop **fully autonomously** for a channel. We match
OpusClip feature-for-feature, then win on automation and a learning loop that gets better with
every clip a user posts.

## Target users

- **Solo creators & podcasters** — have long episodes, want Shorts/Reels/TikToks without editing.
- **Agencies & social teams** — manage many creators; need brand kits, workspaces, volume.
- **"Set-and-forget" operators** — want a niche channel that grows on autopilot (our wedge).
- **Developers** — want the clipping engine via API in their own product.

## Value proposition

| Job the user has | How we serve it |
|---|---|
| "I have a 2h podcast, I need 10 clips." | Upload/URL → AI picks + reframes + captions → download/publish. |
| "Which clip is worth posting?" | Per-clip **virality score** + hook strength. |
| "I don't want to edit captions frame by frame." | Editable karaoke captions in-browser, brand-styled. |
| "Post everywhere without re-uploading." | One-click publish + scheduler: YT Shorts, TikTok, Reels. |
| "I don't even want to be in the loop." | **Autopilot**: connect a source + account, we clip and post on a schedule. |
| "Make my next clips better." | **Learning loop**: selection improves from this account's real view stats. |

## Feature requirements

### Parity with OpusClip (must-have for a credible launch)
- Ingest by YouTube URL or file upload.
- AI highlight detection with a 0–100 virality score per clip.
- Active-speaker-aware 9:16 reframe (also 1:1 and 16:9 output).
- Auto karaoke captions, **editable** (text, timing, style, emphasis colors).
- Multi-language transcription (Whisper already supports 25+).
- Brand kits/templates (fonts, colors, logo, intro/outro).
- Team workspace (orgs, seats, roles).
- Multi-platform publishing + scheduler.
- Public REST API.
- AI B-roll insertion.
- Accounts, plans, credit-based billing, watermarked free tier.
- Marketing site: landing, pricing, blog/SEO, docs.

### Our differentiators (why switch to us)
- **Autopilot channels** — the productized daemon: discover (RSS/search) → clip → post on a
  schedule, unattended. OpusClip still needs a human to curate and schedule.
- **Per-account learning loop** — `top_performers`-style feedback, but scoped per connected
  channel, so selection is tuned to *that* audience.
- **Niche style presets** — swappable picker "voices" (finance, sports, comedy) instead of one
  generic model.

## Non-goals (explicitly out of scope)

- A general timeline video editor (we are clip-first, not a DaVinci competitor).
- Live-streaming / real-time clipping (batch only, at least through v1).
- Hosting users' full video libraries (we keep sources only as long as needed to render).
- Mobile native apps at launch (responsive web first).

## Success metrics

- **Activation:** % of signups that render ≥1 clip in their first session.
- **Time-to-first-clip:** median seconds from upload to first playable clip.
- **Clip quality:** % of rendered clips passing the `verify` gate; user download/publish rate.
- **Conversion:** free → paid; and paid retention (OpusClip's "projects vanish on cancel" is a
  known pain — we can compete on fairer retention).
- **Autopilot stickiness:** clips auto-posted per active autopilot channel per week.
- **Unit economics:** GPU cost per source-minute vs. credit price (must stay positive).

## Key risks

- **GPU cost** is the dominant variable cost (transcription ≈ 55% of pipeline time). Pricing and
  Modal auto-scaling must keep cost/source-minute under the credit price. See
  [05-pricing-billing.md](./05-pricing-billing.md).
- **Platform publishing APIs** (TikTok/Instagram) have strict review + rate limits; treat as a
  dedicated phase, not a checkbox.
- **Commodity engine** — the moat is distribution, UX, and Autopilot, not the model. Plan
  marketing/SEO as real work, not an afterthought.
- **Abuse / copyright** — hosted clipping of arbitrary URLs invites DMCA and ToS issues; need
  usage policy, rate limits, and takedown handling before public launch.
