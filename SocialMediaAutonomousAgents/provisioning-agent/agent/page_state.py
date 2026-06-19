"""PageState enum + PageDetector.

Detection is DOM-state-based (not URL-based): X signup is a single reactive flow.
CAPTCHA is checked FIRST because the FunCaptcha overlay can cover any page.
"""
from __future__ import annotations

from enum import Enum
from typing import Callable, List, Tuple

from .browser_port import BrowserPort
from .selectors import BODY, SEL, TXT


class PageState(str, Enum):
    EMAIL_ENTRY = "email_entry"
    PASSWORD = "password"
    NAME_HANDLE = "name_handle"
    EMAIL_VERIFY = "email_verify"
    PHONE_ENTRY = "phone_entry"
    PHONE_VERIFY = "phone_verify"
    PROFILE_SETUP = "profile_setup"
    DEV_APP = "dev_app"
    DEV_AGREEMENT = "dev_agreement"
    BILLING = "billing"
    KEY_CAPTURE = "key_capture"
    CAPTCHA = "captcha"
    SUCCESS = "success"
    UNKNOWN = "unknown"


Probe = Callable[[BrowserPort], bool]

# Ordered (PageState, probe) signals. Order matters: earlier wins. SUCCESS and the
# key-capture page are checked before generic input pages so a terminal page is not
# mistaken for an earlier one. CAPTCHA is handled out-of-band (see detect()).
SIGNALS: List[Tuple[PageState, Probe]] = [
    (PageState.SUCCESS, lambda b: b.exists(SEL.success_marker) or TXT.success in b.text(BODY).lower()),
    (PageState.KEY_CAPTURE, lambda b: b.exists(SEL.api_key_value)),
    (PageState.BILLING, lambda b: b.exists(SEL.billing_root) or b.exists(SEL.card_number_input)),
    (PageState.DEV_AGREEMENT, lambda b: b.exists(SEL.dev_agreement_root) or b.exists(SEL.dev_agreement_accept_button)),
    (PageState.DEV_APP, lambda b: b.exists(SEL.dev_app_root) or b.exists(SEL.dev_app_name_input)),
    (PageState.PROFILE_SETUP, lambda b: b.exists(SEL.avatar_input) or b.exists(SEL.bio_input)),
    (PageState.PHONE_VERIFY, lambda b: b.exists(SEL.phone_code_input)),
    (PageState.PHONE_ENTRY, lambda b: b.exists(SEL.phone_input)),
    (PageState.EMAIL_VERIFY, lambda b: b.exists(SEL.email_code_input)),
    (PageState.NAME_HANDLE, lambda b: b.exists(SEL.handle_input) or b.exists(SEL.name_input)),
    (PageState.PASSWORD, lambda b: b.exists(SEL.password_input)),
    (PageState.EMAIL_ENTRY, lambda b: b.exists(SEL.email_input)),
]


class PageDetector:
    def detect(self, b: BrowserPort) -> PageState:
        # CAPTCHA first: it can overlay any page.
        if b.exists(SEL.captcha_iframe) or TXT.captcha in b.text(BODY).lower():
            return PageState.CAPTCHA
        for state, probe in SIGNALS:
            if probe(b):
                return state
        return PageState.UNKNOWN
