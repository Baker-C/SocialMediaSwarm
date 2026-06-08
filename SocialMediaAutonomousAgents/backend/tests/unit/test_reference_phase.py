"""Unit tests for reference phase bridge."""

from unittest.mock import patch

from app.interval.reference_phase import ranked_refs_from_runbook
from app.interval.tweet_topic_preanalysis import GatheredTweet


def test_ranked_refs_from_runbook_excludes_copied_ids() -> None:
    ctx_data = {
        "timeline_ranked": {
            "ranked": [
                GatheredTweet(tweet_id="a", text="one https://x.com/1", popularity_score=10.0).model_dump(),
                GatheredTweet(tweet_id="b", text="two https://x.com/2", popularity_score=5.0).model_dump(),
            ],
        },
    }
    ranked = ranked_refs_from_runbook(ctx_data, copied_exclude=frozenset({"a"}))
    assert [t.tweet_id for t in ranked] == ["b"]


def test_ranked_refs_from_runbook_respects_max_attempts() -> None:
    ctx_data = {
        "timeline_ranked": {
            "ranked": [
                GatheredTweet(tweet_id=str(i), text=f"t{i}", popularity_score=float(i)).model_dump()
                for i in range(5)
            ],
        },
    }
    with patch("app.interval.reference_phase.settings") as mock_settings:
        mock_settings.max_reference_fallback_attempts = 2
        ranked = ranked_refs_from_runbook(ctx_data, copied_exclude=frozenset())
    assert len(ranked) == 2
    assert ranked[0].tweet_id == "0"
    assert ranked[1].tweet_id == "1"


def test_ranked_refs_from_runbook_uses_pre_ranked_order() -> None:
    ctx_data = {
        "timeline_ranked": {
            "ranked": [
                GatheredTweet(tweet_id="z", text="z", popularity_score=1.0).model_dump(),
                GatheredTweet(tweet_id="a", text="a", popularity_score=999.0).model_dump(),
            ],
        },
    }
    ranked = ranked_refs_from_runbook(ctx_data, copied_exclude=frozenset())
    assert [t.tweet_id for t in ranked] == ["z", "a"]
