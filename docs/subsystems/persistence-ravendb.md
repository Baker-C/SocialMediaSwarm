# Persistence (RavenDB)

Scope: document models, repositories, and credential encryption. Parent: [../PROJECT.md](../PROJECT.md).

## Key paths

| Path | Role |
|------|------|
| `SocialMediaAutonomousAgents/backend/app/infrastructure/ravendb_http.py` | HTTP client, queries, cert auth |
| `SocialMediaAutonomousAgents/backend/app/services/account_repository.py` | Accounts CRUD, slot key, credential upsert |
| `SocialMediaAutonomousAgents/backend/app/services/post_registry.py` | `TrackedPostRepository` |
| `SocialMediaAutonomousAgents/backend/app/services/pulled_tweet_repository.py` | Reference tweet history |
| `SocialMediaAutonomousAgents/backend/app/services/post_lock_repository.py` | Concurrent post locks |
| `SocialMediaAutonomousAgents/backend/app/services/ravendb_service.py` | API-facing read aggregations |
| `SocialMediaAutonomousAgents/backend/app/models/account.py` | `AccountDocument` |
| `SocialMediaAutonomousAgents/backend/app/models/tracked_post.py` | `TrackedPostDocument`, `PostCreationMetrics` |
| `SocialMediaAutonomousAgents/backend/app/models/pulled_tweet.py` | `PulledTweetDocument` |
| `SocialMediaAutonomousAgents/backend/app/utils/encryption.py` | Fernet encrypt/decrypt |

## Database

| Setting | Default |
|---------|---------|
| `RAVENDB_URL` | `https://localhost` |
| `RAVENDB_DB` | `SocialMediaSwarm` |
| `RAVENDB_CLIENT_CERT` / `RAVENDB_CLIENT_KEY` | Optional mTLS |

Docker backend mounts host certs and uses `host.docker.internal` for RavenDB.

## Collections

| Collection | Document ID pattern | Purpose |
|------------|---------------------|---------|
| `Accounts` | `accounts/{account_id}` | Niche, status, encrypted X creds, posting state, `copied_reference_tweet_ids` |
| `TrackedPosts` | `trackedposts/{account_id}-{tweet_id}` | Posted tweet ids for engagement polling + creation metrics |
| `PulledTweets` | Per pulled tweet id | Audit/history of timeline references fetched |
| Post locks | `post-locks/{account_id}` | Short TTL lock during tick (`POST_LOCK_TTL_SECONDS`) |

## Account document (runtime fields)

Notable fields updated by the pipeline:

- `last_post_slot`, `last_post_id`, `last_post_text`, `last_post_at`, `last_post_views`
- `posts_total`, `followers`
- `copied_reference_tweet_ids` — source tweets already reposted (max 2000)
- `system_prompt`, `personality`, `negative_semantics` — compose inputs

Secrets stored as `*_enc` Fernet ciphertext. Never returned by HTTP list endpoints.

## Encryption

`ENCRYPTION_KEY` must be a Fernet url-safe key. Scripts (`add_account.py`) encrypt before save; `TwitterService` decrypts at use time.

## API vs repository

HTTP reads often go through `RavenDBService` (redacted shapes). Writes from dashboard use `AccountRepository` + `account_update_service`. Account **creation** is CLI-only via `AccountRepository.upsert_credentials`.

## Related docs

- API exposure: [api-and-dashboard](api-and-dashboard.md)
- Reference persistence: [reference-ingestion](reference-ingestion.md)
- Engagement storage: [engagement-and-metrics](engagement-and-metrics.md)
- Setup: [ACCOUNT_SETUP](../../SocialMediaAutonomousAgents/backend/docs/ACCOUNT_SETUP.md)
