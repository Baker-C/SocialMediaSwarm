from __future__ import annotations

from ..page_state import PageState
from ..selectors import SEL
from ..types import AgentContext, HandlerResult, ProvisioningJob
from ..browser_port import BrowserPort


class EmailEntryHandler:
    state = PageState.EMAIL_ENTRY

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult:
        b.fill(SEL.email_input, job.email)
        b.click(SEL.next_button)
        return HandlerResult(status_note="filled email")
