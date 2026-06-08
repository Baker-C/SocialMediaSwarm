"""Account persistence (RavenDB)."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.infrastructure.ravendb_http import RavenDBHttpClient, RavenDBHttpError, get_ravendb_client
from app.models.account import (
    AccountDocument,
    AccountPostingState,
    AccountProfile,
    AccountVoice,
    default_negative_semantics,
    default_system_prompt,
)


def _strip_metadata(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not str(k).startswith("@")}


def normalize_account_document(raw: dict) -> dict:
    """Map legacy flat account keys into nested profile/voice/posting groups."""
    d = _strip_metadata(raw)
    profile = dict(d.get("profile") or {})
    voice = dict(d.get("voice") or {})
    posting = dict(d.get("posting") or {})

    profile.setdefault("niche", d.get("niche") or d.get("account_id") or "")
    profile.setdefault("twitter_handle", d.get("twitter_handle") or "")
    profile.setdefault("status", d.get("status") or "active")
    profile.setdefault("followers", int(d.get("followers") or 0))
    profile.setdefault("posts_total", int(d.get("posts_total") or 0))
    profile.setdefault("registered_at", d.get("registered_at"))
    profile.setdefault("followers_when_registered", d.get("followers_when_registered"))
    sq = profile.get("search_queries")
    if sq is None:
        sq = d.get("search_queries")
    profile["search_queries"] = list(sq or [])

    voice.setdefault("system_prompt", d.get("system_prompt") or "")
    voice.setdefault("personality", d.get("personality") or "")
    voice.setdefault("voice_version_hash", d.get("voice_version_hash"))
    voice.setdefault("voice_version_seq", int(d.get("voice_version_seq") or 1))
    voice.setdefault("voice_version_label", d.get("voice_version_label") or "v1")
    neg = voice.get("negative_semantics")
    if not neg:
        neg = d.get("negative_semantics")
    voice["negative_semantics"] = list(neg) if neg else default_negative_semantics()

    slot = posting.get("last_interval_slot")
    if slot is None:
        slot = d.get("last_interval_slot")
    if slot is None:
        slot = d.get("last_post_slot")
    posting.setdefault("last_interval_slot", slot)
    posting.setdefault("last_post_id", d.get("last_post_id"))
    posting.setdefault("last_post_text", d.get("last_post_text"))
    posting.setdefault("last_post_at", d.get("last_post_at"))
    posting.setdefault("last_post_views", d.get("last_post_views"))
    copied = posting.get("copied_reference_tweet_ids")
    if copied is None:
        copied = d.get("copied_reference_tweet_ids")
    posting["copied_reference_tweet_ids"] = list(copied or [])

    return {
        "account_id": d.get("account_id"),
        "profile": profile,
        "voice": voice,
        "posting": posting,
    }


def document_to_account(doc: dict) -> AccountDocument:
    return AccountDocument.model_validate(normalize_account_document(doc))


def account_to_document(account: AccountDocument) -> dict:
    d = account.model_dump(exclude_none=True)
    d.pop("@metadata", None)
    profile = d.setdefault("profile", {})
    voice = d.setdefault("voice", {})
    if not voice.get("system_prompt"):
        voice["system_prompt"] = default_system_prompt(profile.get("niche") or account.account_id)
    if not voice.get("negative_semantics"):
        voice["negative_semantics"] = default_negative_semantics()
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
        rql = "from Accounts where profile.status = 'active' or status = 'active'"
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

    def upsert_profile(
        self,
        account_id: str,
        *,
        niche: str | None = None,
        twitter_handle: str | None = None,
        status: str | None = None,
    ) -> AccountDocument:
        existing = self.load(account_id)
        if existing is None:
            now = datetime.now(timezone.utc).isoformat()
            acc = AccountDocument(
                account_id=account_id,
                profile=AccountProfile(
                    niche=niche or account_id,
                    twitter_handle=twitter_handle or "",
                    status=status or "active",
                    registered_at=now,
                    followers_when_registered=0,
                ),
                voice=AccountVoice(
                    system_prompt=default_system_prompt(niche or account_id),
                    negative_semantics=default_negative_semantics(),
                ),
                posting=AccountPostingState(),
            )
        else:
            data = existing.model_dump()
            profile = data.setdefault("profile", {})
            if niche is not None:
                profile["niche"] = niche
            if twitter_handle is not None:
                profile["twitter_handle"] = twitter_handle
            if status is not None:
                profile["status"] = status
            if profile.get("registered_at") is None:
                profile["registered_at"] = datetime.now(timezone.utc).isoformat()
            if profile.get("followers_when_registered") is None:
                profile["followers_when_registered"] = int(profile.get("followers") or 0)
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
