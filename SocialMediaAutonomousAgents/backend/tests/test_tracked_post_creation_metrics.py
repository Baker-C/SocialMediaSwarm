"""TrackedPosts persist optional creation_metrics on record_post."""

from unittest.mock import MagicMock

from app.models.tracked_post import PostCreationMetrics
from app.services.post_registry import TrackedPostRepository


def test_record_post_persists_creation_metrics() -> None:
    client = MagicMock()
    repo = TrackedPostRepository(client=client)

    metrics = PostCreationMetrics(
        candidates_created=5,
        tweets_pulled=12,
        regeneration_round=1,
        chosen_topic="Border policy",
        chosen_topic_id="t1",
    )
    repo.record_post("acct1", "tw99", "2026-05-15T12:00:00+00:00", creation_metrics=metrics)

    client.put_document.assert_called_once()
    doc_id, payload = client.put_document.call_args[0]
    assert client.put_document.call_args.kwargs.get("collection") == "TrackedPosts"
    assert doc_id == "trackedposts/acct1-tw99"
    assert payload["creation_metrics"] == {
        "candidates_created": 5,
        "tweets_pulled": 12,
        "tweets_pulled_new": 0,
        "tweets_pulled_duplicates": 0,
        "regeneration_round": 1,
        "chosen_topic": "Border policy",
        "chosen_topic_id": "t1",
    }


def test_record_post_omits_creation_metrics_when_none() -> None:
    client = MagicMock()
    repo = TrackedPostRepository(client=client)
    repo.record_post("acct1", "tw100")

    _, payload = client.put_document.call_args[0]
    assert "creation_metrics" not in payload
