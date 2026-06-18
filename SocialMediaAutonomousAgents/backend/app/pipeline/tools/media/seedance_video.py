"""Generate a video via fal.ai Seedance and persist it as a media asset.

Text-to-video by default; image-to-video when a ``reference`` image handle is
given (it is hydrated from the store and fed as a base64 first frame).
"""

from __future__ import annotations

from app.infrastructure.fal_client import FalMediaClient, get_fal_client
from app.pipeline.tools.media._media_io import persist_result, reference_to_data_uri
from app.pipeline.types.artifacts import ArtifactKey, MediaRef
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.media_asset_repository import MediaAssetRepository

TOOL_ID = "data.seedance_video"
TOOL_KIND = "data"
TOOL_SOURCE = "fal"
TOOL_PURPOSE = "Generate a video (fal.ai Seedance) and store it as a media asset"
TOOL_WRITES = (ArtifactKey.GENERATED_VIDEO,)
PROVIDER = "fal.ai"


def run(
    ctx: TickRunContext,
    *,
    prompt: str,
    media_repo: MediaAssetRepository | None = None,
    fal: FalMediaClient | None = None,
    reference: MediaRef | None = None,
    resolution: str | None = None,
    duration: int | None = None,
    seed: int | None = None,
) -> StepResult:
    fal = fal or get_fal_client()
    media_repo = media_repo or MediaAssetRepository()
    if not prompt.strip():
        return StepResult(ok=False, skip_reason="empty_prompt")

    image_data_uri = reference_to_data_uri(reference, media_repo) if reference else None
    result = fal.generate_video(
        prompt=prompt,
        image_data_uri=image_data_uri,
        resolution=resolution,
        duration=duration,
        seed=seed,
    )
    data = fal.fetch_bytes(result["url"])
    ref = persist_result(
        data=data,
        kind="video",
        mime="video/mp4",
        repo=media_repo,
        provider=PROVIDER,
        prompt=prompt,
        duration_s=float(duration) if duration else None,
        seed=result.get("seed"),
        source_asset_ids=[reference.asset_id] if reference else None,
    )
    ctx.set_artifact(ArtifactKey.GENERATED_VIDEO, ref)
    return StepResult(ok=True, payload={"asset_id": ref.asset_id})
