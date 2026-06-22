"""Media-caption compose: skip cleanly when the LLM cannot produce a caption."""

from unittest.mock import MagicMock, patch

from app.models.account import AccountDocument
from app.pipeline.services.deps import ActLive, PostRunDeps
from app.pipeline.tools import compose_with_media
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext


def _deps(account: AccountDocument, guardian) -> PostRunDeps:
    return PostRunDeps(
        tick_data=MagicMock(),
        repo=MagicMock(),
        post_registry=None,
        twitter=MagicMock(),
        live=ActLive(
            account=account,
            tick_ctx=MagicMock(),
            guardian=guardian,
            twitter=MagicMock(),
            post_registry=None,
            run_id="run1",
            max_regeneration_rounds=5,
        ),
    )


def test_compose_with_media_skips_when_llm_disabled() -> None:
    """No LLM → no fabricated 'Check out this image!' stub; skip with compose_failed."""
    acc = AccountDocument(account_id="a1", niche="News")
    guardian = MagicMock()
    ctx = TickRunContext(
        account_id="a1",
        slot="2026-05-19-12",
        mode="force",
        niche="News",
        data={"generated_image": {"b64": "stub"}},
    )
    deps = _deps(acc, guardian)

    with patch("app.pipeline.tools.compose_with_media.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = False
        result = compose_with_media.run(ctx, deps)

    assert result.ok and result.skipped
    assert result.skip_reason == "compose_failed"
    guardian.evaluate.assert_not_called()
    assert ctx.data["composed_post_with_media"]["text"] is None
    verdict = ctx.get_artifact(ArtifactKey.SAFETY_VERDICT)
    assert verdict is not None and not verdict.approved
