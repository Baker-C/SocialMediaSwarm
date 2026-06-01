"""Account persistence (RavenDB)."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.account import AccountDocument, default_negative_semantics, default_system_prompt


def _strip_metadata(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not str(k).startswith("@")}


def document_to_account(doc: dict) -> AccountDocument:
    d = _strip_metadata(doc)
    if not d.get("negative_semantics"):
        d["negative_semantics"] = default_negative_semantics()
    return AccountDocument.model_validate(d)


def account_to_document(account: AccountDocument) -> dict:
    d = account.model_dump(exclude_none=True)
    d.pop("@metadata", None)
    if not d.get("system_prompt"):
        d["system_prompt"] = default_system_prompt(d["niche"])
    if not d.get("negative_semantics"):
        d["negative_semantics"] = default_negative_semantics()
    return d


class AccountRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def load(self, account_id: str) -> AccountDocument | None:
        doc_id = AccountDocument.document_id(account_id)
        raw = self.client.get_document(doc_id)
        if raw is None:
            return None
        return document_to_account(raw)

    def save(self, account: AccountDocument) -> None:
        doc_id = AccountDocument.document_id(account.account_id)
        self.client.put_document(doc_id, account_to_document(account), collection="Accounts")

    def list_active(self) -> list[AccountDocument]:
        rql = "from Accounts where status = 'active'"
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError:
            rql = "from @all where startsWith(id(), 'accounts/') and status = 'active'"
            rows = self.client.query(rql)
        return [document_to_account(r) for r in rows]

    def list_all_accounts(self) -> list[AccountDocument]:
        try:
            rows = self.client.query("from Accounts")
        except RavenDBHttpError:
            rows = self.client.query("from @all where startsWith(id(), 'accounts/')")
        return [document_to_account(r) for r in rows]

    def upsert_credentials(
        self,
        account_id: str,
        *,
        niche: str | None = None,
        twitter_handle: str | None = None,
        status: str | None = None,
        twitter_api_key_enc: str | None = None,
        twitter_api_secret_enc: str | None = None,
        twitter_access_token_enc: str | None = None,
        twitter_access_token_secret_enc: str | None = None,
        twitter_oauth2_access_token_enc: str | None = None,
        twitter_oauth2_refresh_token_enc: str | None = None,
        buffer_organization_id: str | None = None,
        buffer_channel_id: str | None = None,
        clear_twitter_oauth1: bool = False,
        clear_twitter_oauth2: bool = False,
    ) -> AccountDocument:
        existing = self.load(account_id)
        if existing is None:
            now = datetime.now(timezone.utc).isoformat()
            acc = AccountDocument(
                account_id=account_id,
                niche=niche or account_id,
                twitter_handle=twitter_handle or "",
                status=status or "active",
                system_prompt=default_system_prompt(niche or account_id),
                negative_semantics=default_negative_semantics(),
                twitter_api_key_enc=twitter_api_key_enc,
                twitter_api_secret_enc=twitter_api_secret_enc,
                twitter_access_token_enc=twitter_access_token_enc,
                twitter_access_token_secret_enc=twitter_access_token_secret_enc,
                twitter_oauth2_access_token_enc=twitter_oauth2_access_token_enc,
                twitter_oauth2_refresh_token_enc=twitter_oauth2_refresh_token_enc,
                buffer_organization_id=buffer_organization_id,
                buffer_channel_id=buffer_channel_id,
                registered_at=now,
                followers_when_registered=0,
            )
        else:
            data = existing.model_dump()
            if niche is not None:
                data["niche"] = niche
            if twitter_handle is not None:
                data["twitter_handle"] = twitter_handle
            if status is not None:
                data["status"] = status
            if twitter_api_key_enc is not None:
                data["twitter_api_key_enc"] = twitter_api_key_enc
            if twitter_api_secret_enc is not None:
                data["twitter_api_secret_enc"] = twitter_api_secret_enc
            if twitter_access_token_enc is not None:
                data["twitter_access_token_enc"] = twitter_access_token_enc
            if twitter_access_token_secret_enc is not None:
                data["twitter_access_token_secret_enc"] = twitter_access_token_secret_enc
            if twitter_oauth2_access_token_enc is not None:
                data["twitter_oauth2_access_token_enc"] = twitter_oauth2_access_token_enc
            if twitter_oauth2_refresh_token_enc is not None:
                data["twitter_oauth2_refresh_token_enc"] = twitter_oauth2_refresh_token_enc
            if clear_twitter_oauth1:
                data["twitter_api_key_enc"] = None
                data["twitter_api_secret_enc"] = None
                data["twitter_access_token_enc"] = None
                data["twitter_access_token_secret_enc"] = None
            if clear_twitter_oauth2:
                data["twitter_oauth2_access_token_enc"] = None
                data["twitter_oauth2_refresh_token_enc"] = None
            if buffer_organization_id is not None:
                data["buffer_organization_id"] = buffer_organization_id
            if buffer_channel_id is not None:
                data["buffer_channel_id"] = buffer_channel_id
            if data.get("registered_at") is None:
                data["registered_at"] = datetime.now(timezone.utc).isoformat()
            if data.get("followers_when_registered") is None:
                data["followers_when_registered"] = int(data.get("followers") or 0)
            acc = AccountDocument.model_validate(data)
        self.save(acc)
        return acc


def current_interval_slot_key() -> str:
    """Idempotency bucket for scheduled posts (aligned to ``post_interval_minutes``)."""
    interval = max(1, int(settings.post_interval_minutes))
    tz = ZoneInfo(settings.scheduler_timezone)
    now = datetime.now(tz)
    bucket_minute = (now.minute // interval) * interval
    slot_time = now.replace(minute=bucket_minute, second=0, microsecond=0)
    return slot_time.strftime("%Y-%m-%d-%H-%M")
