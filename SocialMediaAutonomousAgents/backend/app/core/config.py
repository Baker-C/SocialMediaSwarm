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
    scheduler_timezone: str = "UTC"
    # Automated posting paused from start hour (inclusive) to end hour (exclusive), e.g. 0–8 = midnight–8 AM
    post_quiet_hours_enabled: bool = True
    post_quiet_hours_start: int = 0
    post_quiet_hours_end: int = 8
    scheduler_misfire_grace_seconds: int = 300
    # When false, this process will not start APScheduler (use on extra uvicorn workers)
    run_scheduler: bool = True
    # When false, skip the scheduled posting job (forced posts via scripts still work)
    hourly_posting_enabled: bool = True
    # Wall-clock interval between scheduled posting ticks (APScheduler)
    post_interval_minutes: int = 18
    # Min minutes between posts per account (scheduled + force); must be < post_interval_minutes
    post_cooldown_minutes: int = 17
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
    # Same pair for all automated accounts; user access/refresh tokens stay per account in RavenDB.
    twitter_oauth2_client_id: str = ""
    twitter_oauth2_client_secret: str = ""
    # Trends: try X personalized trends for the authenticated user before WOEID fallback
    trends_prefer_personalized: bool = True
    trends_fallback_woeid: int = 1
    # Print/log JSON payloads between hourly pipeline steps
    tick_pipeline_trace: bool = True
    # External reference tweets (Stream A: search, Stream B: following timeline)
    trend_tweet_search_enabled: bool = False
    following_feed_enabled: bool = True
    trend_search_max_results: int = 100
    following_timeline_max_results: int = 100
    reference_tweet_cache_minutes: int = 45
    following_feed_filter_by_trend: bool = True


settings = Settings()
