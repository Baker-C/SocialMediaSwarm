"""Handler protocol + HandlerResult re-export."""
from __future__ import annotations

from typing import Protocol

from ..browser_port import BrowserPort
from ..page_state import PageState
from ..types import AgentContext, HandlerResult, ProvisioningJob

__all__ = ["Handler", "HandlerResult", "BrowserPort", "PageState", "AgentContext", "ProvisioningJob"]


class Handler(Protocol):
    state: PageState

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult: ...
