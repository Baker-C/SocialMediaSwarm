"""Entrypoint: python -m agent.run

Wires the real PlaywrightBrowser + BackendClient, fetches the job and media bytes, runs
the loop, and posts the result. On exception, pushes status='failed'.
"""
from __future__ import annotations

from .backend_client import BackendClient
from .browser_port import PlaywrightBrowser
from .config import load_config
from .orchestrator import run_provisioning
from .types import AgentContext


def main() -> int:
    cfg = load_config()
    backend = BackendClient(cfg.backend_url, cfg.agent_token, cfg.account_id)

    try:
        job = backend.fetch_job()
        ctx = AgentContext(backend=backend, job=job)

        if job.avatar_asset_id:
            ctx.avatar_bytes = backend.fetch_asset(job.avatar_asset_id)
        if job.header_asset_id:
            ctx.header_bytes = backend.fetch_asset(job.header_asset_id)

        browser = PlaywrightBrowser(cfg.chrome_profile_dir)
        try:
            run_provisioning(
                browser,
                job,
                ctx,
                deadline_seconds=cfg.deadline_seconds,
                max_unknown_settles=cfg.max_unknown_settles,
                poll_interval_seconds=cfg.poll_interval_seconds,
            )
        finally:
            browser.close()
        return 0
    except Exception as exc:  # noqa: BLE001 — surface any failure to the backend
        backend.push_status(status="failed", current_page="failed", note=f"agent crashed: {exc!r}")
        raise
    finally:
        backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
