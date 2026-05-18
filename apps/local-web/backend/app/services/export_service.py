# Input: Session + export_format（json/csv/markdown）  |  Output: ExportCardsResponse
# Role: 数据导出服务，将全库 Deck+Card 序列化为三种格式，被 exports 路由调用
# Note: 仅导出 active 状态的 deck/card，不含归档数据；依赖 DeckService/CardService
# Usage: ExportService().export_cards(session, "json" | "csv" | "markdown")
from __future__ import annotations

import csv
from io import StringIO
from typing import Literal

from sqlmodel import Session

from app.schemas.card import CardRead
from app.schemas.deck import DeckRead
from app.schemas.exports import ExportCardsResponse
from app.services.card_service import CardService
from app.services.deck_service import DeckService


class ExportService:
    def __init__(
        self,
        *,
        deck_service: DeckService | None = None,
        card_service: CardService | None = None,
    ) -> None:
        self.deck_service = deck_service or DeckService()
        self.card_service = card_service or CardService()

    def export_cards(
        self,
        session: Session,
        export_format: Literal["json", "csv", "markdown"],
    ) -> ExportCardsResponse:
        decks = self.deck_service.list_decks(session)
        cards = self.card_service.list_cards(session)

        if export_format == "json":
            return ExportCardsResponse(
                format="json",
                payload={
                    "decks": [DeckRead.model_validate(deck).model_dump(mode="json") for deck in decks],
                    "cards": [CardRead.model_validate(card).model_dump(mode="json") for card in cards],
                },
            )

        deck_lookup = {deck.id: deck.name for deck in decks if deck.id is not None}

        if export_format == "csv":
            buffer = StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["front", "back", "card_type", "deck_name"])
            for card in cards:
                writer.writerow([
                    card.front,
                    card.back,
                    card.card_type,
                    deck_lookup.get(card.deck_id, ""),
                ])
            return ExportCardsResponse(format="csv", payload=buffer.getvalue())

        markdown_chunks: list[str] = []
        for card in cards:
            markdown_chunks.append(
                "\n".join(
                    [
                        "## Card",
                        f"Deck: {deck_lookup.get(card.deck_id, '')}",
                        f"Front: {card.front}",
                        f"Back: {card.back}",
                        f"Type: {card.card_type}",
                    ]
                )
            )
        payload = "\n\n".join(markdown_chunks)
        return ExportCardsResponse(format="markdown", payload=payload)
