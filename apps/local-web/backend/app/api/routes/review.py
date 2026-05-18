# Input: /review 下的 session 拉取、提交、撤销、历史查询与 legacy submit 请求
# Output: ReviewSessionRead、Submit/Undo 响应、历史列表，以及兼容旧链路的 ScheduleDecision
# Role: 这是复习主链路的 HTTP 入口，当前主路径是 session v3，旧 /submit 仅保留兼容
# Use: 新前端应优先走 /session、/session/{id}/submit、/undo；不要再把新功能挂到 legacy submit
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from app.api.dependencies import get_activity_service, get_review_service
from app.db.session import get_session
from app.schemas.card import CardRead
from app.schemas.activity import ReviewHistoryItem
from app.schemas.review import (
    ReviewSessionRead,
    ReviewSessionSubmitRequest,
    ReviewSessionSubmitResponse,
    ReviewSessionUndoResponse,
    ScheduleDecision,
)
from app.services.review_service import ReviewService
from app.services.activity_service import ActivityService

router = APIRouter(prefix="/review", tags=["review"])


class ReviewSubmitRequest(BaseModel):
    card_id: int
    grade: Literal["again", "hard", "good", "easy"]
    review_mode: str
    trigger_type: str
    note: str | None = None


@router.get("/queue", response_model=list[CardRead], status_code=status.HTTP_200_OK)
def get_review_queue(session: Session = Depends(get_session), service: ReviewService = Depends(get_review_service)) -> list[CardRead]:
    return [CardRead.model_validate(card) for card in service.list_queue(session)]


@router.get("/session", response_model=ReviewSessionRead, status_code=status.HTTP_200_OK)
def get_review_session(
    scope: Literal["deck", "all"] = "deck",
    deck_id: int | None = None,
    session: Session = Depends(get_session),
    service: ReviewService = Depends(get_review_service),
) -> ReviewSessionRead:
    return service.get_session(session, scope=scope, deck_id=deck_id)


@router.post(
    "/session/{session_id}/submit",
    response_model=ReviewSessionSubmitResponse,
    status_code=status.HTTP_200_OK,
)
def submit_review_session(
    session_id: str,
    payload: ReviewSessionSubmitRequest,
    session: Session = Depends(get_session),
    service: ReviewService = Depends(get_review_service),
) -> ReviewSessionSubmitResponse:
    return service.submit_session(
        session,
        session_id=session_id,
        card_id=payload.card_id,
        grade=payload.grade,
        review_mode=payload.review_mode,
        trigger_type=payload.trigger_type,
        note=payload.note,
    )


@router.post(
    "/session/{session_id}/undo",
    response_model=ReviewSessionUndoResponse,
    status_code=status.HTTP_200_OK,
)
def undo_review_session(
    session_id: str,
    session: Session = Depends(get_session),
    service: ReviewService = Depends(get_review_service),
) -> ReviewSessionUndoResponse:
    return service.undo_session(session, session_id=session_id)


@router.post(
    "/submit",
    response_model=ScheduleDecision,
    status_code=status.HTTP_200_OK,
    deprecated=True,
    summary="Legacy review submit",
)
def submit_review(payload: ReviewSubmitRequest, session: Session = Depends(get_session), service: ReviewService = Depends(get_review_service)) -> ScheduleDecision:
    return service.submit(session, card_id=payload.card_id, grade=payload.grade, review_mode=payload.review_mode, trigger_type=payload.trigger_type, note=payload.note)


@router.get("/history", response_model=list[ReviewHistoryItem], status_code=status.HTTP_200_OK)
def get_review_history(
    deck_id: int | None = None,
    card_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
    service: ActivityService = Depends(get_activity_service),
) -> list[ReviewHistoryItem]:
    return service.list_review_history(session, deck_id=deck_id, card_id=card_id, limit=limit)
