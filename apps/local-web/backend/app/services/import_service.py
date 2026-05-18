# Input: Session + ImportCardsRequest（format + payload/deck_name）
# Output: (Deck, list[Card]) 元组，已持久化到数据库
# Role: 数据导入服务，解析 json/csv/markdown 格式并调用 DeckService/CardService 写库
# Note: 每次导入均创建新 Deck；json 格式需符合 ImportBundle 结构；不支持幂等导入
from __future__ import annotations

import json

from sqlmodel import Session

from app.providers.importer.csv_importer import import_csv_cards
from app.providers.importer.json_importer import ImportBundle, import_json_cards
from app.providers.importer.markdown_importer import import_markdown_cards
from app.schemas.card import CardCreate
from app.schemas.imports import ImportCardsRequest
from app.services.card_service import CardService
from app.services.deck_service import DeckService


class ImportService:
    def __init__(
        self,
        *,
        deck_service: DeckService | None = None,
        card_service: CardService | None = None,
    ) -> None:
        self.deck_service = deck_service or DeckService()
        self.card_service = card_service or CardService()

    def import_cards(self, session: Session, payload: ImportCardsRequest):
        bundle = self._to_bundle(payload)

        deck = self.deck_service.create_deck(session, bundle.deck)
        created_cards = []
        for card in bundle.cards:
            created_cards.append(
                self.card_service.create_card(
                    session,
                    CardCreate(
                        deck_id=deck.id,
                        card_type=card.card_type,
                        front=card.front,
                        back=card.back,
                        render_format=card.render_format,
                        tags=card.tags,
                    ),
                )
            )

        return deck, created_cards

    def _to_bundle(self, payload: ImportCardsRequest) -> ImportBundle:
        if payload.format == "json":
            parsed = json.loads(payload.payload)
            return import_json_cards(parsed)

        if payload.format == "csv":
            deck_name = payload.deck_name or "Imported Cards"
            return import_csv_cards(payload.payload, deck_name=deck_name)

        deck_name = payload.deck_name or "Imported Cards"
        return import_markdown_cards(payload.payload, deck_name=deck_name)
