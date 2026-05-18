# Input: RAG provider knowledge unit payloads and deck IDs | Output: persisted KnowledgeUnit rows
# Role: Owns local storage and lookup of structured knowledge units produced during AI card generation
# Note: The first version records every import result; duplicate detection can be layered on later
# Usage: RAGImportService saves units, and routes/ai.py lists them for inspection/integration
from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.db.models import KnowledgeUnit


class KnowledgeUnitService:
    def list_units(self, session: Session, *, deck_id: int | None = None) -> list[KnowledgeUnit]:
        statement = select(KnowledgeUnit)
        if deck_id is not None:
            statement = statement.where(KnowledgeUnit.deck_id == deck_id)
        statement = statement.order_by(KnowledgeUnit.created_at, KnowledgeUnit.id)
        return list(session.exec(statement).all())

    def create_imported_units(
        self,
        session: Session,
        *,
        deck_id: int,
        units: list[dict[str, Any]],
    ) -> dict[str, KnowledgeUnit]:
        created_by_provider_id: dict[str, KnowledgeUnit] = {}
        for index, unit_payload in enumerate(units, start=1):
            provider_unit_id = _provider_unit_id(unit_payload, index)
            unit = KnowledgeUnit(
                deck_id=deck_id,
                provider_unit_id=provider_unit_id,
                topic=_text_field(unit_payload, "topic", fallback=provider_unit_id),
                summary=_summary(unit_payload),
                source_document=_optional_text_field(unit_payload, "source_document", "source_doc", "filename"),
                source_span=_dict_field(unit_payload, "source_span"),
                raw_payload=unit_payload,
            )
            session.add(unit)
            session.flush()
            created_by_provider_id[provider_unit_id] = unit

        session.commit()
        for unit in created_by_provider_id.values():
            session.refresh(unit)
        return created_by_provider_id


def _provider_unit_id(unit_payload: dict[str, Any], index: int) -> str:
    for key in ("unit_id", "provider_unit_id", "id"):
        value = unit_payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return f"unit_{index}"


def _summary(unit_payload: dict[str, Any]) -> str:
    for key in ("summary", "concept_definition", "definition", "description", "text"):
        value = unit_payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return _text_field(unit_payload, "topic", fallback="")


def _text_field(unit_payload: dict[str, Any], key: str, *, fallback: str) -> str:
    value = unit_payload.get(key)
    if value is not None and str(value).strip():
        return str(value).strip()
    return fallback


def _optional_text_field(unit_payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = unit_payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _dict_field(unit_payload: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = unit_payload.get(key)
    return value if isinstance(value, dict) else None
