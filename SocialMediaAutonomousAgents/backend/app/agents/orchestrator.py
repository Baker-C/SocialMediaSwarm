from __future__ import annotations

from typing import Any, Literal

from app.agents.content_creator import ContentCreator
from app.agents.safety_guardian import SafetyGuardian
from app.hourly.runner import build_tick_context, run_hourly_tick
from app.services.account_repository import AccountRepository
from app.services.post_registry import TrackedPostRepository
from app.services.pulled_tweet_repository import PulledTweetRepository
from app.services.tick_data_service import TickDataService
from app.services.twitter_service import TwitterService

TickRunMode = Literal["scheduled", "force"]

_MISSING_POST_REGISTRY = object()
_MISSING_PULLED_TWEETS = object()


class Orchestrator:
    def __init__(
        self,
        repo: AccountRepository | None = None,
        twitter: TwitterService | None = None,
        creator: ContentCreator | None = None,
        guardian: SafetyGuardian | None = None,
        post_registry: Any = _MISSING_POST_REGISTRY,
        pulled_tweets: Any = _MISSING_PULLED_TWEETS,
    ) -> None:
        self.repo = repo or AccountRepository()
        self.twitter = twitter or TwitterService(self.repo)
        self.creator = creator or ContentCreator()
        self.guardian = guardian or SafetyGuardian()
        if post_registry is _MISSING_POST_REGISTRY:
            self.post_registry: TrackedPostRepository | None = TrackedPostRepository()
        else:
            self.post_registry = post_registry
        if pulled_tweets is _MISSING_PULLED_TWEETS:
            self.pulled_tweets: PulledTweetRepository | None = PulledTweetRepository()
        else:
            self.pulled_tweets = pulled_tweets

    def run_tick(
        self,
        *,
        mode: TickRunMode = "scheduled",
        account_ids: list[str] | None = None,
        bypass_post_cooldown: bool = False,
    ) -> dict:
        """
        Hourly orchestration entrypoint.

        ``mode="scheduled"`` — APScheduler path; enforces one post per account per slot when applicable.
        ``mode="force"`` — optional list ``account_ids``; bypasses hourly slot idempotency for those accounts.
        ``bypass_post_cooldown`` — allow posting inside the cooldown window (manual ``--force-now``).
        """
        force_ids = frozenset(account_ids) if account_ids else None
        tick_data = TickDataService(
            self.repo, self.twitter, self.post_registry, self.pulled_tweets
        )
        ctx = build_tick_context(
            repo=self.repo,
            twitter=self.twitter,
            creator=self.creator,
            guardian=self.guardian,
            tick_data=tick_data,
            post_registry=self.post_registry,
            mode=mode,
            force_account_ids=force_ids,
            max_candidates=5,
            max_regeneration_rounds=3,
            bypass_post_cooldown=bypass_post_cooldown,
        )
        return run_hourly_tick(ctx)
