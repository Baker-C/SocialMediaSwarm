from __future__ import annotations

from ..page_state import PageState
from ..selectors import SEL
from ..types import AgentContext, HandlerResult, ProvisioningJob
from ..browser_port import BrowserPort


class BillingHandler:
    state = PageState.BILLING

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult:
        if job.card is None:
            # Free-tier path: no card configured -> nothing to fill here.
            return HandlerResult(advanced=False, status_note="billing skipped (no card)")
        card = job.card
        b.fill(SEL.card_number_input, str(card.get("number", "")))
        b.fill(SEL.card_exp_input, str(card.get("exp", "")))
        b.fill(SEL.card_cvv_input, str(card.get("cvv", "")))
        if card.get("name"):
            b.fill(SEL.card_name_input, str(card["name"]))
        b.click(SEL.billing_submit_button)
        return HandlerResult(status_note="entered billing")
