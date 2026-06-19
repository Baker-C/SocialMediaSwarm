from __future__ import annotations

from ..page_state import PageState
from ..selectors import SEL
from ..types import AgentContext, HandlerResult, ProvisioningJob
from ..browser_port import BrowserPort

MAX_HANDLE_RETRIES = 5


def _alternate_handle(handle: str, attempt: int) -> str:
    return f"{handle}{attempt}"


class NameHandleHandler:
    state = PageState.NAME_HANDLE

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult:
        b.fill(SEL.name_input, job.display_name)

        handle = job.handle
        for attempt in range(1, MAX_HANDLE_RETRIES + 1):
            b.fill(SEL.handle_input, handle)
            if not b.exists(SEL.handle_taken_error):
                b.click(SEL.next_button)
                note = "filled name+handle" if attempt == 1 else f"filled name+handle (alt #{attempt})"
                return HandlerResult(status_note=note)
            # handle taken -> try an alternate (bounded)
            handle = _alternate_handle(job.handle, attempt)

        return HandlerResult(failed=True, error="handle unavailable after retries", advanced=False)
