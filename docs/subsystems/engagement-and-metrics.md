# Engagement and metrics

Scope: background jobs that poll X for posted tweet metrics and placeholder account metrics. Parent: [../PROJECT.md](../PROJECT.md).

## Key paths

| Path | Role |
|------|------|
| `SocialMediaAutonomousAgents/backend/app/jobs/engagement_job.py` | Hourly `:05` poll |
| `SocialMediaAutonomousAgents/backend/app/jobs/metrics_job.py` | Hourly `:10` placeholder |
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

- Dashboard account cards show `recent_post.views` from account `last_post_views`
- `GET /api/metrics/{account_id}` returns stub zeros
- `GET /api/dashboard` returns `avg_engagement: 0.0`

## Related docs

- Scheduler timing: [entry-and-runtime](entry-and-runtime.md)
- X metrics API: [social-x-integration](social-x-integration.md)
- Storage: [persistence-ravendb](persistence-ravendb.md)
- Post registration: [hourly-orchestration](hourly-orchestration.md)
