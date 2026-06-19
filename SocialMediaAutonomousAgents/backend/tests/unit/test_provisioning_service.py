"""ProvisioningService with injected fake repo + fake secrets."""

from __future__ import annotations

import pytest

from app.api.routes.provisioning_types import ProvisioningResult
from app.models.account import AccountDocument
from app.services import provisioning_service as mod
from app.services.account_secrets_service import AccountSecrets
from app.services.provisioning_service import ProvisioningService


class FakeRepo:
    def __init__(self, acc: AccountDocument | None = None) -> None:
        self.acc = acc
        self.saved: list[AccountDocument] = []

    def load(self, account_id: str) -> AccountDocument | None:
        return self.acc

    def save(self, acc: AccountDocument) -> None:
        self.acc = acc
        self.saved.append(acc)


class FakeSecrets:
    def __init__(self, store: dict | None = None) -> None:
        self.store: dict[str, dict] = store or {}
        self.upserts: list[tuple[str, dict]] = []

    def get(self, account_id: str) -> AccountSecrets | None:
        data = self.store.get(account_id)
        return AccountSecrets(account_id=account_id, **data) if data is not None else None

    def upsert(self, account_id: str, **fields) -> None:
        self.upserts.append((account_id, fields))
        self.store.setdefault(account_id, {}).update(fields)


def _account(status: str = "draft") -> AccountDocument:
    acc = AccountDocument(account_id="aid", profile={"twitter_handle": "h"})
    acc.provisioning.status = status  # type: ignore[assignment]
    acc.provisioning.display_name = "Name"
    acc.provisioning.bio = "Bio"
    return acc


def test_start_flips_status_and_bumps_attempt() -> None:
    repo = FakeRepo(_account("draft"))
    svc = ProvisioningService(repo=repo, secrets=FakeSecrets())

    svc.start("aid")

    assert repo.acc.provisioning.status == "in_progress"
    assert repo.acc.provisioning.attempt_count == 1
    assert repo.acc.provisioning.started_at is not None
    assert repo.saved


def test_start_unknown_account_raises_lookup() -> None:
    svc = ProvisioningService(repo=FakeRepo(None), secrets=FakeSecrets())
    with pytest.raises(LookupError):
        svc.start("aid")


def test_start_rejects_double_start() -> None:
    svc = ProvisioningService(repo=FakeRepo(_account("in_progress")), secrets=FakeSecrets())
    with pytest.raises(ValueError, match="already provisioning"):
        svc.start("aid")


def test_store_result_upserts_secrets_and_completes() -> None:
    repo = FakeRepo(_account("in_progress"))
    secrets = FakeSecrets()
    svc = ProvisioningService(repo=repo, secrets=secrets)

    svc.store_result("aid", ProvisioningResult(x_user_id="x1", dev_api_key="k"))

    assert repo.acc.provisioning.status == "complete"
    assert repo.acc.provisioning.x_user_id == "x1"
    assert repo.acc.provisioning.completed_at is not None
    assert any(f.get("dev_api_key") == "k" for _, f in secrets.upserts)


def test_build_job_uses_prestored_email_no_lazy_import() -> None:
    repo = FakeRepo(_account("in_progress"))
    secrets = FakeSecrets({"aid": {"disposable_email": "a@b.c"}})
    svc = ProvisioningService(repo=repo, secrets=secrets)

    job = svc.build_job("aid")

    assert job.email == "a@b.c"
    assert job.handle == "h"
    assert job.display_name == "Name"
    # no inbox creation happened
    assert secrets.upserts == []


def test_build_job_creates_inbox_lazily(monkeypatch) -> None:
    repo = FakeRepo(_account("in_progress"))
    secrets = FakeSecrets()
    svc = ProvisioningService(repo=repo, secrets=secrets)

    class FakeClient:
        def create_inbox(self, account_id: str) -> str:
            return "fresh@inbox.test"

    import sys
    import types

    fake_mod = types.ModuleType("app.infrastructure.disposable_email_client")
    fake_mod.DisposableEmailClient = FakeClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.infrastructure.disposable_email_client", fake_mod)

    job = svc.build_job("aid")

    assert job.email == "fresh@inbox.test"
    assert any(f.get("disposable_email") == "fresh@inbox.test" for _, f in secrets.upserts)


def test_build_job_card_off_then_on(monkeypatch) -> None:
    repo = FakeRepo(_account("in_progress"))
    secrets = FakeSecrets({"aid": {"disposable_email": "a@b.c"}})
    svc = ProvisioningService(repo=repo, secrets=secrets)

    for field in ("number", "exp", "cvv", "name"):
        monkeypatch.setattr(mod.settings, f"provisioning_card_{field}", "")
    assert svc.build_job("aid").card is None

    monkeypatch.setattr(mod.settings, "provisioning_card_number", "4111")
    monkeypatch.setattr(mod.settings, "provisioning_card_exp", "12/30")
    monkeypatch.setattr(mod.settings, "provisioning_card_cvv", "123")
    monkeypatch.setattr(mod.settings, "provisioning_card_name", "Op")
    card = svc.build_job("aid").card
    assert card == {"number": "4111", "exp": "12/30", "cvv": "123", "name": "Op"}


def test_set_then_get_control_clears() -> None:
    svc = ProvisioningService(repo=FakeRepo(_account()), secrets=FakeSecrets())
    svc.set_control("aid", "continue")
    assert svc.get_control("aid") == "continue"
    assert svc.get_control("aid") is None
