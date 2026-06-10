"""PostMetricSnapshotRepository list_for_tweet."""

from unittest.mock import MagicMock

from app.services.post_metric_snapshot_repository import PostMetricSnapshotRepository


def test_list_for_tweet_queries_rql_ordered_asc() -> None:
    client = MagicMock()
    client.query.return_value = [
        {
            "account_id": "acct1",
            "tweet_id": "99",
            "captured_at": "2026-06-01T10:00:00+00:00",
            "like_count": 1,
        },
        {
            "account_id": "acct1",
            "tweet_id": "99",
            "captured_at": "2026-06-01T11:00:00+00:00",
            "like_count": 2,
        },
    ]
    repo = PostMetricSnapshotRepository(client=client)

    rows = repo.list_for_tweet("acct1", "99", limit=100)

    assert len(rows) == 2
    assert rows[0].captured_at == "2026-06-01T10:00:00+00:00"
    assert rows[1].like_count == 2
    rql = client.query.call_args[0][0]
    assert "acct1" in rql
    assert "99" in rql
    assert "order by captured_at asc" in rql
    assert "limit 100" in rql


def test_list_for_tweet_returns_empty_for_invalid_ids() -> None:
    client = MagicMock()
    repo = PostMetricSnapshotRepository(client=client)
    assert repo.list_for_tweet("", "99") == []
    client.query.assert_not_called()
