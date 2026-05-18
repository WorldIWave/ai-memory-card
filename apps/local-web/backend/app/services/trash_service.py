# Input: Session + card_id  |  Output: Card ORM 对象（归档/恢复后）或 Card 列表（查询）
# Role: 卡片回收站服务，提供单张卡片的软删除（archived）与恢复（active），被 trash 路由调用
# Note: 仅操作单张卡片状态；牌组级别的批量归档由 DeckService 负责，不在此处处理
# Usage: TrashService().archive_card(session, id) / .restore_card(session, id)
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.errors import NotFoundError
from app.db.models import Card, CardReviewState, LearningEvent, ReviewLog


class TrashService:
    def list_trash(self, session: Session) -> list[Card]:
        return list(session.exec(select(Card).where(Card.status == "archived")).all())

    def archive_card(self, session: Session, card_id: int) -> Card:
        card = session.get(Card, card_id)
        if card is None:
            raise NotFoundError("Card", card_id)
        now = datetime.now(timezone.utc)
        card.status = "archived"
        card.deleted_at = now
        card.updated_at = now
        session.add(card)
        session.commit()
        session.refresh(card)
        return card

    def restore_card(self, session: Session, card_id: int) -> Card:
        card = session.get(Card, card_id)
        if card is None:
            raise NotFoundError("Card", card_id)
        now = datetime.now(timezone.utc)
        card.status = "active"
        card.deleted_at = None
        card.updated_at = now
        session.add(card)
        session.commit()
        session.refresh(card)
        return card

    def permanently_delete_card(self, session: Session, card_id: int) -> None:
        card = session.get(Card, card_id)
        if card is None or card.status != "archived":
            raise NotFoundError("Card", card_id)

        self._delete_card_rows(session, card)
        session.commit()

    def clear_trash(self, session: Session) -> int:
        cards = list(session.exec(select(Card).where(Card.status == "archived")).all())
        for card in cards:
            self._delete_card_rows(session, card)
        session.commit()
        return len(cards)

    def _delete_card_rows(self, session: Session, card: Card) -> None:
        review_state = session.get(CardReviewState, card.id)
        if review_state is not None:
            session.delete(review_state)
        for review_log in session.exec(select(ReviewLog).where(ReviewLog.card_id == card.id)).all():
            session.delete(review_log)
        for learning_event in session.exec(select(LearningEvent).where(LearningEvent.card_id == card.id)).all():
            session.delete(learning_event)
        session.delete(card)
