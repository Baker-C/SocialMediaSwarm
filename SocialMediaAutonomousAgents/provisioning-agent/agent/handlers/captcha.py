from __future__ import annotations

from ..page_state import PageState
from ..types import AgentContext, HandlerResult, ProvisioningJob
from ..browser_port import BrowserPort


class CaptchaHandler:
    """Detect-only. Signals a pause; the operator solves the FunCaptcha manually."""

    state = PageState.CAPTCHA

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult:
        return HandlerResult(advanced=False, needs_user=True, status_note="awaiting CAPTCHA")
