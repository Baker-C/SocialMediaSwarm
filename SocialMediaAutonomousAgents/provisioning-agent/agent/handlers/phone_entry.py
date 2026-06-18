from __future__ import annotations

from ..page_state import PageState
from ..selectors import SEL
from ..types import AgentContext, HandlerResult, ProvisioningJob
from ..browser_port import BrowserPort


class PhoneEntryHandler:
    state = PageState.PHONE_ENTRY

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult:
        # Phone is created lazily, only when this page actually appears.
        phone = ctx.backend.create_phone()
        if not phone:
            return HandlerResult(failed=True, error="could not provision phone", advanced=False)
        b.fill(SEL.phone_input, phone)
        b.click(SEL.next_button)
        return HandlerResult(status_note="entered phone")
