# Social / X integration

Scope: unified social layer and per-account X access via Tweepy. Parent: [../PROJECT.md](../PROJECT.md).

## Key paths

| Path | Role |
|------|------|
| `SocialMediaAutonomousAgents/backend/app/social/service.py` | `SocialMediaService` facade by platform |
| `SocialMediaAutonomousAgents/backend/app/social/implementations/x_client.py` | `XTwitterClient` (Tweepy v2 + v1.1) |
| `SocialMediaAutonomousAgents/backend/app/social/protocol.py` | `SocialMediaClient` interface |
| `SocialMediaAutonomousAgents/backend/app/social/credentials.py` | OAuth1 / OAuth2 credential types |
| `SocialMediaAutonomousAgents/backend/app/social/dtos.py` | `AccountData`, `PostData`, `CreatedPost`, trends |
| `SocialMediaAutonomousAgents/backend/app/social/tweet_enrichment.py` | Media URLs, URL filtering, enrichment |
| `SocialMediaAutonomousAgents/backend/app/social/reference_rows.py` | Row normalization for references |
| `SocialMediaAutonomousAgents/backend/app/services/twitter_service.py` | Account-scoped decrypt + delegate to social layer |

## Auth per account

`TwitterService` decrypts credentials from the account document (requires `ENCRYPTION_KEY`):

| Priority | Fields | Client |
|----------|--------|--------|
| OAuth 2.0 user | `twitter_oauth2_access_token_enc` (+ optional refresh) | Bearer token on Tweepy `Client` |
| OAuth 1.0a | Four encrypted OAuth1 fields | Consumer + user token pair |

OAuth2 wins when present and decryptable. Missing/wrong key yields skip errors in posting and API health checks.

## X API surfaces used

| Operation | Client method | Callers |
|-----------|---------------|---------|
| Post tweet | `create_post(text)` | Post tick, `/accounts/{id}/test` |
| User profile | `get_account_data` | Tick bundle, health verify |
| Tweet metrics | `get_post_data` | Engagement job, tick bundle |
| Following home timeline | `get_following_timeline_tweets` | Reference ingestion |
| Trends | `get_trends` (personalized then WOEID fallback) | `TickDataService.compile_niche_discourse` (context; not main reference source) |
| Recent search | `search_recent_tweets` | Available; gated by `TREND_TWEET_SEARCH_ENABLED` (default off) |

Timeline fetch uses v2 fields/expansions for text, metrics, media, entities. Rate limiting: `wait_on_rate_limit=True` on Tweepy clients.

## Error handling

`social/exceptions.SocialPlatformError` wraps vendor failures. Tick and job code log and continue or skip per account where possible.

## Related docs

- Credential storage: [persistence-ravendb](persistence-ravendb.md)
- Timeline references: [reference-ingestion](reference-ingestion.md)
- Posting: [hourly-orchestration](hourly-orchestration.md)
- Account setup: [ACCOUNT_SETUP](../../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md)
