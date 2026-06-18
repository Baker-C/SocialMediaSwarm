from __future__ import annotations

from ..page_state import PageState
from ..selectors import SEL
from ..types import AgentContext, HandlerResult, ProvisioningJob
from ..browser_port import BrowserPort


class EmailVerifyHandler:
    state = PageState.EMAIL_VERIFY

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult:
        code = ctx.backend.fetch_email_code()
        if not code:
            return HandlerResult(failed=True, error="no email verification code", advanced=False)
        b.fill(SEL.email_code_input, code)
        b.click(SEL.next_button)
        return HandlerResult(status_note="entered email code")
