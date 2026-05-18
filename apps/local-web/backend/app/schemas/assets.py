# Input: card asset service results | Output: API response DTOs for local card media
# Role: Shared schema layer for image uploads and draft namespaces
# Usage: routes/assets.py returns these models from /api/assets/cards/*
from pydantic import BaseModel


class CardAssetDraftResponse(BaseModel):
    draft_id: str


class CardAssetUploadResponse(BaseModel):
    asset_id: str
    filename: str
    content_type: str
    size_bytes: int
    url: str
    markdown: str
