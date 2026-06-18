from __future__ import annotations

import secrets
import string

from ..page_state import PageState
from ..selectors import SEL
from ..types import AgentContext, HandlerResult, ProvisioningJob
from ..browser_port import BrowserPort

_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_"


def generate_password(length: int = 20) -> str:
    """Strong random password. Exposed for unit testing/determinism via injection."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


class PasswordHandler:
    state = PageState.PASSWORD

    def __init__(self, gen=generate_password) -> None:
        self._gen = gen

    def handle(self, b: BrowserPort, job: ProvisioningJob, ctx: AgentContext) -> HandlerResult:
        pw = self._gen()
        ctx.result.password = pw  # stored on result -> returned to backend
        b.fill(SEL.password_input, pw)
        b.click(SEL.next_button)
        return HandlerResult(status_note="set password")
