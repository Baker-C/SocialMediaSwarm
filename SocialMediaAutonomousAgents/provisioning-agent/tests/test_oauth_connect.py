"""Tests for the inline OAuth auto-connect sub-phase (Mode A)."""
from __future__ import annotations

from agent.oauth_connect import connect_oauth
from agent.selectors import SEL
from agent.types import AgentContext
from tests.fakes import FakeBackend, Page, TextBrowser


class Clock:
    """Monotonic clock that advances by `step` on each call (so timeouts terminate)."""

    def __init__(self, step: float = 1.0) -> None:
        self.t = 0.0
        self.step = step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


def _ctx(be: FakeBackend) -> AgentContext:
    return AgentContext(backend=be, job=be.job)


def test_connect_happy_path():
    b = TextBrowser(
        pages=[Page(exists={SEL.oauth_authorize_button}, body_text="")],
        texts={SEL.logged_in_handle: "@testhandle"},
    )
    be = FakeBackend(oauth_connected=True)
    res = connect_oauth(b, be.job, _ctx(be), deadline=1000.0, now=Clock(), sleep=lambda s: None)
    assert not res.failed
    assert res.status_note == "oauth connected"
    assert SEL.oauth_authorize_button in b.clicks


def test_connect_refuses_wrong_session():
    b = TextBrowser(
        pages=[Page(exists={SEL.oauth_authorize_button})],
        texts={SEL.logged_in_handle: "someoneelse"},
    )
    be = FakeBackend()
    res = connect_oauth(b, be.job, _ctx(be), deadline=1000.0, now=Clock(), sleep=lambda s: None)
    assert res.failed
    assert "refusing to connect" in (res.error or "")
    assert SEL.oauth_authorize_button not in b.clicks  # never authorized the wrong account


def test_connect_fails_when_not_logged_in():
    b = TextBrowser(pages=[Page(exists=set())], texts={})
    be = FakeBackend()
    res = connect_oauth(b, be.job, _ctx(be), deadline=1000.0, now=Clock(), sleep=lambda s: None)
    assert res.failed
    assert "no logged-in session" in (res.error or "")


def test_connect_identity_mismatch_fails():
    b = TextBrowser(
        pages=[Page(exists={SEL.oauth_authorize_button})],
        texts={SEL.logged_in_handle: "testhandle"},
    )
    be = FakeBackend(oauth_connected=True, oauth_x_user_id="999")
    ctx = _ctx(be)
    ctx.result.x_user_id = "111"  # provisioned identity differs from the connected one
    res = connect_oauth(b, be.job, ctx, deadline=1000.0, now=Clock(), sleep=lambda s: None)
    assert res.failed
    assert "x_user_id" in (res.error or "")


def test_connect_times_out_if_backend_never_connects():
    b = TextBrowser(
        pages=[Page(exists={SEL.oauth_authorize_button})],
        texts={SEL.logged_in_handle: "testhandle"},
    )
    be = FakeBackend(oauth_connected=False)
    res = connect_oauth(b, be.job, _ctx(be), deadline=5.0, now=Clock(step=1.0), sleep=lambda s: None)
    assert res.failed
    assert "timed out" in (res.error or "")


def test_connect_captcha_then_cancel():
    b = TextBrowser(
        pages=[Page(exists={SEL.oauth_authorize_button}, body_text="arkose challenge")],
        texts={SEL.logged_in_handle: "testhandle"},
    )
    be = FakeBackend(control_continue_after=1, control_action="cancel")
    res = connect_oauth(b, be.job, _ctx(be), deadline=1000.0, now=Clock(), sleep=lambda s: None)
    assert res.failed
    assert "cancelled" in (res.error or "")
