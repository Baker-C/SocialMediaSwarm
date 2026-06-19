from __future__ import annotations

from ..page_state import PageState
from ..selectors import SEL
from ..types import AgentContext, HandlerResult, ProvisioningJob
from ..browser_port import BrowserPort


class KeyCaptureHandler:
    state = PageState.KEY_CAPTURE

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult:
        ctx.result.dev_api_key = b.text(SEL.api_key_value) or None
        ctx.result.dev_api_secret = b.text(SEL.api_secret_value) or None
        ctx.result.dev_bearer_token = b.text(SEL.bearer_token_value) or None
        if b.exists(SEL.x_user_id_value):
            ctx.result.x_user_id = b.text(SEL.x_user_id_value)
        if b.exists(SEL.dev_app_id_value):
            ctx.result.dev_app_id = b.text(SEL.dev_app_id_value)

        if not ctx.result.dev_api_key:
            return HandlerResult(failed=True, error="could not capture API key", advanced=False)
        # Advance off the key page (continue button reuses the generic next selector).
        b.click(SEL.next_button)
        return HandlerResult(status_note="captured dev keys")
