# Input: format 查询参数（json/csv/markdown）+ 数据库 Session
# Output: ExportCardsResponse（包含所有活跃卡片的序列化数据）
# Role: 数据导出路由层，将全量卡片数据交由 ExportService 格式化后返回给客户端
# Note: 当前仅支持全量导出，不支持按牌组或文件夹过滤；大数据量时响应可能较慢
# Usage: 由 app/main.py 以 /exports 前缀挂载，GET /cards?format=json|csv|markdown
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.api.dependencies import get_export_service
from app.db.session import get_session
from app.schemas.exports import ExportCardsResponse
from app.services.export_service import ExportService

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/cards", response_model=ExportCardsResponse, status_code=status.HTTP_200_OK)
def export_cards(format: Literal["json", "csv", "markdown"] = "json", session: Session = Depends(get_session), service: ExportService = Depends(get_export_service)) -> ExportCardsResponse:
    return service.export_cards(session, format)
