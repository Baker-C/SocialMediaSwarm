from __future__ import annotations

from ..page_state import PageState
from ..selectors import SEL
from ..types import AgentContext, HandlerResult, ProvisioningJob
from ..browser_port import BrowserPort


class ProfileSetupHandler:
    state = PageState.PROFILE_SETUP

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult:
        if ctx.avatar_bytes is not None:
            b.upload(SEL.avatar_input, ctx.avatar_bytes, "avatar.png")
        if ctx.header_bytes is not None:
            b.upload(SEL.header_input, ctx.header_bytes, "header.png")
        if job.bio:
            b.fill(SEL.bio_input, job.bio)
        b.click(SEL.profile_save_button)
        return HandlerResult(status_note="set up profile")
