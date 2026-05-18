# Input: /cards 下的创建、更新、活动、报错、笔记请求  |  Output: CardRead 与 CardActivityItem API 响应
# Output: 暴露卡片 CRUD 和卡片活动时间线相关 HTTP 入口
# Role: 这是前端 library/review 页面访问卡片资源的路由层薄封装
# Use: 路由只做依赖注入和序列化；业务规则优先下沉到 CardService/ActivityService
from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.api.dependencies import get_activity_service, get_card_service
from app.db.session import get_session
from app.schemas.activity import CardActivityItem, CardNoteCreate, LearningEventCreate
from app.schemas.card import CardCreate, CardRead, CardUpdate
from app.services.activity_service import ActivityService
from app.services.card_service import CardService

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("", response_model=list[CardRead])
def list_cards(session: Session = Depends(get_session), service: CardService = Depends(get_card_service)) -> list[CardRead]:
    return [CardRead.model_validate(card) for card in service.list_cards(session)]


@router.post("", response_model=CardRead, status_code=status.HTTP_201_CREATED)
def create_card(payload: CardCreate, session: Session = Depends(get_session), service: CardService = Depends(get_card_service)) -> CardRead:
    return CardRead.model_validate(service.create_card(session, payload))


@router.put("/{card_id}", response_model=CardRead)
def update_card(
    card_id: int,
    payload: CardUpdate,
    session: Session = Depends(get_session),
    service: CardService = Depends(get_card_service),
) -> CardRead:
    return CardRead.model_validate(service.update_card(session, card_id, payload))


@router.post(
    "/{card_id}/report",
    response_model=CardActivityItem,
    status_code=status.HTTP_201_CREATED,
)
def report_card_issue(
    card_id: int,
    payload: LearningEventCreate,
    session: Session = Depends(get_session),
    service: ActivityService = Depends(get_activity_service),
) -> CardActivityItem:
    event = service.record_report_error(session, card_id=card_id, reason=payload.reason, note=payload.note)
    return service.learning_event_to_activity_item(event)


@router.post(
    "/{card_id}/notes",
    response_model=CardActivityItem,
    status_code=status.HTTP_201_CREATED,
)
def create_card_note(
    card_id: int,
    payload: CardNoteCreate,
    session: Session = Depends(get_session),
    service: ActivityService = Depends(get_activity_service),
) -> CardActivityItem:
    event = service.record_note(session, card_id=card_id, note=payload.note, source=payload.source)
    return service.learning_event_to_activity_item(event)


@router.get("/{card_id}/activity", response_model=list[CardActivityItem])
def get_card_activity(
    card_id: int,
    session: Session = Depends(get_session),
    service: ActivityService = Depends(get_activity_service),
) -> list[CardActivityItem]:
    return service.list_card_activity(session, card_id=card_id)
