"""Point-in-time account snapshots (RavenDB collection AccountSnapshots)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.account import ContrastPattern, PunctuationRule


class AccountSnapshotDocument(BaseModel):
    """One captured snapshot of an account's profile, soul, and engagement totals."""

    account_id: str
    created_at: str
    niche: str = ""
    twitter_handle: str = ""
    followers: int = 0
    following_count: int = 0
    posts_total: int = 0
    total_likes: int = 0
    total_views: int = 0
    total_reposts: int = 0
    total_comments: int = 0
    # ── Soul snapshot (mirrors VoiceRevisionDocument) ──
    personality: str = ""
    posting_prompt: str = ""                                   # was system_prompt
    contrast_patterns: list[ContrastPattern] = Field(default_factory=list)
    punctuation_rules: list[PunctuationRule] = Field(default_factory=list)
    # Read-only legacy passthrough for pre-refactor snapshots (same rationale as the revision).
    system_prompt: str | None = None
    negative_semantics: list[str] | None = None
    following_list: list[str] = Field(default_factory=list)
    follower_list: list[str] = Field(default_factory=list)

    @staticmethod
    def document_id(account_id: str, created_at: str) -> str:
        slug = created_at.replace(":", "").replace(".", "").replace("+", "")
        return f"accountsnapshots/{account_id}-{slug}"
