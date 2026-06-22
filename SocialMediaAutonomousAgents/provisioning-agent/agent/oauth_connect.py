"""Inline OAuth auto-connect: runs right after signup SUCCESS, in the new account's
live browser session, so the account is connected (and API-postable) the moment it's
made — no manual "Connect with X" click.

Uses the shared global OAuth app (per-account dev-app isolation is deferred). Safety:
before authorizing it asserts the *active* x.com session is the account we just
created, and after authorizing it verifies the backend actually stored a connection
(and that the connected identity matches) — so a wrong/stale session fails loudly
instead of silently connecting the wrong account.

Pure w.r.t. browser/backend (both via ports) and clock/sleep (injected) so tests run
instantly.
"""
from __future__ import annotations

from typing import Callable

from .browser_port import BrowserPort
from .selectors import BODY, SEL, TXT
from .types import AgentContext, HandlerResult, ProvisioningJob

X_HOME_URL = "https://x.com/home"


def connect_oauth(
    b: BrowserPort,
    job: ProvisioningJob,
    ctx: AgentContext,
    *,
    deadline: float,
    now: Callable[[], float],
    sleep: Callable[[float], None],
    poll_interval_seconds: float = 2.0,
) -> HandlerResult:
    # 1. Assert the active session is the account we just created (guards wrong/stale login).
    b.goto(X_HOME_URL)
    active = (b.text(SEL.logged_in_handle) or "").strip().lstrip("@")
    if not active:
        return HandlerResult(failed=True, error="oauth: no logged-in session after signup")
    if job.handle and active.lower() != job.handle.lower():
        return HandlerResult(
            failed=True,
            error=f"oauth: active session @{active} != target @{job.handle}; refusing to connect",
        )

    # 2. Fetch the authorization URL (global app + server-stored PKCE state).
    url = (ctx.backend.get_oauth_authorize_url() or "").strip()
    if not url:
        return HandlerResult(failed=True, error="oauth: backend returned no authorize url")

    # 3. Navigate to the consent screen in this same session.
    b.goto(url)

    # 4. Wait for the consent button (CAPTCHA-aware: the overlay can appear here too).
    while now() < deadline:
        if b.exists(SEL.captcha_iframe) or TXT.captcha in b.text(BODY).lower():
            ctx.backend.push_status(status="awaiting_captcha", current_page="oauth_captcha", note="awaiting CAPTCHA")
            action = _wait_for_continue(ctx, now, sleep, deadline, poll_interval_seconds)
            if action == "cancel":
                return HandlerResult(failed=True, error="oauth: cancelled by operator during CAPTCHA")
            if action is None:
                return HandlerResult(failed=True, error="oauth: deadline waiting for CAPTCHA")
            continue
        if b.exists(SEL.oauth_authorize_button):
            break
        sleep(poll_interval_seconds)
    else:
        return HandlerResult(failed=True, error="oauth: consent screen never appeared")

    # 5. Authorize. The redirect to the backend callback completes the token exchange server-side.
    b.click(SEL.oauth_authorize_button)

    # 6. Verify the backend actually stored a connection (the source of truth), and that the
    #    connected identity matches the account we provisioned.
    while now() < deadline:
        st = ctx.backend.get_oauth_status()
        if st.get("connected"):
            connected_uid = str(st.get("x_user_id") or "").strip()
            target_uid = (ctx.result.x_user_id or "").strip()
            if target_uid and connected_uid and connected_uid != target_uid:
                return HandlerResult(
                    failed=True,
                    error=f"oauth: connected x_user_id {connected_uid} != provisioned {target_uid}",
                )
            return HandlerResult(status_note="oauth connected")
        sleep(poll_interval_seconds)
    return HandlerResult(failed=True, error="oauth: timed out waiting for backend connection")


def _wait_for_continue(ctx, now, sleep, deadline, poll_interval_seconds):
    """Poll GET control until the operator returns 'continue'/'cancel' (or deadline)."""
    while now() < deadline:
        action = ctx.backend.poll_control()
        if action in ("continue", "cancel"):
            return action
        sleep(poll_interval_seconds)
    return None
