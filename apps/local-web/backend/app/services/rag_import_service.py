# Input: Session, RAGImportCardsRequest, and local AI plugin capability | Output: persisted deck/cards/knowledge units
# Role: Orchestrates plugin-backed RAG generation, local card import, and card-to-unit source linking
# Note: knowledge_units are now stored locally; generated cards keep knowledge_unit_ref_id when matched
# Usage: routes/ai.py calls RAGImportService.import_generated_cards()
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.db.models import Deck
from app.schemas.ai_generation import RAGImportCardsRequest
from app.schemas.card import CardCreate
from app.schemas.imports import ImportCardsRequest
from app.services.ai_plugin_host_service import AIPluginHostService
from app.services.card_service import CardService
from app.services.import_service import ImportService
from app.services.knowledge_unit_service import KnowledgeUnitService


class RAGImportService:
    def __init__(
        self,
        *,
        plugin_host_service: AIPluginHostService | None = None,
        import_service: ImportService | None = None,
        knowledge_unit_service: KnowledgeUnitService | None = None,
        card_service: CardService | None = None,
    ) -> None:
        self.plugin_host_service = plugin_host_service or AIPluginHostService.from_settings()
        self.import_service = import_service or ImportService()
        self.knowledge_unit_service = knowledge_unit_service or KnowledgeUnitService()
        self.card_service = card_service or CardService()

    def import_generated_cards(self, session: Session, payload: RAGImportCardsRequest):
        target_deck = _target_deck(session, payload.deck_id)
        deck_name = target_deck.name if target_deck is not None else payload.deck_name.strip() if payload.deck_name else "AI Generated Cards"
        remote_payload = self.plugin_host_service.run_rag_generate_cards(
            {
                "capability": "rag.generate_cards",
                "mode": "api",
                "provider_profile": "openai_compatible",
                "deck": {"name": deck_name},
                "documents": [document.model_dump() for document in payload.documents],
                "topics": payload.topics,
                "generation_prefs": payload.generation_prefs.model_dump(),
            }
        )
        remote_cards = _dict_list(remote_payload.get("cards"))
        remote_units = _dict_list(remote_payload.get("knowledge_units"))
        if target_deck is not None:
            deck = target_deck
            cards = [
                self.card_service.create_card(session, CardCreate(deck_id=deck.id, **_card_for_import(card)))
                for card in remote_cards
                if deck.id is not None
            ]
        else:
            import_payload = {
                "deck": _deck_for_import(remote_payload.get("deck"), deck_name),
                "cards": [_card_for_import(card) for card in remote_cards],
            }
            deck, cards = self.import_service.import_cards(
                session,
                ImportCardsRequest(
                    format="json",
                    payload=json.dumps(import_payload, ensure_ascii=False),
                ),
            )
        local_units_by_provider_id = self.knowledge_unit_service.create_imported_units(
            session,
            deck_id=deck.id,
            units=remote_units,
        )
        _attach_knowledge_units(session, cards=cards, remote_cards=remote_cards, units_by_provider_id=local_units_by_provider_id)
        return {
            "deck": deck,
            "cards": cards,
            "knowledge_units": remote_units,
            "warnings": remote_payload.get("warnings") or [],
            "provider_meta": remote_payload.get("provider_meta") or {},
        }

    def close(self) -> None:
        close = getattr(self.plugin_host_service, "close", None)
        if callable(close):
            close()


def _target_deck(session: Session, deck_id: int | None) -> Deck | None:
    if deck_id is None:
        return None
    deck = session.get(Deck, deck_id)
    if deck is None or deck.visibility == "archived" or deck.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck


def _deck_for_import(value: object, fallback_name: str) -> dict[str, object]:
    if isinstance(value, dict):
        name = str(value.get("name") or "").strip() or fallback_name
        return {"name": name}
    return {"name": fallback_name}


def _card_for_import(value: object) -> dict[str, object]:
    card = value if isinstance(value, dict) else {}
    return {
        "card_type": str(card.get("card_type") or "recall"),
        "front": str(card.get("front") or ""),
        "back": str(card.get("back") or ""),
        "render_format": str(card.get("render_format") or "markdown"),
        "tags": card.get("tags") if isinstance(card.get("tags"), list) else [],
    }


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _attach_knowledge_units(
    session: Session,
    *,
    cards: list[Any],
    remote_cards: list[dict[str, Any]],
    units_by_provider_id: dict[str, Any],
) -> None:
    if not cards or not units_by_provider_id:
        return

    for card, remote_card in zip(cards, remote_cards, strict=False):
        source_unit_id = _source_unit_id(remote_card)
        unit = units_by_provider_id.get(source_unit_id) if source_unit_id is not None else None
        if unit is None and source_unit_id is None and len(units_by_provider_id) == 1:
            unit = next(iter(units_by_provider_id.values()))
        if unit is None:
            continue
        card.knowledge_unit_ref_id = unit.id
        card.source_type = "ai_rag"
        session.add(card)

    session.commit()
    for card in cards:
        session.refresh(card)


def _source_unit_id(remote_card: dict[str, Any]) -> str | None:
    for key in ("source_unit_id", "unit_id", "knowledge_unit_id", "provider_unit_id"):
        value = remote_card.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None
