"""VoiceRevisionRepository list_for_account."""

from unittest.mock import MagicMock

from app.services.voice_revision_repository import VoiceRevisionRepository


def test_list_for_account_queries_rql_ordered_asc() -> None:
    client = MagicMock()
    client.query.return_value = [
        {
            "account_id": "acct1",
            "seq": 1,
            "label": "v1",
            "version_hash": "h1",
            "changed_at": "t1",
        },
        {
            "account_id": "acct1",
            "seq": 2,
            "label": "v2",
            "version_hash": "h2",
            "changed_at": "t2",
        },
    ]
    repo = VoiceRevisionRepository(client=client)

    rows = repo.list_for_account("acct1")

    assert len(rows) == 2
    assert rows[0].seq == 1
    assert rows[1].label == "v2"
    rql = client.query.call_args[0][0]
    assert "VoiceRevisions" in rql
    assert "acct1" in rql
    assert "order by seq asc" in rql
