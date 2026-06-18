"""Test doubles: FakeBrowser (scripted pages) + FakeBackend.

No playwright, no network. FakeBrowser satisfies the BrowserPort protocol structurally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agent.selectors import SEL
from agent.types import ProvisioningJob, ProvisioningResult


@dataclass
class Page:
    """One scripted page snapshot.

    exists: selectors present on this page.
    body_text: whole-page text (for CAPTCHA/success token checks).
    """

    exists: set
    body_text: str = ""


class FakeBrowser:
    """Scripted browser. Advances to the next page when the generic 'next' button is clicked.

    `pages` is a list of Page snapshots; the browser sits on pages[index]. Clicking
    SEL.next_button / SEL.profile_save_button / SEL.dev_app_create_button /
    SEL.dev_agreement_accept_button / SEL.billing_submit_button advances the script.
    """

    ADVANCE_SELECTORS = {
        SEL.next_button,
        SEL.profile_save_button,
        SEL.dev_app_create_button,
        SEL.dev_agreement_accept_button,
        SEL.billing_submit_button,
    }

    def __init__(self, pages: list, *, start_url: str = "about:blank") -> None:
        self.pages = pages
        self.index = 0
        self._url = start_url
        self.fills: list = []  # (selector, value)
        self.clicks: list = []  # selector
        self.uploads: list = []  # (selector, len(data), filename)
        self.gotos: list = []
        self.storage_state_value = '{"cookies": []}'
        # selectors that should report exists() True on demand for the CURRENT page
        # beyond the scripted page (used to toggle inline errors in handler tests)
        self.dynamic_exists: dict = {}

    # ---- BrowserPort ----
    def goto(self, url: str) -> None:
        self.gotos.append(url)
        self._url = url

    def url(self) -> str:
        return self._url

    def _page(self) -> Page:
        if self.index >= len(self.pages):
            return Page(exists=set(), body_text="")
        return self.pages[self.index]

    def exists(self, selector: str) -> bool:
        if selector in self.dynamic_exists:
            return self.dynamic_exists[selector]
        return selector in self._page().exists

    def text(self, selector: str) -> str:
        from agent.selectors import BODY

        if selector == BODY:
            return self._page().body_text
        return ""  # handlers that read field text are exercised via dynamic override in tests

    def fill(self, selector: str, value: str) -> None:
        self.fills.append((selector, value))

    def click(self, selector: str) -> None:
        self.clicks.append(selector)
        if selector in self.ADVANCE_SELECTORS:
            self.index += 1

    def upload(self, selector: str, data: bytes, filename: str) -> None:
        self.uploads.append((selector, len(data), filename))

    def wait_for(self, selector: str, timeout_ms: int = 15000) -> bool:
        return self.exists(selector)

    def storage_state(self) -> str:
        return self.storage_state_value


class TextBrowser(FakeBrowser):
    """FakeBrowser variant that can return scripted text for arbitrary selectors.

    Used by key_capture tests where handlers read selector text values.
    """

    def __init__(self, pages: list, texts: Optional[dict] = None) -> None:
        super().__init__(pages)
        self.texts = texts or {}

    def text(self, selector: str) -> str:
        if selector in self.texts:
            return self.texts[selector]
        return super().text(selector)


@dataclass
class FakeBackend:
    """Records status pushes; returns a canned job; scripts control polling + captures result."""

    job: ProvisioningJob = field(
        default_factory=lambda: ProvisioningJob(
            account_id="acc_1",
            handle="testhandle",
            display_name="Test User",
            bio="hello",
            email="t@example.com",
        )
    )
    email_code: str = "111111"
    sms_code: str = "222222"
    phone: str = "+15555550100"
    control_continue_after: int = 2  # poll_control returns "continue" after N polls
    control_action: str = "continue"  # the action to return once ready ("continue"/"cancel")

    statuses: list = field(default_factory=list)  # list of dicts
    result: Optional[ProvisioningResult] = None
    _control_polls: int = 0

    # ---- BackendPort ----
    def fetch_job(self) -> ProvisioningJob:
        return self.job

    def push_status(self, *, status, current_page="", note=None, x_user_id="", dev_app_id="") -> None:
        self.statuses.append(
            {
                "status": status,
                "current_page": current_page,
                "note": note,
                "x_user_id": x_user_id,
                "dev_app_id": dev_app_id,
            }
        )

    def poll_control(self) -> str:
        self._control_polls += 1
        if self._control_polls >= self.control_continue_after:
            return self.control_action
        return ""

    def post_result(self, result: ProvisioningResult) -> None:
        self.result = result

    def fetch_email_code(self) -> str:
        return self.email_code

    def create_phone(self) -> str:
        return self.phone

    def fetch_sms_code(self) -> str:
        return self.sms_code

    def fetch_asset(self, asset_id: str) -> bytes:
        return b"\x89PNG-fake"
