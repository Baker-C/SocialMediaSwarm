from __future__ import annotations

from agent.orchestrator import run_provisioning
from agent.selectors import SEL
from agent.types import AgentContext
from tests.fakes import FakeBackend, FakeBrowser, Page, TextBrowser


def _no_sleep(_):
    return None


def _ctx(backend):
    return AgentContext(backend=backend, job=backend.job)


def test_full_run_with_captcha_pause_resolves_and_posts_result():
    # Scripted flow: email -> CAPTCHA overlay -> password -> key_capture -> success
    key_texts = {
        SEL.api_key_value: "KEY",
        SEL.api_secret_value: "SECRET",
        SEL.bearer_token_value: "BEARER",
    }
    pages = [
        Page(exists={SEL.email_input}),  # 0 email_entry
        Page(exists={SEL.captcha_iframe}),  # 1 CAPTCHA overlay (no advance selector)
        Page(exists={SEL.password_input}),  # 2 password
        Page(exists={SEL.api_key_value}),  # 3 key_capture
        Page(exists={SEL.success_marker}),  # 4 success
    ]
    b = TextBrowser(pages, texts=key_texts)
    # The CAPTCHA page advances when re-detected after operator solves it. The handler
    # for CAPTCHA doesn't click; the orchestrator's _wait_for_continue returns, then we
    # re-detect the SAME page index. To move past it we manually bump on continue:
    backend = FakeBackend(control_continue_after=2, control_action="continue")
    ctx = _ctx(backend)

    # Patch poll_control so that when it returns "continue" we advance the script off the
    # captcha page (simulating the operator solving it in the real browser).
    orig_poll = backend.poll_control

    def poll():
        action = orig_poll()
        if action == "continue":
            b.index += 1  # operator solved captcha -> next page now visible
        return action

    backend.poll_control = poll

    result = run_provisioning(b, ctx.job, ctx, sleep=_no_sleep)

    # terminal result posted with cookies + dev keys
    assert backend.result is not None
    assert backend.result is result
    assert result.session_cookies == b.storage_state_value
    assert result.dev_api_key == "KEY"
    assert result.password is not None  # password handler ran

    # status sequence includes the captcha pause and completion
    statuses = [s["status"] for s in backend.statuses]
    assert "awaiting_captcha" in statuses
    assert statuses[0] == "in_progress"  # initial push
    assert "complete" in statuses


def test_unknown_page_bounded_then_fails():
    pages = [Page(exists=set())]  # always UNKNOWN
    b = FakeBrowser(pages)
    backend = FakeBackend()
    ctx = _ctx(backend)
    result = run_provisioning(b, ctx.job, ctx, max_unknown_settles=3, sleep=_no_sleep)
    statuses = [s["status"] for s in backend.statuses]
    assert "failed" in statuses
    assert backend.result is None  # never posted a result


def test_deadline_zero_fails_fast():
    pages = [Page(exists={SEL.email_input})]
    b = FakeBrowser(pages)
    backend = FakeBackend()
    ctx = _ctx(backend)

    # now() advances past the deadline immediately on the loop check
    times = iter([0.0, 100.0, 200.0, 300.0])

    def now():
        return next(times, 1000.0)

    result = run_provisioning(b, ctx.job, ctx, deadline_seconds=10, now=now, sleep=_no_sleep)
    statuses = [s["status"] for s in backend.statuses]
    assert "failed" in statuses


def test_captcha_cancel_fails():
    pages = [Page(exists={SEL.captcha_iframe})]
    b = FakeBrowser(pages)
    backend = FakeBackend(control_continue_after=1, control_action="cancel")
    ctx = _ctx(backend)
    result = run_provisioning(b, ctx.job, ctx, sleep=_no_sleep)
    statuses = [s["status"] for s in backend.statuses]
    assert "failed" in statuses
    assert backend.result is None


def test_goto_signup_url_first():
    pages = [Page(exists={SEL.success_marker})]
    b = FakeBrowser(pages)
    backend = FakeBackend()
    ctx = _ctx(backend)
    run_provisioning(b, ctx.job, ctx, sleep=_no_sleep)
    assert b.gotos and "signup" in b.gotos[0]
