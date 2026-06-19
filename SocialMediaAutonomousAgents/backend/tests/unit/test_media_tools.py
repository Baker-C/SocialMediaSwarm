"""Unit tests for the media store, poller, and Seedance generation tools (no network)."""

from __future__ import annotations

import pytest

from app.infrastructure.media_store import LocalFilesystemMediaStore, to_data_uri
from app.infrastructure.task_poller import TaskPollError, TaskPollTimeout, poll_until
from app.pipeline.tools.media import seedance_image, seedance_video
from app.pipeline.types.artifacts import ArtifactKey, MediaRef
from app.pipeline.types.context import TickRunContext
from app.services.media_asset_repository import MediaAssetRepository


# --- media store ---------------------------------------------------------

def test_store_round_trip(tmp_path):
    store = LocalFilesystemMediaStore(tmp_path)
    key = store.put(b"hello", mime="image/png")
    assert key.endswith(".png")
    assert store.get(key) == b"hello"


def test_data_uri():
    assert to_data_uri(b"x", "image/png").startswith("data:image/png;base64,")


# --- poller --------------------------------------------------------------

def test_poll_until_returns_when_done():
    seq = iter([{"s": "go"}, {"s": "go"}, {"s": "done"}])
    out = poll_until(lambda: next(seq), lambda r: r["s"] == "done", timeout_s=5, interval_s=0)
    assert out["s"] == "done"


def test_poll_until_raises_on_failure():
    with pytest.raises(TaskPollError):
        poll_until(
            lambda: {"s": "bad"},
            lambda r: r["s"] == "done",
            timeout_s=5,
            interval_s=0,
            is_failed=lambda r: "boom" if r["s"] == "bad" else None,
        )


def test_poll_until_times_out():
    with pytest.raises(TaskPollTimeout):
        poll_until(lambda: {"s": "go"}, lambda r: False, timeout_s=-1, interval_s=0)


# --- generation tools (fake store + fake client) -------------------------

class _FakeStore:
    def __init__(self):
        self.blobs: dict[str, bytes] = {}

    def put(self, data, *, mime):
        key = f"k{len(self.blobs)}"
        self.blobs[key] = data
        return key

    def get(self, storage_key):
        return self.blobs[storage_key]

    def path_for(self, storage_key):  # pragma: no cover - not used here
        raise NotImplementedError


class _FakeRavenClient:
    def __init__(self):
        self.docs: dict[str, dict] = {}

    def put_document(self, doc_id, document, *, collection=None):
        self.docs[doc_id] = document

    def get_document(self, doc_id):
        return self.docs.get(doc_id)


class _FakeFal:
    def generate_image(self, *, prompt, image_size=None, seed=None):
        return {"url": "https://fal/img.png", "width": 1024, "height": 1024, "seed": 7}

    def generate_video(self, *, prompt, image_data_uri=None, resolution=None, duration=None, seed=None):
        self.last_image_data_uri = image_data_uri
        return {"url": "https://fal/vid.mp4", "seed": 9}

    def fetch_bytes(self, url):
        return b"VID" if url.endswith(".mp4") else b"IMG"


def _repo():
    return MediaAssetRepository(client=_FakeRavenClient(), store=_FakeStore())


def test_seedance_image_persists_and_sets_artifact():
    ctx = TickRunContext(account_id="a", slot="s")
    repo = _repo()
    res = seedance_image.run(ctx, prompt="a cat", media_repo=repo, fal=_FakeFal())
    assert res.ok
    ref = ctx.get_artifact(ArtifactKey.GENERATED_IMAGE)
    assert isinstance(ref, MediaRef) and ref.kind == "image"
    doc, data = repo.hydrate(ref.asset_id)
    assert data == b"IMG" and doc.provider == "fal.ai"


def test_seedance_video_image_to_video_uses_reference():
    ctx = TickRunContext(account_id="a", slot="s")
    repo = _repo()
    img = repo.save_bytes(b"REF", kind="image", mime="image/png", provider="test")
    ref = MediaRef(asset_id=img.asset_id, kind="image", mime="image/png")
    fal = _FakeFal()
    res = seedance_video.run(ctx, prompt="pan", media_repo=repo, fal=fal, reference=ref, duration=5)
    assert res.ok
    assert fal.last_image_data_uri.startswith("data:image/png;base64,")
    vid = ctx.get_artifact(ArtifactKey.GENERATED_VIDEO)
    assert vid.kind == "video"
    out_doc, out_bytes = repo.hydrate(vid.asset_id)
    assert out_bytes == b"VID" and out_doc.source_asset_ids == [img.asset_id]


def test_empty_prompt_is_rejected():
    ctx = TickRunContext(account_id="a", slot="s")
    res = seedance_image.run(ctx, prompt="   ", media_repo=_repo(), fal=_FakeFal())
    assert not res.ok and res.skip_reason == "empty_prompt"


# --- catalog conformance (tools are convention-ready though not yet registered) ---

def test_media_tools_introspect_cleanly_under_catalog():
    """The media tools classify correctly if/when added to _TOOL_MODULES:
    media_repo/fal injected, prompt literal, reference wired."""
    from app.pipeline.spec.catalog import _introspect

    for mod, extra_literals in ((seedance_image, set()), (seedance_video, set())):
        doc = _introspect(mod)
        assert doc.kind == "data"
        assert doc.source == "fal"
        by_name = {p.name: p for p in doc.parameters}
        assert by_name["media_repo"].config_origin == "injected"
        assert by_name["fal"].config_origin == "injected"
        assert by_name["prompt"].config_origin == "literal"
    # reference (video only) must be wired, never an LLM-proposable literal
    vdoc = _introspect(seedance_video)
    assert {p.name: p for p in vdoc.parameters}["reference"].config_origin == "wired"
