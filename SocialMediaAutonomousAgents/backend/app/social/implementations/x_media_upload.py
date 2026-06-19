"""X v2 chunked media upload (INIT → APPEND → FINALIZE → STATUS).

Returns a ``media_id`` string to attach to ``create_tweet(media_ids=[...])``.
Works with an OAuth2 user bearer token — the account's app must include the
``media.write`` scope (not in the default scope set; expand before activating).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.infrastructure.task_poller import TaskPollError, poll_until
from app.social.exceptions import SocialPlatformError

logger = logging.getLogger(__name__)

_UPLOAD_URL = "https://api.x.com/2/media/upload"
_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB, within X's 5 MB APPEND limit
_PROCESS_TIMEOUT_S = 300.0

_CATEGORY_BY_KIND = {"image": "tweet_image", "video": "tweet_video", "gif": "tweet_gif"}


def _media_id(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, dict) and data.get("id"):
        return str(data["id"])
    return str(payload.get("media_id_string") or payload.get("media_id") or "") or None


def upload_media(bearer_token: str, data: bytes, mime: str, *, kind: str = "image") -> str:
    """Upload bytes via the chunked flow; block on video processing. Returns media_id."""
    token = (bearer_token or "").strip()
    if not token:
        raise SocialPlatformError("X bearer token is empty for media upload", vendor="x")
    headers = {"Authorization": f"Bearer {token}"}
    category = _CATEGORY_BY_KIND.get(kind, "tweet_image")

    with httpx.Client(timeout=120.0) as client:
        init = client.post(
            _UPLOAD_URL,
            headers=headers,
            data={
                "command": "INIT",
                "total_bytes": str(len(data)),
                "media_type": mime,
                "media_category": category,
            },
        )
        if init.status_code >= 400:
            raise SocialPlatformError(f"media INIT HTTP {init.status_code}: {init.text[:300]}", vendor="x")
        media_id = _media_id(init.json())
        if not media_id:
            raise SocialPlatformError(f"media INIT missing id: {init.text[:300]}", vendor="x")

        for index, start in enumerate(range(0, len(data), _CHUNK_SIZE)):
            chunk = data[start : start + _CHUNK_SIZE]
            ap = client.post(
                _UPLOAD_URL,
                headers=headers,
                data={"command": "APPEND", "media_id": media_id, "segment_index": str(index)},
                files={"media": ("chunk", chunk, "application/octet-stream")},
            )
            if ap.status_code >= 400:
                raise SocialPlatformError(f"media APPEND HTTP {ap.status_code}: {ap.text[:300]}", vendor="x")

        fin = client.post(
            _UPLOAD_URL,
            headers=headers,
            data={"command": "FINALIZE", "media_id": media_id},
        )
        if fin.status_code >= 400:
            raise SocialPlatformError(f"media FINALIZE HTTP {fin.status_code}: {fin.text[:300]}", vendor="x")
        _await_processing(client, headers, media_id, fin.json())

    return media_id


def _await_processing(
    client: httpx.Client,
    headers: dict[str, str],
    media_id: str,
    finalize_payload: dict[str, Any],
) -> None:
    """Poll STATUS until async processing (video) succeeds. No-op for images."""
    info = (finalize_payload.get("data") or finalize_payload).get("processing_info")
    if not isinstance(info, dict):
        return

    def _fetch() -> dict[str, Any]:
        r = client.get(
            _UPLOAD_URL,
            headers=headers,
            params={"command": "STATUS", "media_id": media_id},
        )
        if r.status_code >= 400:
            raise SocialPlatformError(f"media STATUS HTTP {r.status_code}: {r.text[:300]}", vendor="x")
        payload = r.json()
        return (payload.get("data") or payload).get("processing_info") or {}

    def _failed(pi: dict[str, Any]) -> str | None:
        if str(pi.get("state")) == "failed":
            return f"media processing failed: {pi.get('error') or pi}"
        return None

    try:
        poll_until(
            _fetch,
            lambda pi: str(pi.get("state")) == "succeeded",
            timeout_s=_PROCESS_TIMEOUT_S,
            interval_s=2.0,
            is_failed=_failed,
        )
    except TaskPollError as exc:
        raise SocialPlatformError(str(exc), vendor="x") from exc
