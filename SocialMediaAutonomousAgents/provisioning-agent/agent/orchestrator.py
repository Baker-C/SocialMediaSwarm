"""The provisioning loop: detect -> dispatch -> report, with a re-enterable CAPTCHA pause.

Bounded by an overall deadline, bounded UNKNOWN settle attempts, and the handlers' own
bounded retries. Pure with respect to the browser/backend: both arrive via ports, and
the clock/sleep are injectable so tests run instantly.
"""
from __future__ import annotations

import time
from typing import Callable

from .browser_port import BrowserPort
from .handlers import HANDLERS
from .page_state import PageDetector, PageState
from .types import AgentContext, ProvisioningJob, ProvisioningResult

X_SIGNUP_URL = "https://x.com/i/flow/signup"


# Map a PageState to the backend status string.
def _map_status(state: PageState) -> str:
    if state == PageState.SUCCESS:
        return "complete"
    if state == PageState.CAPTCHA:
        return "awaiting_captcha"
    return "in_progress"


def run_provisioning(
    b: BrowserPort,
    job: ProvisioningJob,
    ctx: AgentContext,
    *,
    deadline_seconds: int = 1800,
    max_unknown_settles: int = 5,
    poll_interval_seconds: float = 2.0,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    detector: PageDetector | None = None,
) -> ProvisioningResult:
    detector = detector or PageDetector()

    ctx.backend.push_status(status="in_progress", current_page="start")
    b.goto(X_SIGNUP_URL)

    deadline = now() + deadline_seconds
    unknown_settles = 0

    while now() < deadline:
        state = detector.detect(b)
        ctx.backend.push_status(status=_map_status(state), current_page=state.value)

        if state == PageState.SUCCESS:
            break

        if state == PageState.CAPTCHA:
            ctx.backend.push_status(status="awaiting_captcha", current_page="captcha", note="awaiting CAPTCHA")
            action = _wait_for_continue(ctx, now, sleep, deadline, poll_interval_seconds)
            if action == "cancel":
                return _fail(ctx, "cancelled by operator during CAPTCHA")
            if action is None:  # deadline hit while waiting
                return _fail(ctx, "deadline exceeded waiting for CAPTCHA")
            continue  # re-detect after the operator solved it

        handler = HANDLERS.get(state)
        if handler is None:  # UNKNOWN: bounded short-wait + re-detect
            unknown_settles += 1
            if unknown_settles > max_unknown_settles:
                return _fail(ctx, "stuck on unknown page")
            sleep(poll_interval_seconds)
            continue
        unknown_settles = 0  # reset once we recognize a page again

        res = handler.handle(b, job, ctx)
        if res.status_note:
            ctx.backend.push_status(status=_map_status(state), current_page=state.value, note=res.status_note)
        if res.failed:
            return _fail(ctx, res.error or "handler failed")
        sleep(poll_interval_seconds)  # let navigation/render settle
    else:
        return _fail(ctx, "deadline exceeded")

    ctx.result.session_cookies = b.storage_state()
    ctx.backend.post_result(ctx.result)
    return ctx.result


def _wait_for_continue(ctx, now, sleep, deadline, poll_interval_seconds):
    """Poll GET control until the operator returns 'continue'/'cancel' (or deadline)."""
    while now() < deadline:
        action = ctx.backend.poll_control()
        if action in ("continue", "cancel"):
            return action
        sleep(poll_interval_seconds)
    return None


def _fail(ctx: AgentContext, error: str) -> ProvisioningResult:
    ctx.backend.push_status(status="failed", current_page="failed", note=error)
    return ctx.result
