"""Voice revision history for account voice versioning."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.account import default_negative_semantics


class VoiceRevisionDocument(BaseModel):
    account_id: str
    seq: int
    label: str
    version_hash: str
    changed_at: str
    system_prompt: str = ""
    personality: str = ""
    negative_semantics: list[str] = Field(default_factory=default_negative_semantics)

    @staticmethod
    def document_id(account_id: str, seq: int) -> str:
        return f"voicerevisions/{account_id}-v{seq}"
