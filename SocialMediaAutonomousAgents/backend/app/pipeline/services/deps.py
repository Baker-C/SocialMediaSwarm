"""Dependencies for one post run (built once, passed through the runbook)."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.account_repository import AccountRepository
from app.services.post_registry import TrackedPostRepository
from app.services.pulled_tweet_repository import PulledTweetRepository
from app.services.tick_data_service import TickDataService
from app.services.twitter_service import TwitterService


@dataclass
class PostRunDeps:
    """Everything a runbook step may need — callers rarely touch fields directly."""

    tick_data: TickDataService
    repo: AccountRepository
    post_registry: TrackedPostRepository | None = None
    pulled_tweets: PulledTweetRepository | None = None
    twitter: TwitterService | None = None

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
