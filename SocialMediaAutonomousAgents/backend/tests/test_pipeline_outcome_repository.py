"""PipelineOutcomeRepository list_for_account."""

from unittest.mock import MagicMock

from app.services.pipeline_outcome_repository import PipelineOutcomeRepository


def test_list_for_account_queries_rql() -> None:
    client = MagicMock()
    client.query.return_value = [
        {
            "account_id": "acct1",
            "phase": "runner",
            "status": "ok",
            "created_at": "2026-06-08T12:00:00+00:00",
        }
    ]
    repo = PipelineOutcomeRepository(client=client)

    rows = repo.list_for_account("acct1", limit=50, phase="runner", status="ok")

    assert len(rows) == 1
    assert rows[0].phase == "runner"
    rql = client.query.call_args[0][0]
    assert "PipelineOutcomes" in rql
    assert "acct1" in rql
    assert 'phase == "runner"' in rql
    assert 'status == "ok"' in rql
    assert "order by created_at desc" in rql


def test_list_for_account_filters_since_client_side() -> None:
    client = MagicMock()
    client.query.return_value = [
        {"account_id": "a", "phase": "p", "status": "ok", "created_at": "2026-06-01T00:00:00+00:00"},
        {"account_id": "a", "phase": "p", "status": "ok", "created_at": "2026-06-08T00:00:00+00:00"},
    ]
    repo = PipelineOutcomeRepository(client=client)

    rows = repo.list_for_account("a", since="2026-06-07T00:00:00+00:00")

    assert len(rows) == 1
    assert rows[0].created_at == "2026-06-08T00:00:00+00:00"
