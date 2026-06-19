"""Generate persona avatar + header images via the fal.ai/Seedream path.

Out-of-pipeline (like ``agent_builder``): we call the fal client and media
repository directly, mirroring ``pipeline/tools/media/seedance_image.py``.
"""

from __future__ import annotations

from typing import Literal

from app.infrastructure.fal_client import FalMediaClient, get_fal_client
from app.services.media_asset_repository import MediaAssetRepository

PROVIDER = "fal.ai"


class PersonaImageService:
    # fal image_size presets (see settings.fal_default_image_size docstring).
    AVATAR_SIZE = "square_hd"  # 1:1 profile pic
    HEADER_SIZE = "landscape_16_9"  # wide banner (crop to X's ~3:1 in the handler)

    def __init__(
        self,
        fal: FalMediaClient | None = None,
        media_repo: MediaAssetRepository | None = None,
    ) -> None:
        self.fal = fal or get_fal_client()
        self.media_repo = media_repo or MediaAssetRepository()

    def _one(self, prompt: str, image_size: str) -> str:
        if not self.fal.enabled:
            raise RuntimeError("FAL_API_KEY is not set; cannot generate persona images")
        result = self.fal.generate_image(prompt=prompt, image_size=image_size)
        data = self.fal.fetch_bytes(result["url"])
        doc = self.media_repo.save_bytes(
            data=data,
            kind="image",
            mime="image/png",
            provider=PROVIDER,
            prompt=prompt,
            width=result.get("width"),
            height=result.get("height"),
            seed=result.get("seed"),
        )
        return doc.asset_id

    def generate(self, avatar_prompt: str, header_prompt: str) -> tuple[str, str]:
        return (
            self._one(avatar_prompt, self.AVATAR_SIZE),
            self._one(header_prompt, self.HEADER_SIZE),
        )

    def generate_one(self, kind: Literal["avatar", "header"], prompt: str) -> str:
        image_size = self.AVATAR_SIZE if kind == "avatar" else self.HEADER_SIZE
        return self._one(prompt, image_size)


def generate_persona_images(avatar_prompt: str, header_prompt: str) -> tuple[str, str]:
    return PersonaImageService().generate(avatar_prompt, header_prompt)


def generate_persona_image(kind: Literal["avatar", "header"], prompt: str) -> str:
    return PersonaImageService().generate_one(kind, prompt)
