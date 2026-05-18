# Input: EvaluationRequest（目标知识单元 + 学习者解释文本）
# Output: EvaluationRead（AI 评分及反馈结果）
# Role: AI 评估路由层，将前端答题内容转发给 EvaluationService 调用远端 AI
# Note: 评估本身仍由 provider 计算；若提供 card_id，则将结果同步写入 learning_event
# Usage: 由 app/main.py 以 /evaluations 前缀挂载，POST / 触发单次评估
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.dependencies import get_activity_service, get_evaluation_service
from app.db.models import Card, KnowledgeUnit
from app.db.session import get_session
from app.schemas.activity import CardActivityItem
from app.schemas.evaluation import EvaluationRead, EvaluationRecordRequest, EvaluationRequest
from app.services.activity_service import ActivityService
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("", response_model=EvaluationRead, status_code=status.HTTP_200_OK)
def create_evaluation(
    payload: EvaluationRequest,
    service: EvaluationService = Depends(get_evaluation_service),
    activity_service: ActivityService = Depends(get_activity_service),
    session: Session = Depends(get_session),
) -> EvaluationRead:
    card: Card | None = None
    knowledge_unit: KnowledgeUnit | None = None
    if payload.card_id is not None:
        card = session.get(Card, payload.card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")
        if card.knowledge_unit_ref_id is not None:
            knowledge_unit = session.get(KnowledgeUnit, card.knowledge_unit_ref_id)

    enriched_payload = payload.model_copy(
        update={
            "target_card": _target_card_payload(card) if card is not None else payload.target_card,
            "target_unit": _target_unit_payload(
                knowledge_unit,
                related_units=_related_knowledge_units(session, knowledge_unit) if knowledge_unit is not None else [],
            )
            if knowledge_unit is not None
            else payload.target_unit,
        }
    )
    try:
        result = EvaluationRead.model_validate(
            service.evaluate(enriched_payload, card=card, knowledge_unit=knowledge_unit)
        )
    except RuntimeError as exc:
        raise _plugin_error_to_http_exception(exc) from exc
    if card is not None and payload.persist:
        activity_service.record_evaluation(
            session,
            card=card,
            knowledge_unit=knowledge_unit,
            learner_explanation=payload.learner_explanation,
            result=result,
        )
    return result


@router.post("/records", response_model=CardActivityItem, status_code=status.HTTP_201_CREATED)
def save_evaluation_record(
    payload: EvaluationRecordRequest,
    activity_service: ActivityService = Depends(get_activity_service),
    session: Session = Depends(get_session),
) -> CardActivityItem:
    card = session.get(Card, payload.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    knowledge_unit = (
        session.get(KnowledgeUnit, card.knowledge_unit_ref_id)
        if card.knowledge_unit_ref_id is not None
        else None
    )
    event = activity_service.record_evaluation(
        session,
        card=card,
        knowledge_unit=knowledge_unit,
        learner_explanation=payload.learner_explanation,
        result=payload.result,
    )
    return activity_service.learning_event_to_activity_item(event)


def _target_card_payload(card: Card | None) -> dict[str, object] | None:
    if card is None:
        return None
    return {
        "id": card.id,
        "card_type": card.card_type,
        "front": card.front,
        "back": card.back,
        "tags": list(card.tags or []),
    }


def _target_unit_payload(unit: KnowledgeUnit | None, *, related_units: list[KnowledgeUnit] | None = None) -> dict[str, object]:
    if unit is None:
        return {}
    raw_payload = dict(unit.raw_payload or {})
    related_payload = [_related_unit_payload(related_unit) for related_unit in related_units or []]
    rag_context = _raw_text(raw_payload, "rag_context") or _raw_text(raw_payload, "merged_context_text") or _raw_text(raw_payload, "context")
    retrieved_contexts = _raw_list(raw_payload, "retrieved_contexts")
    question_plans = _raw_list(raw_payload, "question_plans")
    support_linked_members = _raw_list(raw_payload, "support_linked_members")
    relation_linked_members = _raw_list(raw_payload, "relation_linked_members")
    relation_resolution = raw_payload.get("relation_resolution")
    has_rag_payload_context = bool(
        rag_context or retrieved_contexts or question_plans or support_linked_members or relation_linked_members
    )
    return {
        "id": unit.id,
        "provider_unit_id": unit.provider_unit_id,
        "topic": unit.topic,
        "summary": unit.summary,
        "source_document": _unit_source_document(unit),
        "source_span": unit.source_span,
        "raw_payload": raw_payload,
        "rag_context": rag_context,
        "retrieved_contexts": retrieved_contexts,
        "question_plans": question_plans,
        "support_linked_members": support_linked_members,
        "relation_linked_members": relation_linked_members,
        "relation_resolution": relation_resolution,
        "related_units": related_payload,
        "context_debug": {
            "evidence_strategy": "rag_payload_context" if has_rag_payload_context else "same_source_neighbor_units",
            "rag_context_present": bool(rag_context),
            "retrieved_context_count": len(retrieved_contexts),
            "question_plan_count": len(question_plans),
            "support_linked_member_count": len(support_linked_members),
            "relation_linked_member_count": len(relation_linked_members),
            "related_evidence": [
                {
                    "provider_unit_id": related_unit["provider_unit_id"],
                    "topic": related_unit["topic"],
                }
                for related_unit in related_payload
            ],
        },
    }


def _raw_text(raw_payload: dict[str, object], key: str) -> str:
    value = raw_payload.get(key)
    return str(value).strip() if value is not None else ""


def _raw_list(raw_payload: dict[str, object], key: str) -> list[object]:
    value = raw_payload.get(key)
    return value if isinstance(value, list) else []


def _related_unit_payload(unit: KnowledgeUnit) -> dict[str, object]:
    return {
        "id": unit.id,
        "provider_unit_id": unit.provider_unit_id,
        "topic": unit.topic,
        "summary": unit.summary,
        "source_document": _unit_source_document(unit),
        "source_span": unit.source_span,
    }


def _related_knowledge_units(session: Session, unit: KnowledgeUnit, *, limit: int = 3) -> list[KnowledgeUnit]:
    if unit.id is None:
        return []
    source_document = _unit_source_document(unit)
    candidates = session.exec(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.deck_id == unit.deck_id)
        .where(KnowledgeUnit.id != unit.id)
    ).all()
    if source_document:
        candidates = [candidate for candidate in candidates if _unit_source_document(candidate) == source_document]
    return sorted(candidates, key=lambda candidate: _source_span_distance(unit, candidate))[:limit]


def _unit_source_document(unit: KnowledgeUnit) -> str | None:
    raw_source = (unit.raw_payload or {}).get("source_document")
    return unit.source_document or (str(raw_source) if raw_source else None)


def _source_span_distance(target: KnowledgeUnit, candidate: KnowledgeUnit) -> int:
    target_start = _span_start(target.source_span)
    candidate_start = _span_start(candidate.source_span)
    if target_start is None or candidate_start is None:
        return 1_000_000
    return abs(candidate_start - target_start)


def _span_start(source_span: dict[str, object] | None) -> int | None:
    if not source_span:
        return None
    value = source_span.get("line_start")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _plugin_error_to_http_exception(exc: RuntimeError) -> HTTPException:
    code = str(exc).split(":", 1)[0].strip() or "plugin_unhealthy"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    if code in {"evaluation_parse_failed", "provider_invalid_response"}:
        status_code = status.HTTP_502_BAD_GATEWAY
    return HTTPException(status_code=status_code, detail=code)
