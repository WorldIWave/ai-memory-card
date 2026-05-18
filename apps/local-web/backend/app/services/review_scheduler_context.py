# Input: review DB session, card state, grade, session context, and baseline decision
# Output: plugin payload for scheduler.plan_review
# Role: Keeps ReviewService small while giving the AI/RL scheduler bounded local context
# Use: The payload is advisory; plugin output must still be validated before persistence
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from app.db.models import Card, CardReviewState, KnowledgeUnit, LearningEvent, ReviewLog
from app.schemas.review import ReviewSessionContext, SessionScheduleResult


def build_scheduler_plan_payload(
    db: Session,
    *,
    card: Card,
    state: CardReviewState,
    grade: str,
    context: ReviewSessionContext,
    baseline_decision: SessionScheduleResult,
) -> dict[str, Any]:
    latest_evaluation = db.exec(
        select(LearningEvent)
        .where(LearningEvent.card_id == card.id)
        .where(LearningEvent.event_type == "evaluation")
        .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
        .limit(1)
    ).first()
    recent_logs = db.exec(
        select(ReviewLog)
        .where(ReviewLog.card_id == card.id)
        .where(ReviewLog.trigger_type == "scheduled")
        .order_by(ReviewLog.reviewed_at.desc(), ReviewLog.id.desc())
        .limit(20)
    ).all()
    knowledge_unit = (
        db.get(KnowledgeUnit, card.knowledge_unit_ref_id)
        if card.knowledge_unit_ref_id is not None
        else None
    )
    return {
        "capability": "scheduler.plan_review",
        "mode": "local",
        "grade": grade,
        "card": {
            "id": card.id,
            "deck_id": card.deck_id,
            "knowledge_unit_ref_id": card.knowledge_unit_ref_id,
            "card_type": card.card_type,
            "front": card.front,
            "back": card.back,
            "tags": list(card.tags or []),
        },
        "state": {
            "scheduler_type": state.scheduler_type,
            "interval_days": state.interval_days,
            "ease_factor": state.ease_factor,
            "repetition_count": state.repetition_count,
            "lapses": state.lapses,
            "learning_state": state.learning_state,
            "learning_step": state.learning_step,
            "session_repeats_today": state.session_repeats_today,
            "hard_attempts_today": state.hard_attempts_today,
            "last_reviewed_at": _iso(state.last_reviewed_at),
            "next_due_at": _iso(state.next_due_at),
        },
        "knowledge_unit": _knowledge_unit_payload(knowledge_unit),
        "review_history": [
            {
                "grade": log.grade,
                "interval_days": log.interval_days,
                "reviewed_at": _iso(log.reviewed_at),
            }
            for log in recent_logs
        ],
        "understanding": latest_evaluation.payload_json if latest_evaluation is not None else None,
        "recent_burden": {
            "remaining_cards": len(context.remaining_card_ids),
            "session_repeats_today": state.session_repeats_today,
            "hard_attempts_today": state.hard_attempts_today,
        },
        "baseline_decision": baseline_decision.model_dump(mode="json"),
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _knowledge_unit_payload(knowledge_unit: KnowledgeUnit | None) -> dict[str, Any] | None:
    if knowledge_unit is None:
        return None
    return {
        "id": knowledge_unit.id,
        "provider_unit_id": knowledge_unit.provider_unit_id,
        "topic": knowledge_unit.topic,
        "summary": knowledge_unit.summary,
        "source_document": knowledge_unit.source_document,
        "source_span": knowledge_unit.source_span,
        "raw_payload": knowledge_unit.raw_payload,
    }
