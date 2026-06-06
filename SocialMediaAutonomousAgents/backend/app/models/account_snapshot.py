"""Point-in-time account snapshots (RavenDB collection AccountSnapshots)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AccountSnapshotDocument(BaseModel):
    """One captured snapshot of an account's profile, voice, and engagement totals."""

    account_id: str
    created_at: str
    niche: str = ""
    twitter_handle: str = ""
    followers: int = 0
    following_count: int = 0
    posts_total: int = 0
    total_likes: int = 0
    total_views: int = 0
    system_prompt: str = ""
    personality: str = ""
    negative_semantics: list[str] = Field(default_factory=list)
    following_list: list[str] = Field(default_factory=list)
    follower_list: list[str] = Field(default_factory=list)

    @staticmethod
    def document_id(account_id: str, created_at: str) -> str:
        slug = created_at.replace(":", "").replace(".", "").replace("+", "")
        return f"accountsnapshots/{account_id}-{slug}"
