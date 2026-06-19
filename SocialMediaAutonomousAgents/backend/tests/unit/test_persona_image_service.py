"""Unit tests for PersonaImageService (injected fakes, no network)."""

from __future__ import annotations

import pytest

from app.services.persona_image_service import PersonaImageService


class _FakeFal:
    def __init__(self, *, enabled: bool = True):
        self.enabled = enabled
        self.sizes: list[str] = []

    def generate_image(self, *, prompt, image_size=None, seed=None):
        self.sizes.append(image_size)
        return {"url": "https://fal/img.png", "width": 1024, "height": 1024, "seed": 7}

    def fetch_bytes(self, url):
        return b"IMG"


class _FakeDoc:
    def __init__(self, asset_id: str):
        self.asset_id = asset_id


class _FakeRepo:
    def __init__(self):
        self.calls: list[dict] = []
        self._n = 0

    def save_bytes(self, data, **kwargs):
        self.calls.append({"data": data, **kwargs})
        self._n += 1
        return _FakeDoc(f"asset{self._n}")


def test_generate_returns_two_distinct_ids_and_sizes():
    fal = _FakeFal()
    repo = _FakeRepo()
    avatar_id, header_id = PersonaImageService(fal=fal, media_repo=repo).generate(
        "an avatar", "a header"
    )

    assert avatar_id != header_id
    assert avatar_id == "asset1" and header_id == "asset2"
    assert fal.sizes == [
        PersonaImageService.AVATAR_SIZE,
        PersonaImageService.HEADER_SIZE,
    ]

    assert len(repo.calls) == 2
    for call in repo.calls:
        assert call["kind"] == "image"
        assert call["provider"] == "fal.ai"
        assert call["mime"] == "image/png"
        assert call["data"] == b"IMG"


def test_disabled_fal_raises_runtime_error():
    service = PersonaImageService(fal=_FakeFal(enabled=False), media_repo=_FakeRepo())
    with pytest.raises(RuntimeError, match="FAL_API_KEY"):
        service.generate("an avatar", "a header")
