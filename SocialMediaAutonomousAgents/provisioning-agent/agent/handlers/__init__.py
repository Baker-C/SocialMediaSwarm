"""Ordered HANDLERS registry, keyed by PageState.

One module per page. Adding/replacing a page is local to its module + this registry.
"""
from __future__ import annotations

from ..page_state import PageState
from .base import Handler, HandlerResult
from .billing import BillingHandler
from .captcha import CaptchaHandler
from .dev_agreement import DevAgreementHandler
from .dev_app import DevAppHandler
from .email_entry import EmailEntryHandler
from .email_verify import EmailVerifyHandler
from .key_capture import KeyCaptureHandler
from .name_handle import NameHandleHandler
from .password import PasswordHandler
from .phone_entry import PhoneEntryHandler
from .phone_verify import PhoneVerifyHandler
from .profile_setup import ProfileSetupHandler

# Ordered by the typical flow sequence (registry is a dict; order documents intent).
HANDLERS: "dict[PageState, Handler]" = {
    PageState.EMAIL_ENTRY: EmailEntryHandler(),
    PageState.PASSWORD: PasswordHandler(),
    PageState.NAME_HANDLE: NameHandleHandler(),
    PageState.EMAIL_VERIFY: EmailVerifyHandler(),
    PageState.PHONE_ENTRY: PhoneEntryHandler(),
    PageState.PHONE_VERIFY: PhoneVerifyHandler(),
    PageState.PROFILE_SETUP: ProfileSetupHandler(),
    PageState.DEV_APP: DevAppHandler(),
    PageState.DEV_AGREEMENT: DevAgreementHandler(),
    PageState.BILLING: BillingHandler(),
    PageState.KEY_CAPTURE: KeyCaptureHandler(),
    PageState.CAPTCHA: CaptchaHandler(),
}

__all__ = ["HANDLERS", "Handler", "HandlerResult"]
