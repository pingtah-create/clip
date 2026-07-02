# 02 — Tech Stack & Decisions

## Locked choices

| Layer | Choice | Why |
|---|---|---|
| Web + marketing | **Next.js (React)** | One framework for app + SEO marketing/blog; largest ecosystem and hiring pool; first-class Vercel deploy. |
| App hosting | **Vercel** | Native Next.js host; preview deploys per PR; edge/SSR built in. |
| API / engine | **FastAPI (Python)** | Keeps the existing `backend/` engine and its ML deps in one language; async-friendly. |
| GPU workers | **Modal** | Serverless, pay-per-second GPU, scales to zero; wrap `pipeline.py` as a function without cluster ops. |
| Clip selection LLM | **Anthropic SDK** (Claude / DeepSeek via base-url) | Already integrated in `select.py`; no change. |
| Transcription | **faster-whisper** on GPU | Already integrated; GPU cuts the dominant cost. |
| Auth | **Clerk** | Drop-in Next.js auth, orgs/teams/seats built in (needed for team workspace), prebuilt UI. Revisit if pricing bites at scale. *(Locked 2026-07-02.)* |
| Postgres | **Supabase** | Managed Postgres, generous free tier, good DX; MCP access already available. *(Locked 2026-07-02.)* |
| Object storage | **Cloudflare R2** | S3-compatible with **no egress fees** — clips get downloaded a lot, egress is the cost that matters for video. *(Locked 2026-07-02.)* |

### Alternatives considered (for the record)
- Auth: Auth.js (free but we'd build orgs/roles ourselves), Supabase Auth (one fewer vendor).
- Postgres: Neon (per-PR branching), AWS RDS (most control, most ops).
- Storage: AWS S3 (ubiquitous, but egress adds up).

## Still open (decide when needed)

### Queue
- **Modal built-in** to start (fewer moving parts), or **Redis + RQ** if we need richer
  priority/retry control. Decide when we see Phase-1 concurrency needs.

### Billing
- **Stripe** — plans, metered usage (credits), customer portal. Non-negotiable default.

## Repo / workflow

- **Monorepo** (single repo, this one): `backend/` (FastAPI + engine, existing), `web/`
  (Next.js, new), `infra/` (Modal + IaC), `docs/planning/` (this).
- **CI:** GitHub Actions — lint/typecheck web, smoke-test the pipeline on a short sample video
  (`--once`-style), build container images. (No test suite exists yet — Phase 0 adds a minimal one.)
- **Envs:** local → preview (per PR) → staging → prod. Secrets in the platform's secret store,
  never committed (repo already gitignores `.env`, tokens, `data/*.json`).

## Cross-language contract

The Next.js app and FastAPI API share types via an **OpenAPI schema** (FastAPI generates it;
we codegen a typed client for the web app). Keeps the front/back contract honest without a
shared language.
