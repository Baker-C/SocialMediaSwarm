"""Persist media reference records (collection MediaAssets).

The repository owns the DB reference; bytes live in the media store keyed by
``storage_key``. ``hydrate`` joins the two: load the record, fetch the bytes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.infrastructure.media_store import MediaStore, get_media_store
from app.infrastructure.ravendb_http import RavenDBHttpClient, get_ravendb_client
from app.models.media_asset import MediaAssetDocument, MediaKind

MEDIA_COLLECTION = "MediaAssets"


def _strip_metadata(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if not str(k).startswith("@")}


class MediaAssetRepository:
    def __init__(
        self,
        client: RavenDBHttpClient | None = None,
        store: MediaStore | None = None,
    ) -> None:
        self._client = client
        self._store = store

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    @property
    def store(self) -> MediaStore:
        return self._store or get_media_store()

    def save_bytes(
        self,
        data: bytes,
        *,
        kind: MediaKind,
        mime: str,
        provider: str = "",
        provider_request_id: str | None = None,
        prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
        duration_s: float | None = None,
        seed: int | None = None,
        source_asset_ids: list[str] | None = None,
    ) -> MediaAssetDocument:
        """Persist bytes to the store and write the reference record. Returns the record."""
        storage_key = self.store.put(data, mime=mime)
        doc = MediaAssetDocument(
            asset_id=uuid.uuid4().hex,
            kind=kind,
            mime=mime,
            storage_key=storage_key,
            provider=provider,
            provider_request_id=provider_request_id,
            prompt=prompt,
            width=width,
            height=height,
            duration_s=duration_s,
            seed=seed,
            source_asset_ids=list(source_asset_ids or []),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.client.put_document(
            MediaAssetDocument.document_id(doc.asset_id),
            doc.model_dump(exclude_none=True),
            collection=MEDIA_COLLECTION,
        )
        return doc

    def get(self, asset_id: str) -> MediaAssetDocument | None:
        raw = self.client.get_document(MediaAssetDocument.document_id(asset_id))
        if raw is None:
            return None
        return MediaAssetDocument.model_validate(_strip_metadata(raw))

    def hydrate(self, asset_id: str) -> tuple[MediaAssetDocument, bytes]:
        """Load the reference record and its bytes. Raises if the asset is unknown."""
        doc = self.get(asset_id)
        if doc is None:
            raise KeyError(f"media asset not found: {asset_id}")
        return doc, self.store.get(doc.storage_key)
