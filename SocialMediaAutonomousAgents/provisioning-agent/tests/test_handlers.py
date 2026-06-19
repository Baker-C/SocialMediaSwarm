from __future__ import annotations

from agent.handlers.billing import BillingHandler
from agent.handlers.captcha import CaptchaHandler
from agent.handlers.dev_agreement import DevAgreementHandler
from agent.handlers.dev_app import DevAppHandler
from agent.handlers.email_entry import EmailEntryHandler
from agent.handlers.email_verify import EmailVerifyHandler
from agent.handlers.key_capture import KeyCaptureHandler
from agent.handlers.name_handle import NameHandleHandler
from agent.handlers.password import PasswordHandler
from agent.handlers.phone_entry import PhoneEntryHandler
from agent.handlers.phone_verify import PhoneVerifyHandler
from agent.handlers.profile_setup import ProfileSetupHandler
from agent.selectors import SEL
from agent.types import AgentContext, ProvisioningJob
from tests.fakes import FakeBackend, FakeBrowser, Page, TextBrowser


def _ctx(job=None, backend=None, **kw):
    backend = backend or FakeBackend()
    job = job or backend.job
    return AgentContext(backend=backend, job=job, **kw)


def _browser(exists=None):
    return FakeBrowser([Page(exists=set(exists or []))])


def test_email_entry_fills_and_advances():
    b = _browser([SEL.email_input])
    ctx = _ctx()
    res = EmailEntryHandler().handle(b, ctx.job, ctx)
    assert (SEL.email_input, ctx.job.email) in b.fills
    assert SEL.next_button in b.clicks
    assert not res.failed


def test_password_generates_fills_and_stores():
    b = _browser([SEL.password_input])
    ctx = _ctx()
    res = PasswordHandler(gen=lambda: "PW-fixed-123").handle(b, ctx.job, ctx)
    assert ctx.result.password == "PW-fixed-123"
    assert (SEL.password_input, "PW-fixed-123") in b.fills
    assert not res.failed


def test_name_handle_happy_path():
    b = _browser([SEL.name_input, SEL.handle_input])
    ctx = _ctx()
    res = NameHandleHandler().handle(b, ctx.job, ctx)
    assert (SEL.name_input, ctx.job.display_name) in b.fills
    assert (SEL.handle_input, ctx.job.handle) in b.fills
    assert SEL.next_button in b.clicks
    assert not res.failed


def test_name_handle_taken_retries_with_alternate():
    b = _browser([SEL.name_input, SEL.handle_input])
    # first handle attempt shows the "taken" error, subsequent ones clear it
    state = {"calls": 0}
    orig_exists = b.exists

    def exists(sel):
        if sel == SEL.handle_taken_error:
            state["calls"] += 1
            return state["calls"] == 1  # taken only on first attempt
        return orig_exists(sel)

    b.exists = exists
    ctx = _ctx()
    res = NameHandleHandler().handle(b, ctx.job, ctx)
    assert not res.failed
    # original handle + one alternate were filled
    handle_fills = [v for (s, v) in b.fills if s == SEL.handle_input]
    assert handle_fills == [ctx.job.handle, f"{ctx.job.handle}1"]
    assert SEL.next_button in b.clicks


def test_name_handle_exhausts_retries():
    b = _browser([SEL.name_input, SEL.handle_input])
    b.dynamic_exists[SEL.handle_taken_error] = True  # always taken
    ctx = _ctx()
    res = NameHandleHandler().handle(b, ctx.job, ctx)
    assert res.failed
    assert SEL.next_button not in b.clicks


def test_email_verify_polls_and_fills():
    b = _browser([SEL.email_code_input])
    backend = FakeBackend(email_code="987654")
    ctx = _ctx(backend=backend)
    res = EmailVerifyHandler().handle(b, ctx.job, ctx)
    assert (SEL.email_code_input, "987654") in b.fills
    assert not res.failed


def test_email_verify_fails_without_code():
    b = _browser([SEL.email_code_input])
    ctx = _ctx(backend=FakeBackend(email_code=""))
    res = EmailVerifyHandler().handle(b, ctx.job, ctx)
    assert res.failed


def test_phone_entry_creates_phone_lazily():
    b = _browser([SEL.phone_input])
    backend = FakeBackend(phone="+15555551234")
    ctx = _ctx(backend=backend)
    res = PhoneEntryHandler().handle(b, ctx.job, ctx)
    assert (SEL.phone_input, "+15555551234") in b.fills
    assert not res.failed


def test_phone_verify_fills_sms_code():
    b = _browser([SEL.phone_code_input])
    ctx = _ctx(backend=FakeBackend(sms_code="424242"))
    res = PhoneVerifyHandler().handle(b, ctx.job, ctx)
    assert (SEL.phone_code_input, "424242") in b.fills
    assert not res.failed


def test_profile_setup_uploads_and_fills_bio():
    b = _browser([SEL.avatar_input, SEL.header_input, SEL.bio_input])
    ctx = _ctx(avatar_bytes=b"AV", header_bytes=b"HD")
    res = ProfileSetupHandler().handle(b, ctx.job, ctx)
    uploaded = {(s, fn) for (s, n, fn) in b.uploads}
    assert (SEL.avatar_input, "avatar.png") in uploaded
    assert (SEL.header_input, "header.png") in uploaded
    assert (SEL.bio_input, ctx.job.bio) in b.fills
    assert not res.failed


def test_dev_app_creates_app():
    b = _browser([SEL.dev_app_name_input])
    ctx = _ctx()
    res = DevAppHandler().handle(b, ctx.job, ctx)
    assert any(s == SEL.dev_app_name_input for (s, v) in b.fills)
    assert SEL.dev_app_create_button in b.clicks
    assert not res.failed


def test_dev_agreement_accepts():
    b = _browser([SEL.dev_agreement_checkbox, SEL.dev_agreement_accept_button])
    ctx = _ctx()
    res = DevAgreementHandler().handle(b, ctx.job, ctx)
    assert SEL.dev_agreement_checkbox in b.clicks
    assert SEL.dev_agreement_accept_button in b.clicks
    assert not res.failed


def test_billing_skips_when_no_card():
    b = _browser([SEL.card_number_input])
    job = ProvisioningJob(account_id="a", handle="h", display_name="d", bio="b", email="e@x.com", card=None)
    ctx = _ctx(job=job)
    res = BillingHandler().handle(b, ctx.job, ctx)
    assert res.advanced is False
    assert b.fills == []  # nothing entered
    assert b.clicks == []


def test_billing_fills_when_card_present():
    b = _browser([SEL.card_number_input])
    card = {"number": "4242", "exp": "12/30", "cvv": "123", "name": "Op"}
    job = ProvisioningJob(account_id="a", handle="h", display_name="d", bio="b", email="e@x.com", card=card)
    ctx = _ctx(job=job)
    res = BillingHandler().handle(b, ctx.job, ctx)
    assert (SEL.card_number_input, "4242") in b.fills
    assert SEL.billing_submit_button in b.clicks
    assert not res.failed


def test_key_capture_populates_result():
    texts = {
        SEL.api_key_value: "KEY",
        SEL.api_secret_value: "SECRET",
        SEL.bearer_token_value: "BEARER",
        SEL.x_user_id_value: "uid_1",
        SEL.dev_app_id_value: "app_1",
    }
    b = TextBrowser([Page(exists={SEL.api_key_value, SEL.x_user_id_value, SEL.dev_app_id_value})], texts=texts)
    ctx = _ctx()
    res = KeyCaptureHandler().handle(b, ctx.job, ctx)
    assert ctx.result.dev_api_key == "KEY"
    assert ctx.result.dev_api_secret == "SECRET"
    assert ctx.result.dev_bearer_token == "BEARER"
    assert ctx.result.x_user_id == "uid_1"
    assert ctx.result.dev_app_id == "app_1"
    assert not res.failed


def test_key_capture_fails_without_key():
    b = TextBrowser([Page(exists=set())], texts={})
    ctx = _ctx()
    res = KeyCaptureHandler().handle(b, ctx.job, ctx)
    assert res.failed


def test_captcha_returns_needs_user_without_acting():
    b = _browser([SEL.captcha_iframe])
    ctx = _ctx()
    res = CaptchaHandler().handle(b, ctx.job, ctx)
    assert res.needs_user is True
    assert res.advanced is False
    assert b.fills == [] and b.clicks == [] and b.uploads == []
