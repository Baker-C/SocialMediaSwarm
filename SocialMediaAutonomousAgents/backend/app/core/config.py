from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    ravendb_url: str = "https://localhost"
    ravendb_db: str = "SocialMediaSwarm"
    ravendb_verify_ssl: bool = False
    ravendb_client_cert: str = ""
    ravendb_client_key: str = ""
    log_level: str = "INFO"
    environment: str = "development"
    encryption_key: str = ""
    # Dashboard login gate. DASHBOARD_PASSWORD is the plaintext password checked at /api/auth/login.
    # When empty, auth is disabled (all routes open) — set it before exposing the backend publicly.
    dashboard_password: str = ""
    # Secret used to sign session tokens. Falls back to encryption_key when empty.
    dashboard_session_secret: str = ""
    # How long a login stays valid on the user's device.
    dashboard_session_days: int = 30
    # Comma-separated browser origins allowed by CORS (e.g. https://your-app.vercel.app).
    # localhost dev origins are always allowed in addition to these.
    allowed_origins: str = ""
    scheduler_timezone: str = "UTC"
    # Automated posting paused from start hour (inclusive) to end hour (exclusive), e.g. 0–8 = midnight–8 AM
    post_quiet_hours_enabled: bool = True
    post_quiet_hours_start: int = 0
    post_quiet_hours_end: int = 8
    scheduler_misfire_grace_seconds: int = 300
    # When false, this process will not start APScheduler (use on extra uvicorn workers)
    run_scheduler: bool = True
    # When false, skip the scheduled posting job (forced posts via scripts still work)
    interval_posting_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "interval_posting_enabled",
            "hourly_posting_enabled",
            "INTERVAL_POSTING_ENABLED",
            "HOURLY_POSTING_ENABLED",
        ),
    )
    # Wall-clock interval between scheduled posting ticks (APScheduler)
    post_interval_minutes: int = 30
    # Min minutes between posts per account (scheduled + force); must be < post_interval_minutes
    post_cooldown_minutes: int = 29
    # APScheduler posting tick: "force" matches create_forced_post.py; "scheduled" enforces slot idempotency
    scheduler_post_mode: str = "force"
    # When true, scheduled ticks bypass POST_COOLDOWN_MINUTES (same as --force-now)
    scheduler_bypass_cooldown: bool = True
    # Compose + safety/niche retries per account per tick (0-indexed loop runs this many times)
    max_regeneration_rounds: int = 10
    # Max timeline sources to try when compose/niche rejects (0 = no cap, try full ranked pool)
    max_reference_fallback_attempts: int = 0
    # RavenDB post-locks/{account_id} TTL while a tick is running
    post_lock_ttl_seconds: int = 600
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    # Buffer GraphQL API (Settings → API); Bearer token for posting when integrated
    buffer_api_key: str = ""
    # Default Buffer organization (same for all accounts unless overridden per account)
    buffer_organization_id: str = ""
    # X / Twitter OAuth 2.0 app credentials (developer portal → your app → Keys and tokens).
    # User access/refresh tokens are stored at runtime in OAuthTokens collection (not on account docs).
    twitter_oauth2_client_id: str = ""
    twitter_oauth2_client_secret: str = ""
    twitter_oauth2_redirect_uri: str = "http://localhost:8000/api/oauth/x/callback"
    twitter_oauth2_success_redirect_url: str = "http://localhost:3000"
    # X Developer Portal → Website URL (https:// + TLD required; no :port; not used for redirects)
    twitter_oauth2_website_url: str = "https://example.com"
    twitter_oauth2_scopes: str = "tweet.read tweet.write users.read follows.read offline.access"
    oauth2_session_ttl_seconds: int = 600
    oauth2_refresh_enabled: bool = True
    oauth2_refresh_interval_minutes: int = 30
    oauth2_refresh_batch_size: int = 200
    # Trends: try X personalized trends for the authenticated user before WOEID fallback
    trends_prefer_personalized: bool = True
    trends_fallback_woeid: int = 1
    # Print/log JSON payloads between interval pipeline steps
    tick_pipeline_trace: bool = True
    # External reference tweets (per-niche recent search; following-timeline pull removed)
    trend_search_max_results: int = 100
    following_timeline_max_results: int = 100
    following_feed_filter_by_trend: bool = True
    early_engagement_poll_minutes: int = 15
    early_engagement_window_hours: int = 2
    # Full engagement poll: only refresh posts newer than this (older posts' metrics
    # are effectively final). Batched X lookups are capped at this many ids per call.
    metrics_poll_window_hours: int = 168
    metrics_lookup_batch_size: int = 100
    # NATS JetStream event log for pipeline run tracking (Option B / event-sourced)
    nats_enabled: bool = True
    nats_url: str = "nats://localhost:4222"
    pipeline_events_stream: str = "PIPELINE_EVENTS"
    pipeline_events_max_age_days: int = 30
    # Snapshot full (truncated) artifact bodies in step inputs/outputs; metadata is always captured
    pipeline_capture_payloads: bool = True
    # Per-run hard cost ceiling (USD). 0.0 disables enforcement (the > 0 guard in CostMeter.check_before).
    pipeline_cost_ceiling_usd: float = 3.00
    # Blended LLM price in USD per 1K total tokens — the ONLY price in the system (CC-9; no hardcoded
    # model price). _tokens_to_usd (claude_client.py) multiplies total tokens by this. Tune per model/plan.
    cost_per_1k_tokens_usd: float = 0.009
    # ── Interpreter LEARN / champion-challenger ──
    learn_enabled: bool = True  # master switch for the learn_batch job
    learn_auto_rollback_enabled: bool = True  # the ONE automatic action; off => recommend only
    learn_auto_promote_enabled: bool = False  # DEFAULT manual promote; on => job promotes on "improved"
    learn_propose_challenger_enabled: bool = True  # stage a challenger when none exists
    learn_promote_min_window: int = 10  # min SCORED posts per arm before A/B comparison
    learn_promote_min_improvement: float = 0.02  # challenger must beat champion by this avg reward
    learn_rollback_min_window: int = 10  # min SCORED posts per arm before rollback
    learn_rollback_hard_drop: float = 0.05  # parent must beat current champion by this to roll back
    learn_use_builder_llm: bool = False  # off => deterministic knob-tweak proposer (§5.2)
    challenger_slot_every: int = 4  # run the challenger on 1-in-N posting slots
    # fal.ai media generation (Seedance video + Seedream image). Auth: "Authorization: Key <fal_api_key>".
    fal_api_key: str = ""
    fal_queue_base_url: str = "https://queue.fal.run"
    # Model ids on fal.ai (override here as fal versions them).
    fal_seedream_image_model: str = "fal-ai/bytedance/seedream/v3/text-to-image"
    fal_seedance_t2v_model: str = "fal-ai/bytedance/seedance/v1/pro/text-to-video"
    fal_seedance_i2v_model: str = "fal-ai/bytedance/seedance/v1/pro/image-to-video"
    # Generation defaults. Image uses fal's image_size presets (square_hd, square,
    # portrait_4_3/16_9, landscape_4_3/16_9); video uses 480p/720p/1080p.
    fal_default_image_size: str = "square_hd"
    fal_default_video_resolution: str = "1080p"
    fal_default_video_duration: int = 5
    # Poll backstop for async fal jobs (seconds). Generous: only trips on a wedged/dropped job.
    fal_poll_timeout_seconds: int = 900
    fal_poll_interval_seconds: float = 3.0
    # Local media store: where generated/imported media bytes are saved on this machine.
    media_store_dir: str = "media_store"


settings = Settings()
