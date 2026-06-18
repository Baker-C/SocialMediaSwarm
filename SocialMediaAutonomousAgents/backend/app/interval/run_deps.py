"""Build pipeline dependencies from interval tick context."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.pipeline.services.deps import PostRunDeps

if TYPE_CHECKING:
    from app.interval.context import TickContext


def post_run_deps_from_tick(tick_ctx: TickContext) -> PostRunDeps:
    """Build SENSE-only PostRunDeps from the interval tick context.

    Reuses services already wired on the interval tick (no duplicate TickDataService).
    ACT-phase handles (guardian, max_regeneration_rounds, bypass_post_cooldown) are
    set on deps.live by the runner (doc 07), not here.

    Args:
        tick_ctx: The TickContext from the interval scheduler.

    Returns:
        PostRunDeps with tick_data, repo, post_registry, twitter services initialized.
    """
    return PostRunDeps(
        tick_data=tick_ctx.tick_data,
        repo=tick_ctx.repo,
        post_registry=tick_ctx.post_registry,
        twitter=tick_ctx.twitter,
    )
