# Input: card_id 路径参数 + 数据库 Session
# Output: 归档/恢复后的 CardRead 对象；列举回收站返回 CardRead 列表
# Role: 卡片归档路由层，管理卡片的软删除（archive）与恢复，依赖 TrashService
# Note: 无前缀，直接以 /trash 和 /cards/{id}/archive|restore 路径注册
# Usage: 由 app/main.py 直接挂载，前端回收站页面和卡片操作菜单调用
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlmodel import Session

from app.api.dependencies import get_trash_service
from app.db.session import get_session
from app.schemas.card import CardRead
from app.services.trash_service import TrashService

router = APIRouter(tags=["trash"])


class TrashClearResult(BaseModel):
    deleted_count: int


@router.get("/trash", response_model=list[CardRead])
def list_trash(session: Session = Depends(get_session), service: TrashService = Depends(get_trash_service)) -> list[CardRead]:
    return [CardRead.model_validate(card) for card in service.list_trash(session)]


@router.post("/cards/{card_id}/archive", response_model=CardRead)
def archive_card(card_id: int, session: Session = Depends(get_session), service: TrashService = Depends(get_trash_service)) -> CardRead:
    return CardRead.model_validate(service.archive_card(session, card_id))


@router.post("/cards/{card_id}/restore", response_model=CardRead)
def restore_card(card_id: int, session: Session = Depends(get_session), service: TrashService = Depends(get_trash_service)) -> CardRead:
    return CardRead.model_validate(service.restore_card(session, card_id))


@router.delete("/trash/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_card(
    card_id: int,
    session: Session = Depends(get_session),
    service: TrashService = Depends(get_trash_service),
) -> None:
    service.permanently_delete_card(session, card_id)


@router.delete("/trash", response_model=TrashClearResult)
def clear_trash(session: Session = Depends(get_session), service: TrashService = Depends(get_trash_service)) -> TrashClearResult:
    return TrashClearResult(deleted_count=service.clear_trash(session))
