"""Voice revision history for account voice versioning."""

from __future__ import annotations

from pydantic import BaseModel


class VoiceRevisionDocument(BaseModel):
    account_id: str
    seq: int
    label: str
    version_hash: str
    changed_at: str

    @staticmethod
    def document_id(account_id: str, seq: int) -> str:
        return f"voicerevisions/{account_id}-v{seq}"
