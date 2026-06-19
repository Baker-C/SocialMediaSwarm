from __future__ import annotations

from ..page_state import PageState
from ..selectors import SEL
from ..types import AgentContext, HandlerResult, ProvisioningJob
from ..browser_port import BrowserPort


class DevAppHandler:
    state = PageState.DEV_APP

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult:
        app_name = f"{job.handle}-app" if job.handle else "auto-app"
        b.fill(SEL.dev_app_name_input, app_name)
        b.click(SEL.dev_app_create_button)
        return HandlerResult(status_note="created dev app")
