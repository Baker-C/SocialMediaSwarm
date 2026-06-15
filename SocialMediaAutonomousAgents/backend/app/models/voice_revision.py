"""Soul revision history. One immutable document per soul version.

Each revision captures the COMPLETE soul state at the moment of a version bump,
so the dashboard timeline and any future rollback can reconstruct an exact past identity.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Import the soul building blocks (defined in account.py).
from app.models.account import ContrastPattern, PunctuationRule


class VoiceRevisionDocument(BaseModel):
    account_id: str
    seq: int
    label: str
    version_hash: str
    changed_at: str

    # ── Full soul snapshot (canonical going forward) ──
    # NOTE: unlike AccountSoul, the list fields default to EMPTY, not to the default
    # factories. A revision is an immutable archive; filling a missing field with
    # today's defaults would FABRICATE history (every old row would show the current
    # default contrast set). Empty + the legacy passthrough below lets the dashboard
    # render pre-refactor revisions faithfully (see SoulDetail fallback on the frontend).
    personality: str = ""                              # prose identity at this version
    posting_prompt: str = ""                           # was system_prompt; structural instructions
    contrast_patterns: list[ContrastPattern] = Field(default_factory=list)
    punctuation_rules: list[PunctuationRule] = Field(default_factory=list)

    # ── Legacy passthrough (read-only) for revisions written before the soul refactor ──
    # Kept ONLY so historical rows round-trip and the frontend can map
    # system_prompt → posting_prompt and negative_semantics → [negative] contrast.
    # Never populated for NEW revisions (voice_version_service writes the soul fields above).
    # Pydantic's default extra="ignore" would otherwise DROP these keys on read, so
    # they must be declared here for the old data to survive the load.
    system_prompt: str | None = None
    negative_semantics: list[str] | None = None

    @staticmethod
    def document_id(account_id: str, seq: int) -> str:
        return f"voicerevisions/{account_id}-v{seq}"
