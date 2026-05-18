# Input: UploadFile plus card/draft namespace | Output: saved local asset metadata and safe file responses
# Role: Owns local card media storage under RuntimePaths.app_data_dir/assets/cards
# Usage: routes/assets.py delegates upload and file lookup to CardAssetService
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.runtime_paths import RuntimePaths


ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class CardAssetService:
    def __init__(self) -> None:
        self.paths = RuntimePaths.from_settings(get_settings())
        self.asset_root = self.paths.app_data_dir / "assets" / "cards"

    def create_draft_id(self) -> str:
        draft_id = f"draft_{uuid4().hex}"
        (self.asset_root / "drafts" / draft_id).mkdir(parents=True, exist_ok=True)
        return draft_id

    async def save_upload(
        self,
        file: UploadFile,
        *,
        card_id: int | None,
        draft_id: str | None,
    ) -> dict[str, object]:
        namespace = self._namespace(card_id=card_id, draft_id=draft_id)
        content_type = file.content_type or ""
        extension = ALLOWED_IMAGE_TYPES.get(content_type)
        if extension is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported image type: {content_type or 'unknown'}",
            )

        content = await file.read()
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image is larger than 10 MB",
            )

        original_stem = Path(file.filename or "image").stem.strip() or "image"
        safe_stem = "".join(ch for ch in original_stem if ch.isalnum() or ch in ("-", "_"))[:48] or "image"
        asset_id = uuid4().hex
        filename = f"{asset_id}-{safe_stem}{extension}"
        target_dir = self.asset_root / namespace
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = self._resolve_inside_root(target_dir / filename)
        target_path.write_bytes(content)

        url = f"/api/assets/cards/{namespace.as_posix()}/{filename}"
        markdown = f"![{safe_stem}]({url})"
        return {
            "asset_id": asset_id,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(content),
            "url": url,
            "markdown": markdown,
        }

    def file_response(self, *, asset_path: str) -> FileResponse:
        target = self._resolve_inside_root(self.asset_root / Path(asset_path))
        if not target.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        return FileResponse(target)

    def _namespace(self, *, card_id: int | None, draft_id: str | None) -> Path:
        if card_id is not None:
            if card_id <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="card_id must be positive")
            return Path(str(card_id))

        if draft_id:
            if not draft_id.startswith("draft_") or any(ch in draft_id for ch in ("/", "\\", ".")):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid draft_id")
            return Path("drafts") / draft_id

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="card_id or draft_id is required")

    def _resolve_inside_root(self, path: Path) -> Path:
        resolved_root = self.asset_root.resolve()
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid asset path") from exc
        return resolved_path
