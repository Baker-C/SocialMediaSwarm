"""Generate an image via fal.ai Seedream and persist it as a media asset."""

from __future__ import annotations

from app.infrastructure.fal_client import FalMediaClient, get_fal_client
from app.pipeline.tools.media._media_io import persist_result
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.media_asset_repository import MediaAssetRepository

TOOL_ID = "data.seedance_image"
TOOL_KIND = "data"
TOOL_SOURCE = "fal"
TOOL_PURPOSE = "Generate an image (fal.ai Seedream) and store it as a media asset"
TOOL_WRITES = (ArtifactKey.GENERATED_IMAGE,)
PROVIDER = "fal.ai"


def run(
    ctx: TickRunContext,
    *,
    prompt: str,
    media_repo: MediaAssetRepository | None = None,
    fal: FalMediaClient | None = None,
    image_size: str | None = None,
    seed: int | None = None,
) -> StepResult:
    fal = fal or get_fal_client()
    media_repo = media_repo or MediaAssetRepository()
    if not prompt.strip():
        return StepResult(ok=False, skip_reason="empty_prompt")

    result = fal.generate_image(prompt=prompt, image_size=image_size, seed=seed)
    data = fal.fetch_bytes(result["url"])
    ref = persist_result(
        data=data,
        kind="image",
        mime="image/png",
        repo=media_repo,
        provider=PROVIDER,
        prompt=prompt,
        width=result.get("width"),
        height=result.get("height"),
        seed=result.get("seed"),
    )
    ctx.set_artifact(ArtifactKey.GENERATED_IMAGE, ref)
    return StepResult(ok=True, payload={"asset_id": ref.asset_id})
