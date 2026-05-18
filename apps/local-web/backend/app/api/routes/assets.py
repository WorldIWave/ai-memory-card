# Input: multipart image uploads and safe asset path params | Output: local card media metadata or file bytes
# Role: API boundary for Markdown image assets used by card editors and renderers
# Usage: app/main.py mounts this router under /api
from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import FileResponse

from app.schemas.assets import CardAssetDraftResponse, CardAssetUploadResponse
from app.services.card_asset_service import CardAssetService


router = APIRouter(prefix="/assets/cards", tags=["assets"])


@router.post("/drafts", response_model=CardAssetDraftResponse, status_code=status.HTTP_201_CREATED)
def create_card_asset_draft() -> CardAssetDraftResponse:
    draft_id = CardAssetService().create_draft_id()
    return CardAssetDraftResponse(draft_id=draft_id)


@router.post("/upload", response_model=CardAssetUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_card_asset(
    file: UploadFile = File(...),
    card_id: int | None = Form(default=None),
    draft_id: str | None = Form(default=None),
) -> CardAssetUploadResponse:
    result = await CardAssetService().save_upload(file, card_id=card_id, draft_id=draft_id)
    return CardAssetUploadResponse(**result)


@router.get("/{asset_path:path}")
def read_card_asset(asset_path: str) -> FileResponse:
    return CardAssetService().file_response(asset_path=asset_path)
