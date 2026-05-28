# Backend Architecture

This document describes the current architecture of the **Social Media Autonomous Agents** backend: a FastAPI service that runs scheduled X (Twitter) posting for multiple accounts, persists state in RavenDB, and uses Claude for compose and safety checks.

**Related docs:** [ACCOUNT_SETUP.md](./ACCOUNT_SETUP.md) for provisioning accounts and credentials.

---

## 1. System overview

The backend is a single Python process that:

1. Serves a **read-mostly HTTP API** for a dashboard (accounts, status, pulled tweets).
2. Runs an in-process **APScheduler** for automated posting and engagement polling.
3. Stores per-account configuration and posting history in **RavenDB**.
4. Talks to **X API v2** (via Tweepy) and **Anthropic Claude** for generation and niche checks.

There is **no human review queue**. Reference tweets are fetched automatically, ranked, composed, safety-checked, and posted.

```mermaid
flowchart TB
    subgraph clients [Clients]
        FE[Frontend dashboard]
        CLI[CLI scripts]
    end

    subgraph backend [Backend process]
        API[FastAPI /api]
        SCHED[APScheduler]
        ORCH[Orchestrator]
        PIPE[Hourly pipeline]
    end

    subgraph external [External services]
        RDB[(RavenDB)]
        X[X API v2 / Tweepy]
        CLAUDE[Anthropic Claude]
    end

    FE --> API
    CLI --> ORCH
    CLI --> RDB
    API --> RDB
    SCHED --> ORCH
    ORCH --> PIPE
    PIPE --> RDB
    PIPE --> X
    PIPE --> CLAUDE
    API --> X
```

---

## 2. Layered architecture

Code is organized in layers. Dependencies generally flow **downward** (API and jobs call services; services call infrastructure and social clients).

```mermaid
flowchart TB
    subgraph entry [Entry points]
        MAIN[app/main.py]
        JOBS[app/jobs/*]
        SCRIPTS[scripts/*]
    end

    subgraph api [API layer]
        ROUTES[app/api/routes/*]
    end

    subgraph orchestration [Orchestration]
        ORCH[Orchestrator]
        RUNNER[hourly/runner.py]
        ORCH_SUB[hourly/orchestration/*]
    end

    subgraph agents [Agents and compose]
        COMPOSE[compose_timeline_post]
        GUARD[SafetyGuardian]
        PREAN[tweet_topic_preanalysis]
    end

    subgraph services [Services]
        TW[TwitterService]
        TDS[TickDataService]
        REPOS[Repositories]
        RDBSVC[RavenDBService]
    end

    subgraph social [Social abstraction]
        SMS[SocialMediaService]
        XCLIENT[XTwitterClient]
    end

    subgraph infra [Infrastructure]
        RDBHTTP[RavenDBHttpClient]
        CLAUDE[ClaudeClient]
        LOCK[scheduler_lock / post_lock]
    end

    MAIN --> ROUTES
    MAIN --> JOBS
    JOBS --> ORCH
    SCRIPTS --> ORCH
    ROUTES --> REPOS
    ROUTES --> TW
    ROUTES --> RDBSVC
    ORCH --> RUNNER
    RUNNER --> TDS
    RUNNER --> COMPOSE
    RUNNER --> GUARD
    RUNNER --> PREAN
    RUNNER --> ORCH_SUB
    ORCH --> TW
    ORCH --> REPOS
    TDS --> TW
    TDS --> REPOS
    TW --> SMS
    SMS --> XCLIENT
    REPOS --> RDBHTTP
    COMPOSE --> CLAUDE
    GUARD --> CLAUDE
```

| Layer | Path | Responsibility |
|-------|------|----------------|
| Entry | `app/main.py`, `app/jobs/`, `scripts/` | Process bootstrap, HTTP, cron |
| API | `app/api/routes/` | REST endpoints for dashboard |
| Orchestration | `app/agents/orchestrator.py`, `app/hourly/` | Per-tick and per-account pipeline |
| Agents | `app/agents/`, `app/hourly/compose_timeline_post.py` | LLM compose and safety |
| Services | `app/services/` | Business logic, RavenDB access |
| Social | `app/social/` | Platform-agnostic facade; X implementation |
| Infrastructure | `app/infrastructure/` | RavenDB HTTP, Claude, file locks |
| Models | `app/models/` | Pydantic document shapes |
| Config | `app/core/config.py` | Environment-driven settings |

---

## 3. Process lifecycle and scheduler

On startup, FastAPI runs a **lifespan** hook that optionally starts APScheduler. Only one worker should hold the scheduler lock (`RUN_SCHEDULER=true`).

```mermaid
sequenceDiagram
    participant Uvicorn
    participant Main as main.py lifespan
    participant Lock as scheduler_lock
    participant Sched as AsyncIOScheduler
    participant Jobs as hourly / engagement / metrics

    Uvicorn->>Main: startup
    Main->>Lock: try_acquire_scheduler_lock()
    alt lock acquired and RUN_SCHEDULER
        Main->>Sched: start()
        Sched-->>Jobs: cron / interval triggers
    else no lock or RUN_SCHEDULER=false
        Main->>Main: log disabled
    end
    Note over Uvicorn,Jobs: HTTP serves regardless of scheduler
    Uvicorn->>Main: shutdown
    Main->>Sched: shutdown()
    Main->>Lock: release_scheduler_lock()
```

### Scheduled jobs

| Job ID | Callable | Schedule | Purpose |
|--------|----------|----------|---------|
| `scheduled_posting` | `run_hourly_job` | Every `POST_INTERVAL_MINUTES` (default 18), clock-aligned | Run posting tick for all active accounts |
| `engagement_poll` | `run_engagement_job` | `:05` each hour | Refresh metrics on tracked posts |
| `metrics_batch` | `run_metrics_job` | `:10` each hour | Placeholder / future batch metrics |

Posting is skipped when `HOURLY_POSTING_ENABLED=false` or during **quiet hours** (`post_quiet_hours_*` in `SCHEDULER_TIMEZONE`).

```mermaid
gantt
    title Example hour (POST_INTERVAL_MINUTES=18, UTC)
    dateFormat HH:mm
    axisFormat %H:%M

    section Posting
    Tick at :00     :00, 1m
    Tick at :18     :18, 1m
    Tick at :36     :36, 1m

    section Other jobs
    Engagement :05, 2m
    Metrics    :10, 2m
```

---

## 4. Component wiring

The **Orchestrator** is the composition root for automated posting. It constructs repositories, `TwitterService`, `TickDataService`, `SafetyGuardian`, and delegates to `run_hourly_tick`.

```mermaid
classDiagram
    class Orchestrator {
        +AccountRepository repo
        +TwitterService twitter
        +ContentCreator creator
        +SafetyGuardian guardian
        +TrackedPostRepository post_registry
        +PulledTweetRepository pulled_tweets
        +run_tick(mode, account_ids, bypass_post_cooldown)
    }

    class TickDataService {
        +compile_account_bundle()
        +compile_niche_discourse()
        +compile_timeline_reference_tweets()
        +merge_reference_pool()
    }

    class TwitterService {
        +post_tweet()
        +get_following_feed()
        +get_trends()
        +get_tweet_metrics()
        +get_account_data()
    }

    class SocialMediaService {
        +get_following_timeline_tweets()
        +create_post()
        +get_trends()
    }

    class XTwitterClient {
        +get_home_timeline()
        +search_recent_tweets()
        +create_tweet()
        +get_trends()
    }

    Orchestrator --> TickDataService
    Orchestrator --> TwitterService
    Orchestrator --> SafetyGuardian
    TickDataService --> TwitterService
    TwitterService --> SocialMediaService
    SocialMediaService --> XTwitterClient
```

**Note:** `ContentCreator` is wired into `TickContext` but the **active** posting path uses `compose_formatted_post` directly, not the CrewAI `hourly_crew` pipeline.

---

## 5. Data layer (RavenDB)

Persistence uses **RavenDB** over HTTP (`RavenDBHttpClient`). Database name defaults to `SocialMediaSwarm`.

```mermaid
erDiagram
    Accounts ||--o{ TrackedPosts : publishes
    Accounts ||--o{ PulledTweets : "references pulled by"
    Accounts ||--o| PostLocks : "may hold"

    Accounts {
        string account_id PK
        string niche
        string status
        string twitter_handle
        string system_prompt
        string personality
        list copied_reference_tweet_ids
        string last_post_slot
        string last_post_id
        int posts_total
        blob twitter_oauth2_access_token_enc
        blob twitter_api_key_enc
    }

    TrackedPosts {
        string id PK
        string account_id
        string tweet_id
        datetime posted_at
        object metrics
    }

    PulledTweets {
        string tweet_id PK
        list account_ids
        string source
        int fetch_count
        object enrichment
    }

    PostLocks {
        string account_id PK
        string holder
        datetime until
    }
```

### Document ID conventions

| Collection | ID pattern | Repository |
|------------|------------|------------|
| `Accounts` | `accounts/{account_id}` | `AccountRepository` |
| `TrackedPosts` | `trackedposts/{account_id}-{tweet_id}` | `TrackedPostRepository` |
| `PulledTweets` | `pulledtweets/{tweet_id}` | `PulledTweetRepository` |
| `PostLocks` | `post-locks/{account_id}` | `PostLockRepository` |

### Credential storage

Per-account X tokens are stored **encrypted** (Fernet) on `AccountDocument`:

- **OAuth 2.0 user** (preferred): `twitter_oauth2_access_token_enc`, optional refresh token.
- **OAuth 1.0a**: consumer key/secret + access token/secret (four encrypted fields).

`TwitterService._x_credentials()` decrypts with `ENCRYPTION_KEY`. OAuth2 wins when present and decryptable.

---

## 6. X (Twitter) integration

All live X traffic goes through a thin stack. There is **no scraping**; only official API via Tweepy.

```mermaid
flowchart LR
    TS[TwitterService]
    SMS[SocialMediaService]
    XC[XTwitterClient]
    TW[Tweepy Client]

    TS -->|decrypt creds| SMS
    SMS -->|SocialPlatform.X| XC
    XC --> TW
```

### Endpoints used (by feature)

| Feature | Tweepy / X API | Called from |
|---------|----------------|-------------|
| Following timeline (reference tweets) | `get_home_timeline` | `get_following_timeline_tweets` → `TickDataService.compile_timeline_reference_tweets` |
| Post publish | `create_tweet` | `finalize_post` → `TwitterService.post_tweet` |
| Tweet metrics | `get_tweet` | Engagement job, post-registry priming |
| Account profile | `get_me` / `get_user` | `compile_account_bundle`, health checks |
| Trends | v1.1 `get_place_trends` (OAuth1) or v2 `/2/trends/by/woeid/{id}` / personalized (OAuth2) | `compile_niche_discourse` (crew tools); **not** main posting path |
| Recent search | `search_recent_tweets` | Implemented; gated by `TREND_TWEET_SEARCH_ENABLED` (default **off**, not wired into posting runner) |

```mermaid
sequenceDiagram
    participant Pipe as Posting pipeline
    participant TDS as TickDataService
    participant TW as TwitterService
    participant X as X API

    Pipe->>TDS: compile_timeline_reference_tweets(account, slot)
    alt cache miss
        TDS->>TW: get_following_feed(account_id)
        TW->>X: get_home_timeline(max_results, exclude retweets)
        X-->>TW: tweets + metrics
        TW-->>TDS: reference rows
        TDS->>TDS: filter own tweets, record_pulls → PulledTweets
        TDS->>TDS: set in-memory cache (REFERENCE_TWEET_CACHE_MINUTES)
    else cache hit
        TDS-->>Pipe: cached rows (still record_pulls)
    end
```

---

## 7. Posting pipeline (primary flow)

The production path is **timeline reference → compose → safety → publish**. One successful post per account per tick (when guards allow).

### 7.1 Tick-level flow

```mermaid
flowchart TD
    START([run_hourly_job / create_forced_post.py])
    START --> RT[Orchestrator.run_tick]
    RT --> BTC[build_tick_context]
    BTC --> P1[phase1_global_setup: list active accounts]

    P1 --> LOOP{For each account}
    LOOP --> RAP[run_account_pipeline]

    RAP --> SKIP1{should_skip_account?}
    SKIP1 -->|yes| END_SKIP[return skipped]
    SKIP1 -->|no| SKIP2{scheduled + same slot?}
    SKIP2 -->|yes| END_SKIP
    SKIP2 -->|no| GUARD[try_begin_post: cooldown + locks]
    GUARD -->|blocked| END_SKIP
    GUARD -->|ok| SLOT[try_reserve_hourly_slot]
    SLOT -->|blocked| END_SKIP
    SLOT -->|ok| BUNDLE[compile_account_bundle]
    BUNDLE --> REFS[compile_timeline_reference_tweets]
    REFS --> POOL[merge_reference_pool + filter_rows_with_urls]
    POOL --> EMPTY{pool empty?}
    EMPTY -->|yes| END_SKIP
    EMPTY -->|no| RANK[rank_timeline_references]
    RANK --> LOOPREF{For each ranked reference}

    LOOPREF --> COMPOSE[compose_formatted_post]
    COMPOSE --> SAFE[SafetyGuardian.evaluate]
    SAFE -->|reject niche| LOOPREF
    SAFE -->|reject other| REGEN{regen rounds left?}
    REGEN -->|yes| COMPOSE
    REGEN -->|no| LOOPREF
    SAFE -->|approve| POST[finalize_post → post_tweet]
    POST --> DONE([tweet published])
    LOOPREF -->|exhausted| FAIL[all references failed]

    END_SKIP --> LOOP
    FAIL --> LOOP
    DONE --> LOOP
```

### 7.2 Guards and idempotency

```mermaid
flowchart LR
    subgraph pre [Pre-post guards]
        A[Inactive account]
        B[already_posted_this_hour]
        C[posted_within_cooldown]
        D[account_post_lock_held]
        E[ravendb PostLocks]
        F[slot_lock_held]
    end

    subgraph mode [Mode behavior]
        M1[scheduled: enforce last_post_slot]
        M2[force: optional account_ids, looser slot rules]
    end

    pre --> SKIP[Skip account this tick]
    mode --> SLOT[Slot key YYYY-MM-DD-HH-MM bucket]
```

**Slot key** (`AccountRepository.current_post_slot_key()`): time bucket derived from `POST_INTERVAL_MINUTES` and `SCHEDULER_TIMEZONE`.

### 7.3 Compose and safety

```mermaid
sequenceDiagram
    participant Runner
    participant Compose as compose_formatted_post
    participant Claude
    participant Guard as SafetyGuardian
    participant X as X API

    Runner->>Compose: winner tweet, niche, account prompts
    Compose->>Claude: paraphrase to ≤280 chars (opinion + quip + embed URL)
    Claude-->>Compose: JSON body
    Compose-->>Runner: formatted text

    Runner->>Guard: evaluate(text, niche, ...)
    alt length / prompt-leak fail
        Guard-->>Runner: reject → retry compose (same reference)
    else niche_mismatch
        Guard-->>Runner: reject → try next reference
    else approved
        Guard-->>Runner: approve
        Runner->>X: create_tweet
    end
```

Prompts live under `app/hourly_crew/prompts/tasks/` (e.g. `compose_timeline_post.*.md`, `niche_fit_check.*.md`) and are loaded via `prompt_loader`.

### 7.4 Publish and side effects

On success, `finalize_post` (`hourly/orchestration/post_tick.py`):

1. `TwitterService.post_tweet`
2. Updates `AccountDocument` (`last_post_*`, `posts_total`, `copied_reference_tweet_ids`)
3. `TrackedPostRepository.record_post` + optional immediate metrics/enrichment
4. Releases slot reservation and post guard

---

## 8. Reference tweet ingestion

Reference tweets are **not** human-reviewed. They are pulled from the account’s **following home timeline**.

```mermaid
flowchart TD
    A[compile_timeline_reference_tweets] --> B{In-memory cache hit?}
    B -->|yes| C[Return cached rows]
    B -->|no| D{FOLLOWING_FEED_ENABLED?}
    D -->|no| E[reference_errors: disabled]
    D -->|yes| F[get_following_feed → get_home_timeline]
    F --> G[filter_out_own_tweets]
    G --> H[PulledTweetRepository.record_pulls]
    H --> I[Cache payload for slot TTL]
    C --> J[merge_reference_pool]
    I --> J
    J --> K[filter_rows_with_urls]
    K --> L[Exclude copied_reference_tweet_ids]
    L --> M[rank_timeline_references by engagement score]
    M --> N[Try top N references in compose/safety loop]
```

**Ranking** (`tweet_topic_preanalysis.rank_timeline_references`): weighted likes, replies, retweets, impressions; skips already-copied source tweet IDs.

---

## 9. Engagement polling

Separate from posting: refreshes metrics for tweets the system already published.

```mermaid
flowchart TD
    EJ[run_engagement_job at :05] --> LA[list_active accounts]
    LA --> ACC{For each account}
    ACC --> IDS[TrackedPostRepository.list_tweet_ids]
    IDS --> POLL[For each tweet_id: get_tweet_metrics]
    POLL --> UPD[TrackedPostRepository.update_metrics]
    ACC --> LP{last_post_id in tracked set?}
    LP -->|yes| LV[Refresh account.last_post_views]
```

---

## 10. HTTP API surface

Routers are mounted under `/api` in `app/main.py`. CORS allows local frontend origins.

```mermaid
flowchart LR
    subgraph health [Health]
        H1[GET /api/health]
    end

    subgraph accounts [Accounts]
        A1[GET /accounts]
        A2[GET /accounts/id]
        A3[GET /accounts/id/edit]
        A4[PATCH /accounts/id]
        A5[PATCH /accounts/id/archive]
        A6[GET /accounts/id/pulled-tweets]
        A7[GET /accounts/id/status]
        A8[POST /accounts/id/test]
    end

    subgraph read [Read models]
        D1[GET /dashboard]
        P1[GET /posts]
        P2[GET /patterns]
        M1[GET /metrics/account_id]
    end
```

| Endpoint | Behavior |
|----------|----------|
| `GET /accounts` | List accounts (secrets redacted via `RavenDBService`) |
| `PATCH /accounts/{id}` | Update niche, personality, prompts (`AccountUpdateService`) |
| `GET /pulled-tweets` | Historical reference pulls from RavenDB (not live X pull) |
| `POST /test` | Live test post via `TwitterService.post_tweet` |
| `GET /dashboard` | Aggregate counts for UI |

**Account creation is not exposed over HTTP.** Use CLI: `scripts/add_account.py` or `account_setup_wizard.py`.

---

## 11. Configuration

Settings are loaded from `.env` via `app/core/config.py` (`pydantic-settings`).

```mermaid
mindmap
  root((Settings))
    RavenDB
      RAVENDB_URL
      RAVENDB_DB
      certs
    Security
      ENCRYPTION_KEY
      OAuth2 app id/secret
    Scheduler
      RUN_SCHEDULER
      POST_INTERVAL_MINUTES
      POST_COOLDOWN_MINUTES
      quiet hours
      SCHEDULER_POST_MODE
    Pipeline
      MAX_REGENERATION_ROUNDS
      MAX_REFERENCE_FALLBACK_ATTEMPTS
      FOLLOWING_FEED_ENABLED
      REFERENCE_TWEET_CACHE_MINUTES
    LLM
      ANTHROPIC_API_KEY
      CLAUDE_MODEL
```

See `.env.example` for the full list.

---

## 12. CLI and manual entry points

```mermaid
flowchart LR
    subgraph scripts [scripts/]
        ADD[add_account.py]
        FORCE[create_forced_post.py]
        TEST[test_twitter_credentials.py]
        WIZ[account_setup_wizard.py]
    end

    ADD --> CAJ[run_create_account_job]
    CAJ --> AR[AccountRepository.upsert_credentials]

    FORCE --> ORCH[Orchestrator.run_tick mode=force]
    TEST --> TW[TwitterService.post_tweet]

    ORCH --> PIPE[hourly pipeline]
```

| Script | Purpose |
|--------|---------|
| `add_account.py` | Create account + encrypt credentials in RavenDB |
| `create_forced_post.py` | Run one posting tick (bypasses some slot rules) |
| `test_twitter_credentials.py` | Verify X connectivity per account |

---

## 13. Legacy and alternate paths

Two compose architectures exist; only one is used by `hourly/runner.py` today.

```mermaid
flowchart TB
    subgraph active [Active path]
        R1[runner.run_account_pipeline]
        R2[compose_formatted_post]
        R3[SafetyGuardian]
        R1 --> R2 --> R3
    end

    subgraph legacy [Legacy / alternate - hourly_crew]
        C1[kickoff_content_pipeline / llm_pipeline]
        C2[generate_candidates + rank_candidates]
        C3[CrewAI agents + tools]
        C1 --> C2 --> C3
    end

    subgraph shared [Shared]
        P[prompts under hourly_crew/prompts]
        T[TickDataService tools]
    end

    R2 -.-> P
    R3 -.-> P
    C1 -.-> T
```

| Path | Status |
|------|--------|
| Timeline compose + `SafetyGuardian` | **Production** |
| `hourly_crew` CrewAI generate/rank | Implemented, **not** called from `run_account_pipeline` |
| Trend search for references | `search_recent_tweets` implemented; `TREND_TWEET_SEARCH_ENABLED=false`, not in runner |
| Buffer API | Optional scripts only; core pipeline posts via Tweepy |

---

## 14. Directory reference

```
backend/
├── app/
│   ├── main.py                 # FastAPI + APScheduler lifespan
│   ├── api/routes/             # REST handlers
│   ├── agents/                 # Orchestrator, SafetyGuardian, ContentCreator
│   ├── core/config.py          # Settings
│   ├── hourly/                 # Posting tick (runner, compose, orchestration)
│   ├── hourly_crew/            # Prompts, CrewAI, LLM tools (shared + legacy)
│   ├── infrastructure/         # RavenDB HTTP, Claude, locks
│   ├── jobs/                   # Scheduler callables
│   ├── models/                 # Pydantic documents
│   ├── services/               # Repositories, TwitterService, TickDataService
│   ├── social/                 # X client, DTOs, enrichment
│   └── utils/                  # encryption
├── scripts/                    # CLI entry points
├── tests/                      # unit + integration
└── docs/
    ├── ARCHITECTURE.md         # this file
    └── ACCOUNT_SETUP.md
```

---

## 15. Operational notes

- **Single scheduler:** File lock `%TEMP%/sma_apscheduler.lock` prevents duplicate cron in multi-worker deployments; set `RUN_SCHEDULER=false` on extra workers.
- **Tests:** X client and service layers are covered with **mocked Tweepy**; passing tests do not prove live API tier/access.
- **Observability:** Set `TICK_PIPELINE_TRACE=true` for structured step logs between pipeline phases (`pipeline_trace.trace_step`).

---

*Last updated to reflect the codebase as of the automated posting pipeline (timeline references, `compose_formatted_post`, APScheduler, RavenDB collections above).*
