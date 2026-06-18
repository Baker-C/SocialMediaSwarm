from __future__ import annotations

from ..page_state import PageState
from ..selectors import SEL
from ..types import AgentContext, HandlerResult, ProvisioningJob
from ..browser_port import BrowserPort


class DevAgreementHandler:
    state = PageState.DEV_AGREEMENT

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult:
        if b.exists(SEL.dev_agreement_checkbox):
            b.click(SEL.dev_agreement_checkbox)
        b.click(SEL.dev_agreement_accept_button)
        return HandlerResult(status_note="accepted dev agreement")
