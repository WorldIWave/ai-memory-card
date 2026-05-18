# Input: Session 与 DeckCreate/DeckUpdate 等业务 payload  |  Output: Deck ORM 实例及相关级联副作用
# Output: 封装牌组创建、编辑、归档、恢复、删除与文件夹迁移相关规则
# Role: 这是牌组生命周期的业务核心，保护同名冲突和级联卡片状态一致性
# Use: 改动 deck visibility/folder 规则时优先收敛到这里，再让 routes 保持薄层
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.errors import NotFoundError
from app.db.models import Card, CardReviewState, Deck, Folder, KnowledgeUnit, LearningEvent, ReviewLog, ReviewSession
from app.schemas.deck import DeckCreate, DeckUpdate


class DeckService:
    def list_decks(self, session: Session, include_archived: bool = False) -> list[Deck]:
        statement = select(Deck)
        if not include_archived:
            statement = statement.where(Deck.visibility != "archived", Deck.deleted_at.is_(None))
        return list(session.exec(statement).all())

    def name_exists(self, session: Session, name: str) -> bool:
        return (
            session.exec(
                select(Deck).where(
                    Deck.name == name,
                    Deck.visibility != "archived",
                    Deck.deleted_at.is_(None),
                )
            ).first()
            is not None
        )

    def delete_deck(self, session: Session, deck_id: int) -> None:
        deck = session.get(Deck, deck_id)
        if deck is None:
            raise NotFoundError("Deck", deck_id)

        self.delete_deck_record(session, deck)
        session.commit()

    def delete_deck_record(self, session: Session, deck: Deck) -> None:
        deck_id = deck.id
        if deck_id is None:
            return

        cards = list(session.exec(select(Card).where(Card.deck_id == deck_id)).all())
        for card in cards:
            review_state = session.get(CardReviewState, card.id)
            if review_state is not None:
                session.delete(review_state)
            for review_log in session.exec(select(ReviewLog).where(ReviewLog.card_id == card.id)).all():
                session.delete(review_log)
            for learning_event in session.exec(select(LearningEvent).where(LearningEvent.card_id == card.id)).all():
                session.delete(learning_event)
            session.delete(card)

        for learning_event in session.exec(select(LearningEvent).where(LearningEvent.deck_id == deck_id)).all():
            session.delete(learning_event)
        for knowledge_unit in session.exec(select(KnowledgeUnit).where(KnowledgeUnit.deck_id == deck_id)).all():
            session.delete(knowledge_unit)
        for review_session in session.exec(select(ReviewSession).where(ReviewSession.deck_id == deck_id)).all():
            session.delete(review_session)

        session.delete(deck)

    def create_deck(self, session: Session, payload: DeckCreate) -> Deck:
        deck = Deck(name=payload.name, description=payload.description, folder_id=payload.folder_id)
        session.add(deck)
        session.commit()
        session.refresh(deck)
        return deck

    def update_deck(self, session: Session, deck_id: int, payload: DeckUpdate) -> Deck:
        deck = session.get(Deck, deck_id)
        if deck is None:
            raise HTTPException(status_code=404, detail="Deck not found")

        folder = session.get(Folder, payload.folder_id)
        if folder is None:
            raise HTTPException(status_code=404, detail="Folder not found")

        duplicate = session.exec(
            select(Deck).where(
                Deck.name == payload.name,
                Deck.id != deck_id,
                Deck.visibility != "archived",
                Deck.deleted_at.is_(None),
            )
        ).first()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Deck name already exists")

        deck.name = payload.name
        deck.description = payload.description
        deck.folder_id = payload.folder_id
        deck.updated_at = datetime.now(timezone.utc)
        session.add(deck)
        session.commit()
        session.refresh(deck)
        return deck

    def archive_deck(self, session: Session, deck_id: int) -> Deck:
        deck = session.get(Deck, deck_id)
        if deck is None:
            raise NotFoundError("Deck", deck_id)

        now = datetime.now(timezone.utc)
        deck.visibility = "archived"
        deck.deleted_at = now
        deck.updated_at = now
        session.add(deck)

        cards = list(session.exec(select(Card).where(Card.deck_id == deck_id)).all())
        for card in cards:
            card.status = "archived"
            card.deleted_at = now
            card.updated_at = now
            session.add(card)

        session.commit()
        session.refresh(deck)
        return deck

    def restore_deck(self, session: Session, deck_id: int) -> Deck:
        deck = session.get(Deck, deck_id)
        if deck is None:
            raise NotFoundError("Deck", deck_id)

        now = datetime.now(timezone.utc)
        deck.visibility = "normal"
        deck.deleted_at = None
        deck.updated_at = now
        session.add(deck)

        cards = list(session.exec(select(Card).where(Card.deck_id == deck_id)).all())
        for card in cards:
            card.status = "active"
            card.deleted_at = None
            card.updated_at = now
            session.add(card)

        session.commit()
        session.refresh(deck)
        return deck
