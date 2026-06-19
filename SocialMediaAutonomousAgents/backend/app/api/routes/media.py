"""Serve generated media bytes by asset id (plan 04 §3).

GET /media/{asset_id} returns the raw bytes so the frontend can render them via
``<img src>``. Mounted WITHOUT the dashboard auth gate (see main.py): browser image
requests cannot carry the bearer token, and these assets (generated avatar/header
images, uuid asset ids) are non-sensitive.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.services.media_asset_repository import MediaAssetRepository

router = APIRouter()


@router.get("/media/{asset_id}")
def get_media(asset_id: str) -> Response:
    try:
        doc, data = MediaAssetRepository().hydrate(asset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="media asset not found") from None
    return Response(content=data, media_type=doc.mime)
