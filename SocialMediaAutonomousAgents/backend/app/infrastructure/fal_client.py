"""fal.ai queue client for Seedance (video) and Seedream (image) generation.

Flow per the fal queue API: ``POST {base}/{model_id}`` returns a request with a
``status_url`` and ``response_url``; poll the status until ``COMPLETED``, then GET
the response for the output. Auth header is ``Authorization: Key <fal_api_key>``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.infrastructure.task_poller import TaskPollError, poll_until

logger = logging.getLogger(__name__)


class FalAPIError(RuntimeError):
    """HTTP failure or unexpected fal payload."""


class FalMediaClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = (api_key or settings.fal_api_key or "").strip()
        self._base_url = (base_url or settings.fal_queue_base_url).rstrip("/")
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Key {self._api_key}", "Content-Type": "application/json"}

    def _require_key(self) -> None:
        if not self.enabled:
            raise FalAPIError("FAL_API_KEY is not set")

    def _submit(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_key()
        url = f"{self._base_url}/{model_id.strip('/')}"
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, headers=self._headers(), json=payload)
        if r.status_code >= 400:
            raise FalAPIError(f"fal submit HTTP {r.status_code}: {r.text[:500]}")
        data = r.json()
        if not data.get("status_url") or not data.get("response_url"):
            raise FalAPIError(f"fal submit missing status/response url: {data!r}")
        return data

    def _await_output(self, submitted: dict[str, Any]) -> dict[str, Any]:
        status_url = submitted["status_url"]
        response_url = submitted["response_url"]

        def _fetch_status() -> dict[str, Any]:
            with httpx.Client(timeout=self._timeout) as client:
                r = client.get(status_url, headers=self._headers())
            if r.status_code >= 400:
                raise FalAPIError(f"fal status HTTP {r.status_code}: {r.text[:300]}")
            return r.json()

        def _failed(s: dict[str, Any]) -> str | None:
            status = str(s.get("status") or "").upper()
            if status in ("FAILED", "ERROR", "CANCELLED"):
                return f"fal job {status}: {s.get('error') or s}"
            return None

        try:
            poll_until(
                _fetch_status,
                lambda s: str(s.get("status") or "").upper() == "COMPLETED",
                timeout_s=settings.fal_poll_timeout_seconds,
                interval_s=settings.fal_poll_interval_seconds,
                is_failed=_failed,
            )
        except TaskPollError as exc:
            raise FalAPIError(str(exc)) from exc

        with httpx.Client(timeout=self._timeout) as client:
            r = client.get(response_url, headers=self._headers())
        if r.status_code >= 400:
            raise FalAPIError(f"fal response HTTP {r.status_code}: {r.text[:500]}")
        return r.json()

    def fetch_bytes(self, url: str) -> bytes:
        """Download a result asset (fal CDN url) so the media store can persist it."""
        with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
            r = client.get(url)
        if r.status_code >= 400:
            raise FalAPIError(f"fal asset download HTTP {r.status_code}: {url}")
        return r.content

    # --- generation -----------------------------------------------------

    def generate_image(
        self,
        *,
        prompt: str,
        model_id: str | None = None,
        image_size: str | None = None,
        num_images: int = 1,
        seed: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Seedream text-to-image. Returns ``{url, width, height, seed}``."""
        payload: dict[str, Any] = {"prompt": prompt, "num_images": num_images}
        if image_size or settings.fal_default_image_size:
            payload["image_size"] = image_size or settings.fal_default_image_size
        if seed is not None:
            payload["seed"] = seed
        if extra:
            payload.update(extra)
        out = self._await_output(
            self._submit(model_id or settings.fal_seedream_image_model, payload)
        )
        images = out.get("images") or []
        if not images or not isinstance(images, list) or not images[0].get("url"):
            raise FalAPIError(f"fal image output missing images[].url: {out!r}")
        first = images[0]
        return {
            "url": first["url"],
            "width": first.get("width"),
            "height": first.get("height"),
            "seed": out.get("seed"),
        }

    def generate_video(
        self,
        *,
        prompt: str,
        image_data_uri: str | None = None,
        resolution: str | None = None,
        duration: int | None = None,
        seed: int | None = None,
        model_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Seedance text-to-video, or image-to-video when ``image_data_uri`` is given.

        ``image_data_uri`` is a base64 ``data:`` URI (a local reference frame) or a
        public image URL. Returns ``{url, seed}``.
        """
        payload: dict[str, Any] = {
            "prompt": prompt,
            "resolution": resolution or settings.fal_default_video_resolution,
            "duration": str(duration or settings.fal_default_video_duration),
        }
        if seed is not None:
            payload["seed"] = seed
        if extra:
            payload.update(extra)
        if image_data_uri:
            payload["image_url"] = image_data_uri
            chosen_model = model_id or settings.fal_seedance_i2v_model
        else:
            chosen_model = model_id or settings.fal_seedance_t2v_model
        out = self._await_output(self._submit(chosen_model, payload))
        video = out.get("video") or {}
        if not isinstance(video, dict) or not video.get("url"):
            raise FalAPIError(f"fal video output missing video.url: {out!r}")
        return {"url": video["url"], "seed": out.get("seed")}


_client: FalMediaClient | None = None


def get_fal_client() -> FalMediaClient:
    global _client
    if _client is None:
        _client = FalMediaClient()
    return _client
