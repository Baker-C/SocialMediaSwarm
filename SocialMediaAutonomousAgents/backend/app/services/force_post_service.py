"""Manual force-post orchestration for HTTP/API triggers."""

from __future__ import annotations

from typing import Any, Callable

from app.agents.orchestrator import Orchestrator
from app.services.force_post_progress import ProgressCallback, run_with_progress


def run_force_post(
    account_id: str,
    *,
    on_progress: ProgressCallback | None = None,
    bypass_cooldown: bool = True,
) -> dict[str, Any]:
    aid = (account_id or "").strip()
    if not aid:
        raise ValueError("account_id is required")

    def _run() -> dict[str, Any]:
        orch = Orchestrator()
        return orch.run_tick(
            mode="force",
            account_ids=[aid],
            bypass_post_cooldown=bypass_cooldown,
        )

    if on_progress is None:
        return _run()
    return run_with_progress(on_progress, _run)
