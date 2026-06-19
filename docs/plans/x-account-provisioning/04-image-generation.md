# 04 — Avatar + Header Image Generation

**Touches:** `backend/app/services/persona_image_service.py` (new)

Generate the profile picture and header banner from the persona's `avatar_prompt` / `header_prompt`
using the **existing** fal.ai/Seedream path. We do **not** register a pipeline tool — image gen here
is an out-of-pipeline call (like `agent_builder`), so we call the client + repo directly, exactly as
`pipeline/tools/media/seedance_image.py` does internally.

## 1. The reuse path (already on `main`)

- `get_fal_client().generate_image(*, prompt, image_size=None, seed=None) -> {url, width, height, seed}`
  — `infrastructure/fal_client.py:104`. Model defaults to `settings.fal_seedream_image_model`.
- `FalMediaClient.fetch_bytes(url) -> bytes` — `:94`.
- `MediaAssetRepository().save_bytes(*, data, kind, mime, provider, prompt, width, height, seed) -> MediaAssetDocument`
  — `services/media_asset_repository.py:40`. Stores bytes via the media store + a `MediaAssets` doc.
- Helper `persist_result(...)` in `pipeline/tools/media/_media_io.py:21` wraps `save_bytes` and returns
  a `MediaRef`. Either is fine; `save_bytes` returns the doc with `asset_id`.

## 2. Service

```python
from app.infrastructure.fal_client import get_fal_client
from app.services.media_asset_repository import MediaAssetRepository

class PersonaImageService:
    # fal supported size enums; confirm against fal_client / settings.fal_default_image_size
    AVATAR_SIZE = "square_hd"          # 1:1 profile pic
    HEADER_SIZE = "landscape_16_9"     # wide banner (X header ~3:1; 16:9 then crop in handler)

    def __init__(self, fal=None, media_repo: MediaAssetRepository | None = None) -> None:
        self.fal = fal or get_fal_client()
        self.media_repo = media_repo or MediaAssetRepository()

    def _one(self, prompt: str, image_size: str) -> str:
        if not self.fal.enabled:
            raise RuntimeError("FAL_API_KEY is not set; cannot generate persona images")
        result = self.fal.generate_image(prompt=prompt, image_size=image_size)
        data = self.fal.fetch_bytes(result["url"])
        doc = self.media_repo.save_bytes(
            data=data, kind="image", mime="image/png", provider="fal.ai",
            prompt=prompt, width=result.get("width"), height=result.get("height"),
            seed=result.get("seed"),
        )
        return doc.asset_id

    def generate(self, avatar_prompt: str, header_prompt: str) -> tuple[str, str]:
        return self._one(avatar_prompt, self.AVATAR_SIZE), self._one(header_prompt, self.HEADER_SIZE)

def generate_persona_images(avatar_prompt: str, header_prompt: str) -> tuple[str, str]:
    return PersonaImageService().generate(avatar_prompt, header_prompt)
```

`03`'s approve step and the "regenerate" endpoint both call `generate_persona_images`.

## 3. Regenerate endpoint (review-stage)

The operator can regenerate before approving. Add to `persona.py` (or `provisioning.py`):

```python
class RegenImagesBody(BaseModel):
    avatar_prompt: str
    header_prompt: str

@router.post("/persona/regenerate-images")
def regenerate_images(body: RegenImagesBody) -> dict:
    avatar_id, header_id = generate_persona_images(body.avatar_prompt, body.header_prompt)
    return {"avatar_asset_id": avatar_id, "header_asset_id": header_id}
```

The frontend renders the images by asset id — confirm/serve a bytes route. If the media tools added
a `GET /api/media/{asset_id}` route, reuse it; otherwise add a thin one:
`MediaAssetRepository().hydrate(asset_id)` → `Response(content=bytes, media_type=doc.mime)`.
(Check whether the seedance work already exposes a media-serving route before adding one.)

## 4. Consumption by the agent

The provisioning agent uploads these during X profile setup. The job payload (`05`) includes the
two asset ids; the agent fetches the bytes via the media route (or the backend inlines base64 data
URIs in the job). Prefer the media route to keep the job payload small.

## 5. Tests (`tests/unit/test_persona_image_service.py`)

Mirror `test_media_tools.py` exactly — inject a `_FakeFal` (returns canned `{url,...}` + bytes) and a
fake `MediaAssetRepository`:
- `generate(...)` returns two distinct asset ids; `save_bytes` called twice with `kind="image"`,
  `provider="fal.ai"`, and the avatar/header sizes respectively.
- `fal.enabled is False` → `RuntimeError` mentioning `FAL_API_KEY`.
- `_FakeFal.generate_image` asserts the `image_size` it receives matches AVATAR/HEADER per call.

> Do **not** test the real `FalMediaClient` HTTP here (it's untested by design in this repo). If you
> want client-level coverage, add a separate `httpx.Client`-patch test per `07`'s skeleton.

## Done when
- `generate_persona_images(avatar, header)` returns two persisted `MediaAssets` asset ids.
- Regenerate endpoint returns fresh ids; images are servable by id to the frontend.
- Tests green with injected fakes; no network.
