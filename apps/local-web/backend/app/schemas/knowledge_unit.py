# Input: KnowledgeUnit ORM rows | Output: API-safe knowledge unit DTOs
# Role: Defines the local contract for listing AI-generated knowledge units after RAG imports
# Note: raw_payload intentionally remains available for future evaluation/debugging without schema churn
# Usage: routes/ai.py returns KnowledgeUnitRead from KnowledgeUnitService
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class KnowledgeUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deck_id: int
    provider_unit_id: str
    topic: str
    summary: str
    source_document: str | None = None
    source_span: dict[str, Any] | None = None
    raw_payload: dict[str, Any]
    created_at: datetime
