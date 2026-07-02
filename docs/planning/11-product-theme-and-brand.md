# 11 — Product Theme & Brand

A cohesive theme across **name → positioning → voice → visual identity → design system →
marketing site → the clips themselves**. Everything ladders up to our one idea: **automation —
short clips that make themselves.** These are recommendations to lock, not final decisions;
validation steps (domain/trademark/handles) noted at the end.

## 1. Name

Naming principles for 2026 AI SaaS: short (5–12 chars, ~2 syllables), descriptive names win
customers ~37% faster (Gartner), `.ai` signals AI-native (up 214% in SaaS) but `.com` reads more
trustworthy long-term. "AI"/"bot" in the name is now redundant — it's assumed.

**Recommended: `Clipilot`** (clip + pilot). Signals the **autopilot wedge** directly, brandable,
trademarkable, pairs with a clear tagline. Seek `clipilot.com` / `clipilot.ai` / `@clipilot`.

Shortlist (in case of conflicts):
| Name | Read | Note |
|---|---|---|
| **Clipilot** ⭐ | clip + pilot → "runs itself" | on-theme, brandable |
| Autoreel | auto + reel | very descriptive, weaker trademark |
| Snipilot | snip + pilot | playful, memorable |
| Clipstream | continuous auto output | evokes a pipeline/feed |
| Reelay | reel + relay | short, abstract, expandable beyond clips |

**Name + tagline** (the recommended pattern):
> **Clipilot — long video in, growing channel out.**

Alt taglines: "Put your clips on autopilot." · "The clip channel that runs itself." · "Hands off.
Views on."

## 2. Positioning statement

> For **creators, podcasters, and niche channel operators** who don't have time to edit, **Clipilot**
> is an **AI clip autopilot** that turns long videos into scored, captioned, platform-ready shorts —
> and, unlike OpusClip and the rest, can **discover, clip, and post entirely on its own** while
> learning what your audience actually watches.

Category we claim: not "AI video editor" (crowded) but **"clip autopilot"** — a new lane where
automation, not manual editing, is the point.

## 3. Brand personality & voice

- **Personality:** effortless, confident, a little futuristic — but **human, not slick-AI**.
  (2026 trend is away from over-polished AI aesthetics toward warmth.)
- **Voice:** plain-spoken, outcome-focused, lightly playful. We talk about *your growing channel*,
  not *our neural networks*. Short sentences. Verbs.
- **Do:** "Post while you sleep." "It just clips." **Don't:** "Leverage our proprietary
  transformer-based highlight extraction pipeline."
- **Tone by surface:** marketing = bold/aspirational; app = calm/reassuring; errors = honest +
  helpful; docs = precise.

## 4. Visual identity

Anchored in 2026 direction: **clarity + minimalism, oversized assertive typography, calm neutrals,
motion-first**, with one energetic accent to signal momentum/automation.

- **Logo direction:** wordmark + a mark suggesting motion/autopilot — a play/clip glyph morphing
  into a forward arrow or orbit. Simple enough to work as a favicon and as the free-tier clip
  watermark (the watermark is a distribution channel — doc 10 — so the mark must read small).
- **Color:**
  - App is **dark-first** (creators work in dark editing UIs; footage pops on dark).
  - Accent: **electric — signals energy/automation** (a vivid violet→blue or lime; pick one).
  - Neutrals: near-black surfaces + soft off-white ("Cloud Dancer"-style) for marketing = calm,
    breathing layouts.
- **Typography:** oversized, confident display for headlines (a geometric/grotesk like Inter Tight,
  Geist, or Satoshi) + a clean readable body of the same family. Type *is* the hero, per 2026.
- **Motion:** motion-first — subtle auto-playing "long video → clips flying out" hero animation;
  micro-interactions that feel alive but never block. Motion communicates the automation promise.
- **Texture:** a touch of "human" (grain, hand-annotations on screenshots) to avoid AI-slick.

## 5. Design system (tokens to implement in the Next.js app)

Define once, share across app + marketing (Tailwind config / CSS vars):

```
color:   --bg, --surface, --surface-2, --border,
         --text, --text-muted,
         --accent, --accent-hover, --accent-contrast,
         --success (score-good), --warn, --danger (verify-fail)
type:    --font-display, --font-body; sizes 12/14/16/20/24/32/48/64
space:   4-based scale (4,8,12,16,24,32,48,64)
radius:  --r-sm 6, --r-md 10, --r-lg 16, --r-full
shadow:  subtle, dark-mode-aware
motion:  --ease (cubic-bezier), --dur-fast 120ms, --dur 240ms
```
Component kit: shadcn/ui (Radix + Tailwind) for speed and consistency. Score badge, clip card,
progress/stage stepper (mirrors pipeline stages), and the caption-preview player are the
signature components.

## 6. Marketing-site theme (page-by-page)

Minimalist, product-first, one CTA per section, light theme with dark product screenshots.

- **Hero:** headline (tagline) + live "paste a URL → watch it clip" demo + primary CTA. Motion.
- **The wedge section (first, not buried):** ⭐ **Autopilot** — "connect a source, we clip and post
  on a schedule." This is our differentiator; it leads.
- **How it works:** 3 steps (in → AI clips + scores + captions → publish/auto-post).
- **Feature grid:** parity features (doc 09) as reassurance, not the star.
- **Social proof:** marquee creators (doc 10), clip counts, view counts.
- **Comparison:** honest "vs OpusClip" incl. our fairness angles (no clip-deletion-on-cancel,
  charge-only-on-success — doc 07).
- **Pricing:** plans (doc 05), FAQ addressing the retention fear head-on.
- **Blog/SEO hub + Docs + Legal (ToS/AUP/Privacy).**

## 7. Clip / caption output themes (the product's *visible* brand)

The clips users publish are our most-seen surface — themes here matter as much as the site.
Ship a set of **named caption/clip presets** (extends `captions.py` + brand kits, doc 09):

| Preset | Look | For |
|---|---|---|
| **Bold** | big, punchy, word-by-word pop, high-contrast | general viral / hype |
| **Clean** | minimal, single-line, subtle | premium / corporate |
| **Podcast** | duotone, speaker-name lower-third | interviews |
| **Finance** | data-forward, green/red number emphasis (our niche ⭐) | investing content |
| **Creator** | user's brand kit (font/color/logo) applied | teams/agencies |

Each theme = a set of ASS style params + color rules, selectable per job and lockable per brand
kit. The current karaoke style becomes "Bold". This is also a marketed feature ("on-brand clips
automatically"), matching OpusClip's brand templates.

## 8. Validation before committing (do this, don't skip)
- Domain: `clipilot.com` / `.ai` availability + price.
- Trademark search (USPTO/EUIPO) for the name in software/SaaS class.
- Social handles across X, TikTok, Instagram, YouTube, LinkedIn.
- Quick gut-check with 3–5 target-niche creators.

## Sources
- 2026 design trends — https://www.eloqwnt.com/blog/saas-website-design-trends , https://venngage.com/blog/ai-and-design-trends/
- SaaS/AI naming — https://madnext.in/the-2026-guide-to-naming-ai-tech-saas-brands/ , https://unicornplatform.com/blog/ai-domain-naming-strategy-for-2026/
