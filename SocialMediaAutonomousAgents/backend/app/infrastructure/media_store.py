"""Local media byte store (bytes ↔ disk), keyed by ``storage_key``.

This layer is deliberately narrow: it only reads/writes bytes. It knows nothing
about generation or the database. The DB reference record (see
``app.services.media_asset_repository``) holds the ``storage_key``; hydrating a
reference means loading the record, then fetching its bytes from here.

Swapping disk for S3/R2 or RavenDB attachments later is a new implementation of
the ``MediaStore`` protocol — records and tools are unaffected.
"""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import settings

_EXT_BY_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
}


def ext_for_mime(mime: str) -> str:
    return _EXT_BY_MIME.get((mime or "").strip().lower(), "bin")


def to_data_uri(data: bytes, mime: str) -> str:
    """Base64 ``data:`` URI — how a local reference image is fed to fal.ai."""
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


class MediaStore(Protocol):
    def put(self, data: bytes, *, mime: str) -> str:
        """Persist bytes; return the ``storage_key`` to fetch them later."""
        ...

    def get(self, storage_key: str) -> bytes:
        """Return the bytes for a ``storage_key``."""
        ...

    def path_for(self, storage_key: str) -> Path:
        """Filesystem path for a ``storage_key`` (local stores only)."""
        ...


class LocalFilesystemMediaStore:
    """Saves media under ``media_store_dir`` on this machine."""

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root or settings.media_store_dir)

    @property
    def root(self) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        return self._root

    def put(self, data: bytes, *, mime: str) -> str:
        storage_key = f"{uuid.uuid4().hex}.{ext_for_mime(mime)}"
        (self.root / storage_key).write_bytes(data)
        return storage_key

    def get(self, storage_key: str) -> bytes:
        return self.path_for(storage_key).read_bytes()

    def path_for(self, storage_key: str) -> Path:
        return self.root / storage_key


_store: LocalFilesystemMediaStore | None = None


def get_media_store() -> LocalFilesystemMediaStore:
    global _store
    if _store is None:
        _store = LocalFilesystemMediaStore()
    return _store
