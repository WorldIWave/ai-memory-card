# Input: ImportCardsRequest（格式类型 + 原始内容字符串）+ 数据库 Session
# Output: ImportCardsResponse（新建/匹配的牌组 + 卡片列表 + 导入数量）
# Role: 数据导入路由层，委托 ImportService 解析内容并批量写入 DB
# Note: 导入会自动创建或复用同名牌组；不支持重复卡片去重，需由 service 层处理
# Usage: 由 app/main.py 以 /imports 前缀挂载，POST /cards 上传文本数据
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.api.dependencies import get_import_service
from app.db.session import get_session
from app.schemas.card import CardRead
from app.schemas.deck import DeckRead
from app.schemas.imports import ImportCardsRequest, ImportCardsResponse
from app.services.import_service import ImportService

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/cards", response_model=ImportCardsResponse, status_code=status.HTTP_201_CREATED)
def import_cards(payload: ImportCardsRequest, session: Session = Depends(get_session), service: ImportService = Depends(get_import_service)) -> ImportCardsResponse:
    deck, cards = service.import_cards(session, payload)
    return ImportCardsResponse(deck=DeckRead.model_validate(deck), cards=[CardRead.model_validate(c) for c in cards], imported_count=len(cards))
