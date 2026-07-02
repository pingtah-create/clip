# 04 — Data Model

Postgres replaces two things that exist today: the **in-process job dict** (`jobs.py`, lost on
restart) and the **daemon's JSON files** (`processed.json`, `top_performers.json`). Below is the
target schema. Types are indicative; finalize in migrations during Phase 1.

## Entities

### Identity & tenancy
```
users            id, email, name, created_at
orgs             id, name, plan, stripe_customer_id, created_at
                 -- personal org auto-created on first login; teams add more
memberships      id, user_id → users, org_id → orgs, role (owner|editor|viewer)
```
Every resource below is owned by an **org**, not a user, so team workspace and personal use
share one model.

### Billing & usage
```
subscriptions    id, org_id, stripe_subscription_id, plan, status,
                 current_period_end, monthly_credits
credit_ledger    id, org_id, delta (+grant / -spend), reason, job_id?, created_at
                 -- balance = SUM(delta); 1 credit = 1 source-minute
api_keys         id, org_id, hashed_key, name, last_used_at, revoked_at
```

### Clipping core (replaces `jobs.py`)
```
projects         id, org_id, title, source_kind (url|upload), source_ref, created_at
jobs             id, project_id, org_id, status, stage, progress,
                 source_storage_key, source_duration_sec, error, created_at, finished_at
                 -- status: queued|running|done|failed ; stage mirrors pipeline stages
clips            id, job_id, org_id, storage_key (mp4), ass_key,
                 caption_cues (jsonb),        -- editable cue data (Phase 2)
                 start_sec, end_sec,
                 score, hook, hook_strength,  -- from select.py
                 face_coverage,               -- from reframe.py
                 verify_ok, verify_reason,    -- from verify.py
                 aspect_ratio, watermarked, created_at
```
`clips` carries every signal the pipeline already computes (score/hook/face_coverage/verify) so
the UI and the learning loop can read them without re-deriving.

### Publishing (Phase 4)
```
social_accounts  id, org_id, platform (youtube|tiktok|instagram),
                 external_account_id, encrypted_refresh_token, connected_at
publications     id, clip_id, social_account_id, status (scheduled|posted|failed),
                 scheduled_for, external_post_id, views?, error, posted_at
```
`publications.views` backfilled from platform stats → feeds the learning loop.

### Autopilot & learning (Phase 5)
```
autopilot_configs id, org_id, enabled, cadence, niche_preset,
                  social_account_id, min_score_to_post, max_posts_per_day,
                  sources (jsonb: rss urls + search queries)  -- was channels.txt/queries.txt
autopilot_seen    id, org_id, video_external_id, first_seen_at, outcome
                  -- replaces processed.json's "already seen" markers
brand_kits        id, org_id, name, font, colors (jsonb), logo_key, intro_key, outro_key
style_presets     id, org_id?, name, prompt_text  -- per-org override of style.md; null org = global
top_performers    id, org_id, clip_id, views, captured_at
                  -- replaces top_performers.json; scoped per org for the learning loop
```

## Mapping from today's state

| Today | Becomes |
|---|---|
| `jobs.py` in-process dict | `projects` + `jobs` + `clips` tables |
| `data/processed.json` | `autopilot_seen` + `jobs`/`clips` history |
| `data/top_performers.json` | `top_performers` (per org) |
| `channels.txt` / `queries.txt` | `autopilot_configs.sources` (per org) |
| `style.md` | `style_presets` (global default + per-org overrides) |
| `data/youtube_token.json` | `social_accounts.encrypted_refresh_token` (per user) |
| `.env` `DAEMON_*` knobs | `autopilot_configs` columns |
| clips on local disk | object storage; keys stored on `clips`/`jobs` |

## Notes

- **Immutability at the app layer:** treat rows as append-where-possible (e.g. `credit_ledger`
  is an event log, never mutated) to keep an auditable billing/usage trail.
- **Encryption:** OAuth refresh tokens encrypted at rest (KMS/app-level), never logged.
- **Retention:** a scheduled cleanup expires `jobs.source_storage_key` after render and `clips`
  per plan retention — enforced by storage lifecycle rules + a reconciler.
