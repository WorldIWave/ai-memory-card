# Input: Session 与 CardCreate/CardUpdate 等业务 payload  |  Output: Card ORM 实例及其 review_state 副作用
# Output: 封装卡片列表、创建、编辑、归档/恢复等生命周期操作
# Role: 这是 cards 路由背后的核心业务层，并负责创建卡片时初始化 CardReviewState
# Use: 任何卡片字段或删除语义变更都应先收敛到这里，别在 route 中直接改 ORM
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from app.db.models import Card, CardReviewState, Deck
from app.schemas.card import CardCreate, CardUpdate


class CardService:
    def list_cards(self, session: Session, include_archived: bool = False) -> list[Card]:
        statement = select(Card)
        if not include_archived:
            statement = statement.where(Card.status == "active", Card.deleted_at.is_(None))
        return list(session.exec(statement).all())

    def create_card(self, session: Session, payload: CardCreate) -> Card:
        card = Card(
            deck_id=payload.deck_id,
            card_type=payload.card_type,
            front=payload.front,
            back=payload.back,
            render_format=payload.render_format,
            tags=payload.tags,
        )
        session.add(card)
        session.flush()

        review_state = CardReviewState(card_id=card.id, scheduler_type="sm2_basic")
        session.add(review_state)
        session.commit()
        session.refresh(card)
        return card

    def update_card(self, session: Session, card_id: int, payload: CardUpdate) -> Card:
        card = session.get(Card, card_id)
        if card is None or card.status != "active" or card.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Card not found")

        deck = session.get(Deck, payload.deck_id)
        if deck is None:
            raise HTTPException(status_code=404, detail="Deck not found")

        content_changed = (
            card.deck_id != payload.deck_id
            or card.card_type != payload.card_type
            or card.front != payload.front
            or card.back != payload.back
            or card.render_format != payload.render_format
            or card.tags != payload.tags
        )

        card.deck_id = payload.deck_id
        card.card_type = payload.card_type
        card.front = payload.front
        card.back = payload.back
        card.render_format = payload.render_format
        card.tags = payload.tags
        card.updated_at = datetime.now(timezone.utc)
        if content_changed:
            card.content_version += 1

        session.add(card)
        session.commit()
        session.refresh(card)
        return card
