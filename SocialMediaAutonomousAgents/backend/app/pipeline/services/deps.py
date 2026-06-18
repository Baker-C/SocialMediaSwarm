"""Dependencies for one post run (built once, passed through the runbook)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.models.account import AccountDocument
from app.services.account_repository import AccountRepository
from app.services.post_registry import TrackedPostRepository
from app.services.pulled_tweet_repository import PulledTweetRepository
from app.services.tick_data_service import TickDataService
from app.services.twitter_service import TwitterService

if TYPE_CHECKING:
    from app.interval.context import TickContext


@dataclass
class ActLive:
    """Non-serializable handles + engine-injected config the ACT steps need, carried
    OUTSIDE ctx.data. The serializable VIEW of what these produce is the captured
    artifact (COMPOSED_POST / SAFETY_VERDICT / PUBLISHED_POST); these raw objects exist
    only for the duration of the run and are never traced or persisted.
    """

    account: AccountDocument
    tick_ctx: Any                      # TickContext (live eval engine; never spec-tunable)
    guardian: Any                      # SafetyGuardian (live eval engine; never spec-tunable)
    twitter: Any                       # TwitterService — == tick_ctx.twitter (CC-7 names it explicitly)
    post_registry: Any                 # TrackedPostRepository — == tick_ctx.post_registry (CC-7)
    run_id: str                        # → creation_metrics.run_id + idempotency key (02 attribution)
    pipeline_hash: str | None = None   # loaded spec.version_hash → creation_metrics.pipeline_hash (02)
    copied_exclude: frozenset[str] = frozenset()  # fallback-exclusion set for ranked_refs build
    max_regeneration_rounds: int = 10
    bypass_post_cooldown: bool = False


@dataclass
class PostRunDeps:
    """Everything a runbook step may need — callers rarely touch fields directly."""

    tick_data: TickDataService
    repo: AccountRepository
    post_registry: TrackedPostRepository | None = None
    pulled_tweets: PulledTweetRepository | None = None
    twitter: TwitterService | None = None
    # ── ACT-phase side-channel (engine-injected; never proposable in a spec) ──
    live: ActLive | None = None

    @classmethod
    def build(
        cls,
        *,
        repo: AccountRepository | None = None,
        twitter: TwitterService | None = None,
        post_registry: TrackedPostRepository | None = None,
        pulled_tweets: PulledTweetRepository | None = None,
    ) -> PostRunDeps:
        repo = repo or AccountRepository()
        twitter = twitter or TwitterService(repo)
        post_registry = post_registry if post_registry is not None else TrackedPostRepository()
        pulled_tweets = pulled_tweets if pulled_tweets is not None else PulledTweetRepository()
        tick_data = TickDataService(repo, twitter, post_registry, pulled_tweets)
        return cls(
            tick_data=tick_data,
            repo=repo,
            post_registry=post_registry,
            pulled_tweets=pulled_tweets,
            twitter=twitter,
        )
