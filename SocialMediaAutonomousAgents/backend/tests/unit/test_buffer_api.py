from unittest.mock import patch

import pytest

from app.infrastructure.buffer_api import (
    BufferAPIError,
    buffer_create_queued_post,
    buffer_graphql,
    buffer_verify_channel_accessible,
)


def test_buffer_create_queued_post_success():
    payload = {"data": {"createPost": {"post": {"id": "p1", "text": "hi", "dueAt": "2026-01-01T00:00:00Z"}}}}
    with patch("app.infrastructure.buffer_api.buffer_graphql", return_value=payload):
        out = buffer_create_queued_post("buf_key", "chan_1", "hi")
    assert out["id"] == "p1"
    assert out["text"] == "hi"


def test_buffer_create_queued_post_mutation_error():
    payload = {"data": {"createPost": {"message": "Channel not found"}}}
    with patch("app.infrastructure.buffer_api.buffer_graphql", return_value=payload):
        with pytest.raises(BufferAPIError, match="Channel not found"):
            buffer_create_queued_post("k", "bad", "x")


def test_buffer_create_queued_post_graphql_errors():
    with patch(
        "app.infrastructure.buffer_api.buffer_graphql",
        side_effect=BufferAPIError("Unauthorized"),
    ):
        with pytest.raises(BufferAPIError, match="Unauthorized"):
            buffer_create_queued_post("k", "c", "t")


def test_buffer_verify_channel_accessible_ok():
    def side_effect(api_key: str, query: str, **kwargs):
        assert api_key == "k"
        if "organizations" in query:
            return {"data": {"account": {"organizations": [{"id": "org1"}]}}}
        if "channels" in query:
            return {
                "data": {
                    "channels": [
                        {"id": "other", "name": "A", "service": "instagram"},
                        {"id": "want", "name": "X", "service": "twitter"},
                    ]
                }
            }
        raise AssertionError("unexpected query")

    with patch("app.infrastructure.buffer_api.buffer_graphql", side_effect=side_effect):
        buffer_verify_channel_accessible("k", "want")


def test_buffer_verify_channel_accessible_with_organization_id():
    def side_effect(api_key: str, query: str, **kwargs):
        if "channels" in query:
            assert kwargs.get("variables", {}).get("organizationId") == "org-fixed"
            return {"data": {"channels": [{"id": "c99", "name": "T", "service": "twitter"}]}}
        raise AssertionError("unexpected query")

    with patch("app.infrastructure.buffer_api.buffer_graphql", side_effect=side_effect):
        buffer_verify_channel_accessible("k", "c99", organization_id="org-fixed")


def test_buffer_verify_channel_accessible_not_found():
    def side_effect(api_key: str, query: str, **kwargs):
        if "organizations" in query:
            return {"data": {"account": {"organizations": [{"id": "org1"}]}}}
        if "channels" in query:
            return {"data": {"channels": [{"id": "nope", "name": "X", "service": "twitter"}]}}
        raise AssertionError("unexpected query")

    with patch("app.infrastructure.buffer_api.buffer_graphql", side_effect=side_effect):
        with pytest.raises(BufferAPIError, match="not found"):
            buffer_verify_channel_accessible("k", "want")


def test_buffer_graphql_empty_key():
    with pytest.raises(BufferAPIError, match="empty"):
        buffer_graphql("", "{ __typename }")
