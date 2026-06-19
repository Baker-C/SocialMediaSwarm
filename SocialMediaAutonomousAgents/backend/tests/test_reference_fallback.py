"""Timeline reference fallback when niche check fails."""

from unittest.mock import MagicMock, patch

from app.interval.tweet_topic_preanalysis import rank_timeline_references
from app.models.account import AccountDocument
from app.pipeline.services.deps import ActLive, PostRunDeps
from app.pipeline.tools.llm import compose_until_safe
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext


def test_rank_timeline_references_orders_by_popularity() -> None:
    rows = [
        {"id": "1", "text": "a https://x.com/1", "like_count": 5},
        {"id": "2", "text": "b https://x.com/2", "like_count": 100},
        {"id": "3", "text": "c https://x.com/3", "like_count": 20},
    ]
    ranked = rank_timeline_references(rows)
    assert [t.tweet_id for t in ranked] == ["2", "3", "1"]


def test_runner_tries_next_reference_on_niche_mismatch() -> None:
    """The niche-mismatch reference-fallback loop moved out of the imperative runner and
    INTO the compose tool (app/pipeline/tools/llm/compose_until_safe.py). Assert the SAME
    behavior at the new seam: compose is attempted on the top reference ("viral"); when the
    guardian rejects it for a niche mismatch, compose falls back to the next reference
    ("pol"), which passes — and that approved body is what the run carries forward."""
    from app.interval.tweet_topic_preanalysis import GatheredTweet

    acc = AccountDocument(account_id="a1", niche="Breaking Political News Commentary")

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

    # The ranked references compose reads (TIMELINE_RANKED.ranked): viral ranked first.
    ctx = TickRunContext(
        account_id="a1",
        slot="2026-05-19-12",
        mode="force",
        niche=acc.category,
        data={
            "timeline_ranked": {
                "ranked": [viral.model_dump(), political.model_dump()],
                "winner": viral.model_dump(),
            },
            "timeline_analysis": {"pattern_summary": "viral political mix"},
            "own_posts_analysis": {"skipped": True, "skip_reason": "insufficient_own_posts"},
        },
    )
    deps = PostRunDeps(
        tick_data=MagicMock(),
        repo=MagicMock(),
        post_registry=None,
        twitter=MagicMock(),
        live=ActLive(
            account=acc,
            tick_ctx=MagicMock(),
            guardian=guardian,
            twitter=MagicMock(),
            post_registry=None,
            run_id="run1",
            max_regeneration_rounds=10,
        ),
    )

    with patch(
        "app.pipeline.tools.llm.compose_until_safe.compose_formatted_post",
        side_effect=fake_compose,
    ):
        result = compose_until_safe.run(ctx, deps)

    # Fallback order preserved: viral attempted first (niche-mismatch reject), then pol.
    assert compose_calls == ["viral", "pol"]
    # The approved pol body is what compose selected and carried forward as COMPOSED_POST,
    # with the safety verdict marked approved.
    assert result.ok
    verdict = ctx.get_artifact(ArtifactKey.SAFETY_VERDICT)
    assert verdict is not None and verdict.approved
    composed = ctx.get_artifact(ArtifactKey.COMPOSED_POST)
    assert composed is not None and composed.body == "body for pol"
