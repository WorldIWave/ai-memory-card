# Input: local text documents, generation prefs, and knowledge-unit query params | Output: imported cards/units
# Role: Bridges remote RAG generation into local persistence and exposes stored knowledge units
# Note: Documents are text payloads from the frontend; binary parsing remains outside this route
# Usage: POST /api/ai/rag/import-cards or GET /api/ai/knowledge-units?deck_id=1
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_ai_plugin_host_service, get_knowledge_unit_service, get_rag_import_service
from app.db.session import get_session
from app.schemas.ai_generation import RAGImportCardsRequest, RAGImportCardsResponse
from app.schemas.ai_plugin import PluginConfigRead, PluginConfigUpdateInput, PluginStatusRead
from app.schemas.card import CardRead
from app.schemas.deck import DeckRead
from app.schemas.knowledge_unit import KnowledgeUnitRead
from app.services.ai_plugin_host_service import AIPluginHostService
from app.services.knowledge_unit_service import KnowledgeUnitService
from app.services.rag_import_service import RAGImportService

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)


@router.post("/rag/import-cards", response_model=RAGImportCardsResponse, status_code=status.HTTP_201_CREATED)
def import_rag_generated_cards(
    payload: RAGImportCardsRequest,
    session: Session = Depends(get_session),
    service: RAGImportService = Depends(get_rag_import_service),
) -> RAGImportCardsResponse:
    try:
        result = service.import_generated_cards(session, payload)
    except RuntimeError as exc:
        logger.warning("RAG import failed with runtime error: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("RAG import failed unexpectedly")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc) or "RAG import failed") from exc
    finally:
        service.close()

    return RAGImportCardsResponse(
        deck=DeckRead.model_validate(result["deck"]),
        cards=[CardRead.model_validate(card) for card in result["cards"]],
        imported_count=len(result["cards"]),
        knowledge_units=result["knowledge_units"],
        warnings=result["warnings"],
        provider_meta=result["provider_meta"],
    )


@router.get("/knowledge-units", response_model=list[KnowledgeUnitRead])
def list_knowledge_units(
    deck_id: int | None = None,
    session: Session = Depends(get_session),
    service: KnowledgeUnitService = Depends(get_knowledge_unit_service),
) -> list[KnowledgeUnitRead]:
    return [KnowledgeUnitRead.model_validate(unit) for unit in service.list_units(session, deck_id=deck_id)]


@router.get("/plugins/rag-core", response_model=PluginStatusRead)
def get_rag_plugin_status(
    service: AIPluginHostService = Depends(get_ai_plugin_host_service),
) -> PluginStatusRead:
    return PluginStatusRead.model_validate(service.get_plugin_status("rag-core"))


@router.put("/plugins/rag-core/config", response_model=PluginConfigRead)
def update_rag_plugin_config(
    payload: PluginConfigUpdateInput,
    service: AIPluginHostService = Depends(get_ai_plugin_host_service),
) -> PluginConfigRead:
    return PluginConfigRead.model_validate(service.save_plugin_config("rag-core", payload.model_dump(mode="json")))


@router.post("/plugins/rag-core/test", response_model=PluginStatusRead)
def test_rag_plugin(
    service: AIPluginHostService = Depends(get_ai_plugin_host_service),
) -> PluginStatusRead:
    try:
        return PluginStatusRead.model_validate(service.test_plugin("rag-core"))
    except RuntimeError as exc:
        logger.warning("RAG plugin test failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
