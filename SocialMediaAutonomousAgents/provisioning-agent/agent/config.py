"""Agent configuration, read from environment variables.

Self-contained: no import of the backend. The agent is a stateless executor that gets
everything else (the job, disposable creds) from the backend over HTTP.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

X_SIGNUP_URL = "https://x.com/i/flow/signup"


@dataclass(frozen=True)
class AgentConfig:
    backend_url: str
    agent_token: str
    chrome_profile_dir: str
    account_id: str

    # Bounds for the orchestrator loop. Defaults are sane; overridable via env for tests/ops.
    deadline_seconds: int = 1800
    max_unknown_settles: int = 5
    poll_interval_seconds: float = 2.0


def load_config(env: dict[str, str] | None = None) -> AgentConfig:
    e = env if env is not None else os.environ
    missing = [
        k
        for k in ("BACKEND_URL", "PROVISIONING_AGENT_TOKEN", "CHROME_PROFILE_DIR", "ACCOUNT_ID")
        if not e.get(k)
    ]
    if missing:
        raise RuntimeError(f"missing required env vars: {', '.join(missing)}")
    return AgentConfig(
        backend_url=e["BACKEND_URL"].rstrip("/"),
        agent_token=e["PROVISIONING_AGENT_TOKEN"],
        chrome_profile_dir=e["CHROME_PROFILE_DIR"],
        account_id=e["ACCOUNT_ID"],
        deadline_seconds=int(e.get("PROVISIONING_DEADLINE_SECONDS", "1800")),
        max_unknown_settles=int(e.get("PROVISIONING_MAX_UNKNOWN_SETTLES", "5")),
        poll_interval_seconds=float(e.get("PROVISIONING_POLL_INTERVAL_SECONDS", "2.0")),
    )
