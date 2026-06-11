"""RavenDBService analytics extensions: dashboard, metrics, fleet posts, account public."""

from unittest.mock import MagicMock, patch

from app.models.account import AccountDocument
from app.models.metrics import AccountMetricsDocument
from app.models.tracked_post import TrackedPostDocument
from app.services.ravendb_service import RavenDBService, _account_public


def test_account_public_includes_voice_and_reference_fields() -> None:
    acc = AccountDocument(
        account_id="acct1",
        niche="tech",
        status="active",
        search_queries=["q1", "q2"],
        voice_version_label="v3",
        voice_version_seq=3,
        copied_reference_tweet_ids=["ref1", "ref2", "ref3"],
    )
    with patch("app.services.ravendb_service._account_has_x_credentials", return_value=False):
        pub = _account_public(acc)

    assert pub["voice_version_label"] == "v3"
    assert pub["voice_version_seq"] == 3
    assert pub["search_queries_count"] == 2
    assert pub["copied_reference_count"] == 3


def test_get_dashboard_includes_fleet_kpis() -> None:
    accounts = MagicMock()
    accounts.list_active.return_value = [
        AccountDocument(account_id="a1", niche="tech", status="active"),
        AccountDocument(account_id="a2", niche="tech", status="active"),
    ]
    tracked = MagicMock()
    tracked.list_for_account.side_effect = [
        [{"engagement_rate": 0.1, "reply_rate": 0.02}],
        [],
    ]
    svc = RavenDBService(account_repo=accounts)
    svc._tracked = tracked

    dash = svc.get_dashboard()

    assert dash["active_accounts"] == 2
    assert dash["top_niche"] == "tech"
    assert dash["total_tracked_posts"] == 1
    assert dash["accounts_without_posts"] == 1
    assert dash["avg_reply_rate"] == 0.02
    assert "computed_at" in dash


def test_get_account_metrics_returns_doc() -> None:
    metrics_doc = AccountMetricsDocument(
        account_id="a1",
        computed_at="2026-06-08T00:00:00+00:00",
        avg_engagement_rate=0.12,
        follower_delta_engagement_gap=0.03,
    )
    svc = RavenDBService()
    with patch.object(svc, "_load_account_metrics", return_value=metrics_doc):
        result = svc.get_account_metrics("a1")

    assert result is not None
    assert result["account_id"] == "a1"
    assert result["avg_engagement_rate"] == 0.12
    assert result["follower_delta_engagement_gap"] == 0.03


def test_get_posts_fleet_rollup() -> None:
    accounts = MagicMock()
    accounts.list_active.return_value = [
        AccountDocument(account_id="a1", niche="tech", status="active"),
    ]
    tracked = MagicMock()
    tracked.list_for_account.return_value = [
        TrackedPostDocument(
            account_id="a1",
            tweet_id="t1",
            posted_at="2026-06-08T00:00:00+00:00",
        ).model_dump(),
        TrackedPostDocument(
            account_id="a1",
            tweet_id="t2",
            posted_at="2026-06-07T00:00:00+00:00",
        ).model_dump(),
    ]
    svc = RavenDBService(account_repo=accounts)
    svc._tracked = tracked

    posts = svc.get_posts(limit_per_account=5)

    assert len(posts) == 2
    assert posts[0]["tweet_id"] == "t1"
    tracked.list_for_account.assert_called_once_with("a1", limit=5)


@patch("app.api.routes.posts.service")
def test_posts_route_fleet_rollup(mock_service) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    mock_service.get_posts.return_value = [{"account_id": "a1", "tweet_id": "t1"}]
    client = TestClient(app)

    resp = client.get("/api/posts?limit_per_account=3")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    mock_service.get_posts.assert_called_once_with(limit_per_account=3)
