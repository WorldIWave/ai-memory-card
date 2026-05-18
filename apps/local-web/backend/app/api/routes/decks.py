# Input: /decks 下的列表、创建、编辑、归档、恢复、删除请求  |  Output: DeckRead API 响应或空体状态码
# Output: 暴露牌组生命周期 HTTP 接口，供 library/review 页读取和管理牌组
# Role: 这是 deck_service 的路由封装层，负责把业务异常转成合适的 HTTP 响应
# Use: 保持这里尽量薄；同名冲突、级联归档等规则应继续放在 service 层
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_deck_service
from app.db.session import get_session
from app.schemas.deck import DeckCreate, DeckRead, DeckUpdate
from app.services.deck_service import DeckService

router = APIRouter(prefix="/decks", tags=["decks"])


@router.get("", response_model=list[DeckRead])
def list_decks(include_archived: bool = False, session: Session = Depends(get_session), service: DeckService = Depends(get_deck_service)) -> list[DeckRead]:
    return [DeckRead.model_validate(deck) for deck in service.list_decks(session, include_archived=include_archived)]


@router.post("", response_model=DeckRead, status_code=status.HTTP_201_CREATED)
def create_deck(payload: DeckCreate, session: Session = Depends(get_session), service: DeckService = Depends(get_deck_service)) -> DeckRead:
    if service.name_exists(session, payload.name):
        raise HTTPException(status_code=409, detail="同名牌组已存在")
    return DeckRead.model_validate(service.create_deck(session, payload))


@router.put("/{deck_id}", response_model=DeckRead)
def update_deck(
    deck_id: int,
    payload: DeckUpdate,
    session: Session = Depends(get_session),
    service: DeckService = Depends(get_deck_service),
) -> DeckRead:
    return DeckRead.model_validate(service.update_deck(session, deck_id, payload))


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(deck_id: int, session: Session = Depends(get_session), service: DeckService = Depends(get_deck_service)) -> None:
    service.delete_deck(session, deck_id)


@router.post("/{deck_id}/archive", response_model=DeckRead)
def archive_deck(deck_id: int, session: Session = Depends(get_session), service: DeckService = Depends(get_deck_service)) -> DeckRead:
    return DeckRead.model_validate(service.archive_deck(session, deck_id))


@router.post("/{deck_id}/restore", response_model=DeckRead)
def restore_deck(deck_id: int, session: Session = Depends(get_session), service: DeckService = Depends(get_deck_service)) -> DeckRead:
    return DeckRead.model_validate(service.restore_deck(session, deck_id))
