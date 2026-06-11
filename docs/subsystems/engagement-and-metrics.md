# Engagement and metrics

Scope: background jobs that poll X for posted tweet metrics and placeholder account metrics. Parent: [../PROJECT.md](../PROJECT.md).

## Key paths

| Path | Role |
|------|------|
| `SocialMediaAutonomousAgents/backend/app/jobs/engagement_job.py` | Each hour at `:05` poll |
| `SocialMediaAutonomousAgents/backend/app/jobs/metrics_job.py` | Each hour at `:10` placeholder |
| `SocialMediaAutonomousAgents/backend/app/services/post_registry.py` | `TrackedPostRepository` |
| `SocialMediaAutonomousAgents/backend/app/services/twitter_service.py` | `get_tweet_metrics` |
| `SocialMediaAutonomousAgents/backend/app/models/tracked_post.py` | Stored metrics + `PostCreationMetrics` |
| `SocialMediaAutonomousAgents/backend/app/models/metrics.py` | Account metrics model (future) |

## Engagement job (`:05`)

For each **active** account:

1. Lists tweet ids from `TrackedPosts`
2. Calls `TwitterService.get_tweet_metrics(account_id, tweet_id)` for each
3. Updates `TrackedPostRepository.update_metrics`
4. If account `last_post_id` is tracked, refreshes `account.last_post_views` on the account document

Returns per-account status: `ok`, `no_tracked_posts`, or `partial_or_failed`.

Tracked posts are **created** in `post_tick.finalize_post` when a tick successfully posts.

## Metrics job (`:10`)

Placeholder: counts active accounts and logs. Does not yet write `AccountMetrics` batches or feed dashboard `avg_engagement`.

## Tracked post document

Stores public metrics (likes, replies, retweets, impressions), optional enrichment (permalink, media types), and optional `creation_metrics` from the posting tick (regeneration round, source reference id, pull counts).

## API exposure

- **Analytics routes** (primary for dashboard): `GET /api/accounts/{id}/tracked-posts`, `/posts/{tweet_id}`, `/posts/{tweet_id}/snapshots`, `/account-metrics` — see [api-and-dashboard](api-and-dashboard.md)
- Fleet overview still uses `GET /api/dashboard` (`avg_engagement: 0.0` placeholder) and account summaries with `recent_post.views` from `last_post_views`

Dashboard pages: Posts explorer, post detail engagement curves ([frontend-dashboard](frontend-dashboard.md)).

## Related docs

- Scheduler timing: [entry-and-runtime](entry-and-runtime.md)
- X metrics API: [social-x-integration](social-x-integration.md)
- Storage: [persistence-ravendb](persistence-ravendb.md)
- Post registration: [interval-orchestration](interval-orchestration.md)
