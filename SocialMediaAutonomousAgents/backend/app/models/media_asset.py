"""Generated/imported media reference records (RavenDB collection MediaAssets).

The document is the source of truth for a piece of media: it carries provenance
and the ``storage_key`` used to fetch the actual bytes from the media store.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MediaKind = Literal["image", "video"]


class MediaAssetDocument(BaseModel):
    asset_id: str
    kind: MediaKind
    mime: str
    storage_key: str
    provider: str = ""
    provider_request_id: str | None = None
    prompt: str | None = None
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    seed: int | None = None
    # Reference assets this one was derived from (e.g. the image fed to i2v).
    source_asset_ids: list[str] = Field(default_factory=list)
    created_at: str = ""

    @staticmethod
    def document_id(asset_id: str) -> str:
        return f"mediaassets/{asset_id}"
