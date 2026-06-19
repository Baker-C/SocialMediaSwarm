"""Orchestration broker between the dashboard and the local provisioning agent.

Owns no browser: it reads/writes the AccountProvisioning sub-doc (progress) and
AccountSecrets (outcomes), and carries a transient control flag the agent polls
during the FunCaptcha pause.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.api.routes.provisioning_types import ProvisioningJob, ProvisioningResult
from app.core.config import settings
from app.services.account_repository import AccountRepository
from app.services.account_secrets_service import AccountSecretsService


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProvisioningService:
    def __init__(
        self,
        repo: AccountRepository | None = None,
        secrets: AccountSecretsService | None = None,
    ) -> None:
        self.repo = repo or AccountRepository()
        self.secrets = secrets or AccountSecretsService()
        # Transient, in-memory control flags keyed by account_id (off any public view).
        self._control: dict[str, str] = {}

    def start(self, account_id: str) -> None:
        acc = self.repo.load(account_id)
        if acc is None:
            raise LookupError(account_id)
        if acc.provisioning.status not in ("draft", "failed", "cancelled"):
            raise ValueError(f"already provisioning (status={acc.provisioning.status})")
        acc.provisioning.status = "in_progress"
        acc.provisioning.attempt_count += 1
        acc.provisioning.error_message = None
        acc.provisioning.started_at = _now()
        self.repo.save(acc)

    def update_status(
        self,
        account_id: str,
        *,
        status: str,
        current_page: str = "",
        note: str | None = None,
        x_user_id: str = "",
        dev_app_id: str = "",
    ) -> None:
        acc = self.repo.load(account_id)
        if acc is None:
            raise LookupError(account_id)
        acc.provisioning.status = status  # type: ignore[assignment]
        if current_page:
            acc.provisioning.current_page = current_page
        if note:
            acc.provisioning.step_log.append(note)
        if x_user_id:
            acc.provisioning.x_user_id = x_user_id
        if dev_app_id:
            acc.provisioning.dev_app_id = dev_app_id
        if status == "complete":
            acc.provisioning.completed_at = _now()
        self.repo.save(acc)

    def build_job(self, account_id: str) -> ProvisioningJob:
        """Spec + disposable creds + card the agent needs. Creates an inbox lazily."""
        acc = self.repo.load(account_id)
        if acc is None:
            raise LookupError(account_id)
        sec = self.secrets.get(account_id)
        email = sec.disposable_email if sec else None
        if not email:
            # Lazy import: this client ships in a LATER unit and must not be imported
            # at module top level (keeps `import app.main` clean until then).
            from app.infrastructure.disposable_email_client import DisposableEmailClient

            email = DisposableEmailClient().create_inbox(account_id)
            self.secrets.upsert(account_id, disposable_email=email)
        card = settings.provisioning_card
        return ProvisioningJob(
            account_id=account_id,
            handle=acc.profile.twitter_handle,
            display_name=acc.provisioning.display_name,
            bio=acc.provisioning.bio,
            avatar_asset_id=acc.provisioning.images.avatar_asset_id,
            header_asset_id=acc.provisioning.images.header_asset_id,
            email=email,
            card=card,
        )

    def store_result(self, account_id: str, result: ProvisioningResult) -> None:
        self.secrets.upsert(
            account_id,
            password=result.password,
            session_cookies=result.session_cookies,
            dev_api_key=result.dev_api_key,
            dev_api_secret=result.dev_api_secret,
            dev_bearer_token=result.dev_bearer_token,
            updated_at=_now(),
        )
        self.update_status(
            account_id,
            status="complete",
            x_user_id=result.x_user_id,
            dev_app_id=result.dev_app_id,
            note="provisioning complete",
        )

    # ── control flag for the FunCaptcha pause (poll target for the agent) ──
    def set_control(self, account_id: str, action: str) -> None:
        self._control[account_id] = action

    def get_control(self, account_id: str) -> str | None:
        """Return and consume (clear) the pending control action, if any."""
        return self._control.pop(account_id, None)
