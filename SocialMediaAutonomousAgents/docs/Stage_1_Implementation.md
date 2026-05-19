# Stage 1 Implementation

Operator and developer reference for the **implemented** Stage 1 hourly posting stack. Product requirements live in [`ImplementationSpecifications/STAGE_1_Implementation_Specifications.md`](../../ImplementationSpecifications/STAGE_1_Implementation_Specifications.md).

## Overview

Stage 1 targets **five active accounts** posting **once per hour**, collecting engagement data without pattern/tone optimization. The backend uses:

- **FastAPI** + **APScheduler** for scheduling
- **RavenDB** for account and tracked-post state
- **Clinic Connect–style separation**: orchestration (gateway) → `hourly_crew` (LLM runtime) → services (data)
- **Prompt files** under `app/hourly_crew/prompts/` (not inline in Python)

## Architecture

| Surface | Location | Role |
|---------|----------|------|
| Gateway / scheduler | `app/jobs/hourly_job.py`, `app/hourly/runner.py`, `app/hourly/orchestration/` | Cron entry, idempotency, safety, post to X |
| Agent runtime | `app/hourly_crew/` | Generate + rank candidates via prompts + Claude |
| Persistence | `app/services/account_repository.py`, `post_registry.py` | Accounts, `last_post_slot`, tracked tweets |

```
backend/app/
├── jobs/hourly_job.py
├── hourly/
│   ├── schemas.py          # TickInput, TickOutput, TickBrief
│   ├── runner.py           # run_hourly_tick, run_account_pipeline
│   └── orchestration/
│       ├── pre_tick.py
│       ├── post_tick.py
│       └── safety_filter.py
├── hourly_crew/
│   ├── prompt_loader.py
│   ├── llm_pipeline.py
│   ├── runner.py
│   ├── crew.py
│   ├── prompts/            # .md templates
│   ├── agents/
│   ├── tasks/
│   └── tools/
└── agents/orchestrator.py  # stable entry: Orchestrator.run_tick()
```

## Hourly schedule

| Minute | Job | Module |
|--------|-----|--------|
| `:00` | Posting tick | `jobs/hourly_job.py` → `Orchestrator.run_tick()` |
| `:05` | Engagement poll | `jobs/engagement_job.py` |
| `:10` | Metrics placeholder | `jobs/metrics_job.py` |

Timezone: `SCHEDULER_TIMEZONE` (default UTC). Slot key: `YYYY-MM-DD-H` in that timezone.

## Posting pipeline (per account)

1. **pre_tick** — Load active accounts (or force IDs). Skip if `last_post_slot` equals current slot (scheduled mode only).
2. **Data fetch (2a)** — `TickDataService`: profile + **tracked post** metrics from X (`post_engagements`) for engagement/history only — **not** used as LLM reference candidates.
3. **Timeline references (2a′)** — `compile_timeline_reference_tweets`: up to **100** tweets from the authenticated user’s **following home timeline** only. Own tweets filtered out. URL-bearing rows kept (`filter_rows_with_urls`). In-memory cache per account/slot (`REFERENCE_TWEET_CACHE_MINUTES`).
4. **Reference selection (2a½)** — [`tweet_topic_preanalysis.py`](backend/app/hourly/tweet_topic_preanalysis.py): pick the timeline tweet with highest engagement score. **Skip tick** when no URL-bearing timeline tweets (`no_reference_with_urls`) — no LLM compose or post.
5. **Compose** — [`compose_timeline_post.py`](backend/app/hourly/compose_timeline_post.py): LLM paraphrase into `{emoji} {headline}\n\n{story}\n\n{source_permalink}` (≤280 chars).
6. **Safety** — `SafetyGuardian.evaluate` on the composed body; up to `MAX_REGENERATION_ROUNDS` retries.
7. **post_tick** — plain-text `post_tweet` (source link in body; no quote posts).

Force mode: `Orchestrator.run_tick(mode="force", account_ids=[...])` bypasses slot idempotency.

## Prompts

Edit files under `backend/app/hourly_crew/prompts/`:

| File | Use |
|------|-----|
| `tasks/generate_candidates.system.md` | JSON posts array contract |
| `tasks/generate_candidates.user.md` | Niche + context (`{niche}`, `{context}`, `{account_system_prompt_section}`) |
| `tasks/rank_candidates.system.md` | Ranking JSON contract |
| `tasks/rank_candidates.user.md` | Context + candidates |
| `agents/content_creator.role.md` | Crew agent role (optional `crew.py` path) |
| `tasks/compose_timeline_post.system.md` | Emoji + headline + story JSON for timeline reposts |
| `tasks/compose_timeline_post.user.md` | Source tweet + niche |
| `tasks/analyze_tick.system.md` | Reserved for future 2c analysis |

Load via `prompt_loader.load()` / `load_template()`. Per-account overrides: `AccountDocument.system_prompt` in RavenDB.

## Configuration

| Variable | Purpose |
|----------|---------|
| `SCHEDULER_TIMEZONE` | Hourly slot boundary |
| `ANTHROPIC_API_KEY` | Claude for generate/rank (fallback heuristics if unset) |
| `CLAUDE_MODEL` | Model id |
| `RAVENDB_*` | Account storage |
| X / Buffer credentials | Per-account encrypted fields on `Accounts` |

## Running locally

```bash
cd backend
.\venv\Scripts\activate   # Windows
uvicorn app.main:app --reload
```

APScheduler starts with the app (`app/main.py`). Force a tick for one account:

```bash
python scripts/create_forced_post.py <account_id>
```

## Data model (Stage 1)

| Collection / doc | Status |
|------------------|--------|
| `Accounts` | Active — slot idempotency, followers, last post fields |
| Tracked posts registry (`TrackedPosts`) | Active — engagement job + tick metrics; optional `creation_metrics` on publish |
| `PulledTweets` | Active — external reference tweets deduped by X `tweet_id`; `duplicate_fetch_count`, `pulled_for_account_ids` |
| Tick snapshot / analysis | Stub (`save_and_analyze_stub`) |
| `Posts`, `EngagementSnapshot`, `AccountMetrics` | Per STAGE_1 spec — expand as collections are wired |

### PulledTweets

- **When written:** each hourly/forced tick during `compile_timeline_reference_tweets` (before selection), including in-memory cache hits.
- **Pull cap:** following timeline requests up to **100** tweets (X API max per call).
- **Doc id:** `pulledtweets/{tweet_id}` (global dedup).
- **API:** `GET /api/accounts/{account_id}/pulled-tweets?limit=100&since=<iso>` — read corpus for an account (does not trigger a live X pull).
- **Media / embed fields** (from X `attachments` + `entities` when API tier allows):
  - `tweet_permalink` — `https://x.com/i/status/{tweet_id}` (usable as text embed link)
  - `media_types`, `primary_media_type` — `photo`, `video`, `animated_gif`
  - `media[]` — native attachment metadata (`type`, `url`, `preview_image_url`; CDN URLs are not embed links)
  - `embed_urls` — permalink plus expanded external URLs (excludes `pbs.twimg.com` / `video.twimg.com`)
  - `url_entities[]` — structured link rows from `entities.urls`

**TrackedPosts** receive the same enrichment fields after publish via `get_tweet` + `update_enrichment`.

**Recommended RavenDB Studio indexes:** `PulledTweets/ByAccount` (multi-map on `pulled_for_account_ids`), `ByLastPulledAt`, `ByDuplicateFetchCount`, `BySource`, `ByAuthorId`.

## Out of scope (Stage 2+)

- Pattern discovery and `pattern_id` assignment
- `AccountTonePreferences` optimization
- Full `analyze_tick` LLM step and snapshot persistence
- `:10` metrics batch (placeholder only)
- CrewAI `kickoff` with `use_crew=True` (optional; default uses `llm_pipeline` for reliable JSON)

## Verification

- Logs: `hourly_job slot=... accounts=...`
- Account doc: `last_post_slot` matches current hour after a successful post
- Repeat tick same hour → `skipped: already_posted_this_hour`
- Tests: `pytest tests/test_orchestrator.py`

## Entry points

| Call | Use |
|------|-----|
| `Orchestrator().run_tick()` | Scheduled hourly job |
| `Orchestrator().run_tick(mode="force", account_ids=[...])` | Manual / script override |
