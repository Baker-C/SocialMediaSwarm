"""Copied timeline reference tracking tests."""

from app.hourly.tweet_topic_preanalysis import run_reference_preanalysis, select_top_timeline_reference
from app.models.account import AccountDocument
from app.services.copied_references import (
    copied_reference_exclude_set,
    record_copied_reference,
)


def test_record_copied_reference_appends_once() -> None:
    acc = AccountDocument(account_id="a1", niche="News")
    record_copied_reference(acc, "100")
    record_copied_reference(acc, "100")
    record_copied_reference(acc, "200")
    assert acc.copied_reference_tweet_ids == ["100", "200"]


def test_select_top_skips_copied_ids() -> None:
    rows = [
        {"id": "1", "text": "top https://example.com/a", "like_count": 100},
        {"id": "2", "text": "second https://example.com/b", "like_count": 50},
    ]
    pick = select_top_timeline_reference(rows, exclude_ids=frozenset({"1"}))
    assert pick is not None
    assert pick.tweet_id == "2"


def test_run_preanalysis_all_copied_skips() -> None:
    rows = [
        {"id": "1", "text": "only https://example.com/a", "like_count": 10},
    ]
    result = run_reference_preanalysis(rows, niche="News", exclude_ids=frozenset({"1"}))
    assert result.skipped is True
    assert result.skip_reason == "all_references_already_copied"


def test_copied_reference_exclude_set_numeric_only() -> None:
    acc = AccountDocument(
        account_id="a1",
        niche="News",
        copied_reference_tweet_ids=["99", "", "bad", "100"],
    )
    assert copied_reference_exclude_set(acc) == frozenset({"99", "100"})
