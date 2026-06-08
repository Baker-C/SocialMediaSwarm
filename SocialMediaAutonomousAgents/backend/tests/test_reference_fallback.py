"""Timeline reference fallback when niche check fails."""

from unittest.mock import MagicMock, patch

from app.interval.reference_phase import ReferencePhaseResult
from app.interval.runner import build_tick_context, run_account_pipeline
from app.interval.tweet_topic_preanalysis import rank_timeline_references
from app.models.account import AccountDocument
from tests.test_orchestrator import FakeRepo


def test_rank_timeline_references_orders_by_popularity() -> None:
    rows = [
        {"id": "1", "text": "a https://x.com/1", "like_count": 5},
        {"id": "2", "text": "b https://x.com/2", "like_count": 100},
        {"id": "3", "text": "c https://x.com/3", "like_count": 20},
    ]
    ranked = rank_timeline_references(rows)
    assert [t.tweet_id for t in ranked] == ["2", "3", "1"]


def test_runner_tries_next_reference_on_niche_mismatch() -> None:
    from app.interval.tweet_topic_preanalysis import GatheredTweet

    acc = AccountDocument(account_id="a1", niche="Breaking Political News Commentary")
    repo = FakeRepo([acc])
    tw = MagicMock()

    pol_text = "Senate vote on bill https://example.com/a"
    viral_text = "Airplane drama https://example.com/b"
    political = GatheredTweet(
        tweet_id="pol",
        text=pol_text,
        popularity_score=10.0,
        metrics={
            "id": "pol",
            "text": pol_text,
            "tweet_permalink": "https://x.com/i/status/pol",
        },
    )
    viral = GatheredTweet(
        tweet_id="viral",
        text=viral_text,
        popularity_score=100.0,
        metrics={
            "id": "viral",
            "text": viral_text,
            "tweet_permalink": "https://x.com/i/status/viral",
        },
    )

    guardian = MagicMock()
    guardian.evaluate.side_effect = [
        (False, "niche_mismatch:not political"),
        (True, None),
    ]

    compose_calls: list[str] = []

    def fake_compose(winner, niche, **kwargs):
        compose_calls.append(winner.tweet_id)
        return f"body for {winner.tweet_id}"

    ref_result = ReferencePhaseResult(
        ok=True,
        bundle_account={"profile": {"id": "u1"}},
        refs_payload={
            "timeline_reference_tweets": [
                {"id": "viral", "text": viral_text, "like_count": 100},
                {"id": "pol", "text": pol_text, "like_count": 10},
            ],
            "reference_errors": [],
        },
        reference_pool=[
            {"id": "viral", "text": viral_text, "like_count": 100},
            {"id": "pol", "text": pol_text, "like_count": 10},
        ],
        ranked_refs=[viral, political],
        timeline_analysis={"pattern_summary": "viral political mix"},
        own_posts_analysis={"skipped": True, "skip_reason": "insufficient_own_posts"},
    )

    working = repo.load("a1")
    assert working is not None

    with (
        patch("app.interval.orchestration.post_guard.PostLockRepository") as lock_cls,
        patch("app.interval.orchestration.post_guard._acquire_file_lock", return_value=True),
        patch("app.interval.orchestration.post_guard._release_file_lock"),
        patch("app.interval.runner.current_interval_slot_key", return_value="2026-05-19-12"),
        patch("app.interval.runner.compose_formatted_post", side_effect=fake_compose),
        patch("app.interval.runner.run_reference_phase", return_value=ref_result),
        patch(
            "app.interval.runner.finalize_post",
            return_value={"account_id": "a1", "tweet": {"id": "99"}},
        ) as fin,
    ):
        lock_cls.return_value.try_acquire.return_value = True
        lock_cls.return_value.release.return_value = None
        ctx = build_tick_context(
            repo=repo,
            twitter=tw,
            creator=MagicMock(),
            guardian=guardian,
            tick_data=MagicMock(),
            post_registry=None,
            mode="force",
        )
        out = run_account_pipeline(ctx, working)

    assert "tweet" in out
    assert compose_calls == ["viral", "pol"]
    fin.assert_called_once()
