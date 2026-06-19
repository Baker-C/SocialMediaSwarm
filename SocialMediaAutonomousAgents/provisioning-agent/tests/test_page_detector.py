from __future__ import annotations

from agent.page_state import PageDetector, PageState
from agent.selectors import SEL
from tests.fakes import FakeBrowser, Page


def _detect(exists=None, body=""):
    b = FakeBrowser([Page(exists=set(exists or []), body_text=body)])
    return PageDetector().detect(b)


def test_email_entry():
    assert _detect([SEL.email_input]) == PageState.EMAIL_ENTRY


def test_password():
    assert _detect([SEL.password_input]) == PageState.PASSWORD


def test_name_handle():
    assert _detect([SEL.handle_input, SEL.name_input]) == PageState.NAME_HANDLE


def test_email_verify():
    assert _detect([SEL.email_code_input]) == PageState.EMAIL_VERIFY


def test_phone_entry_vs_verify_precedence():
    assert _detect([SEL.phone_input]) == PageState.PHONE_ENTRY
    assert _detect([SEL.phone_code_input]) == PageState.PHONE_VERIFY


def test_profile_setup():
    assert _detect([SEL.avatar_input]) == PageState.PROFILE_SETUP


def test_dev_app():
    assert _detect([SEL.dev_app_name_input]) == PageState.DEV_APP


def test_dev_agreement():
    assert _detect([SEL.dev_agreement_accept_button]) == PageState.DEV_AGREEMENT


def test_billing():
    assert _detect([SEL.card_number_input]) == PageState.BILLING


def test_key_capture():
    assert _detect([SEL.api_key_value]) == PageState.KEY_CAPTURE


def test_success_marker_and_text():
    assert _detect([SEL.success_marker]) == PageState.SUCCESS
    assert _detect(body="You're all set!") == PageState.SUCCESS


def test_unknown():
    assert _detect([]) == PageState.UNKNOWN


def test_captcha_iframe_detected():
    assert _detect([SEL.captcha_iframe]) == PageState.CAPTCHA


def test_captcha_text_detected():
    assert _detect(body="please complete the arkose challenge") == PageState.CAPTCHA


def test_captcha_overlay_takes_precedence_over_page():
    # CAPTCHA overlay on top of the email page must win.
    assert _detect([SEL.captcha_iframe, SEL.email_input]) == PageState.CAPTCHA
