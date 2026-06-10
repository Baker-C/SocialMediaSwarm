"""Typed context artifact accessors."""

from __future__ import annotations

import pytest

from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext


def test_set_artifact_validates_and_stores() -> None:
    ctx = TickRunContext(account_id="acct", slot="slot")
    ctx.set_artifact(
        ArtifactKey.ACCOUNT_BUNDLE,
        {"account_id": "acct", "profile": {"id": "1"}},
    )
    raw = ctx.get("account_bundle")
    assert isinstance(raw, dict)
    assert raw["account_id"] == "acct"


def test_set_artifact_rejects_invalid() -> None:
    ctx = TickRunContext(account_id="acct", slot="slot")
    with pytest.raises(ValueError, match="Invalid artifact"):
        ctx.set_artifact(ArtifactKey.ACCOUNT_BUNDLE, {"profile": {}})


def test_get_artifact_returns_model() -> None:
    ctx = TickRunContext(account_id="acct", slot="slot")
    ctx.set_artifact(
        ArtifactKey.TIMELINE_ANALYSIS,
        {"source": "timeline", "pattern_summary": "test"},
    )
    artifact = ctx.get_artifact(ArtifactKey.TIMELINE_ANALYSIS)
    assert artifact is not None
    assert artifact.pattern_summary == "test"  # type: ignore[attr-defined]


def test_require_artifact_raises_when_missing() -> None:
    ctx = TickRunContext(account_id="acct", slot="slot")
    with pytest.raises(KeyError):
        ctx.require_artifact(ArtifactKey.OWN_POSTS)
