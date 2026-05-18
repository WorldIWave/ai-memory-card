# Input: Session、card_id/deck_id、note/reason 等事件参数  |  Output: LearningEvent、活动列表与复习历史结果
# Output: 负责把报错、笔记、历史查询统一映射到 activity 视图模型
# Role: 这是学习事件时间线的核心服务层，连接 cards/review 路由与 learning_event/review_log 数据
# Use: 新活动类型先在 schemas/activity.py 定义，再在这里补 record/list 转换逻辑
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from app.db.models import Card, Deck, KnowledgeUnit, LearningEvent, ReviewLog
from app.schemas.activity import CardActivityItem, ReviewHistoryItem
from app.schemas.evaluation import EvaluationRead


class ActivityService:
    def record_report_error(
        self,
        session: Session,
        *,
        card_id: int,
        reason: str,
        note: str | None,
    ) -> LearningEvent:
        card = session.get(Card, card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")

        event = LearningEvent(
            card_id=card.id,
            deck_id=card.deck_id,
            event_type="report_error",
            payload_json={"reason": reason, "note": note or ""},
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event

    def record_note(
        self,
        session: Session,
        *,
        card_id: int,
        note: str,
        source: str | None = None,
    ) -> LearningEvent:
        card = session.get(Card, card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")

        event = LearningEvent(
            card_id=card.id,
            deck_id=card.deck_id,
            event_type="note",
            payload_json={"note": note, "source": source},
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event

    def record_evaluation(
        self,
        session: Session,
        *,
        card: Card,
        knowledge_unit: KnowledgeUnit | None,
        learner_explanation: str,
        result: EvaluationRead,
    ) -> LearningEvent:
        event = LearningEvent(
            card_id=card.id,
            deck_id=card.deck_id,
            event_type="evaluation",
            payload_json={
                "kind": "understanding_evaluation",
                "rubric_version": result.rubric_version,
                "card_id": card.id,
                "knowledge_unit_id": knowledge_unit.id if knowledge_unit is not None else None,
                "knowledge_unit_provider_id": knowledge_unit.provider_unit_id if knowledge_unit is not None else None,
                "learner_explanation": learner_explanation,
                "scores": {
                    "mastery": result.mastery_score,
                    "accuracy": result.accuracy_score,
                    "mechanism": result.mechanism_score,
                    "boundary": result.boundary_score,
                    "misconception": result.misconception_score,
                },
                "diagnosis": {
                    "misconception_detected": result.misconception_detected,
                    "confidence_score": result.confidence_score,
                    "uncertain": result.uncertain,
                    "feedback": result.feedback,
                    "weak_points": list(result.weak_points),
                    "reinforcement_advice": list(result.reinforcement_advice),
                },
                "provider_meta": dict(result.provider_meta),
                "evidence_snapshot": _evaluation_evidence_snapshot(result.provider_meta),
            },
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event

    def evaluation_signal_summary(
        self,
        session: Session,
        *,
        card_id: int | None = None,
        deck_id: int | None = None,
        limit: int = 50,
    ) -> dict[str, object]:
        query = (
            select(LearningEvent)
            .where(LearningEvent.event_type == "evaluation")
            .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
        )
        if card_id is not None:
            query = query.where(LearningEvent.card_id == card_id)
        if deck_id is not None:
            query = query.where(LearningEvent.deck_id == deck_id)
        events = session.exec(query.limit(max(limit, 0))).all()

        score_totals: dict[str, float] = {}
        score_counts: dict[str, int] = {}
        weak_point_counts: dict[str, int] = {}
        uncertain_count = 0
        latest_scores: dict[str, object] = {}
        latest_misconception_detected = False

        for index, event in enumerate(events):
            payload = event.payload_json or {}
            scores = payload.get("scores")
            diagnosis = payload.get("diagnosis")
            if not isinstance(scores, dict):
                scores = {}
            if not isinstance(diagnosis, dict):
                diagnosis = {}
            if index == 0:
                latest_scores = dict(scores)
                latest_misconception_detected = bool(diagnosis.get("misconception_detected"))
            if diagnosis.get("uncertain"):
                uncertain_count += 1
            weak_points = diagnosis.get("weak_points")
            if isinstance(weak_points, list):
                for item in weak_points:
                    weak_point = str(item).strip()
                    if weak_point:
                        weak_point_counts[weak_point] = weak_point_counts.get(weak_point, 0) + 1
            for key, value in scores.items():
                try:
                    score = float(value)
                except (TypeError, ValueError):
                    continue
                score_totals[str(key)] = score_totals.get(str(key), 0.0) + score
                score_counts[str(key)] = score_counts.get(str(key), 0) + 1

        average_scores = {
            key: round(score_totals[key] / score_counts[key], 2)
            for key in score_totals
            if score_counts.get(key)
        }
        return {
            "evaluation_count": len(events),
            "average_scores": average_scores,
            "latest_scores": latest_scores,
            "latest_misconception_detected": latest_misconception_detected,
            "weak_point_counts": weak_point_counts,
            "uncertain_count": uncertain_count,
        }

    def list_card_activity(self, session: Session, *, card_id: int) -> list[CardActivityItem]:
        card = session.get(Card, card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")

        activity_rows: list[tuple[datetime, int, CardActivityItem]] = []

        review_logs = session.exec(
            select(ReviewLog)
            .where(ReviewLog.card_id == card_id)
            .where(ReviewLog.is_undone == False)  # noqa: E712
            .order_by(ReviewLog.reviewed_at.desc(), ReviewLog.id.desc())
        ).all()
        for review_log in review_logs:
            activity_rows.append(
                (
                    review_log.reviewed_at,
                    review_log.id or 0,
                    self.review_log_to_activity_item(card, review_log),
                )
            )

        learning_events = session.exec(
            select(LearningEvent)
            .where(LearningEvent.card_id == card_id)
            .order_by(LearningEvent.created_at.desc(), LearningEvent.id.desc())
        ).all()
        for event in learning_events:
            activity_rows.append((event.created_at, event.id or 0, self.learning_event_to_activity_item(event)))

        activity_rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item for _created_at, _row_id, item in activity_rows]

    def list_review_history(
        self,
        session: Session,
        *,
        deck_id: int | None = None,
        card_id: int | None = None,
        limit: int = 50,
    ) -> list[ReviewHistoryItem]:
        if deck_id is not None and session.get(Deck, deck_id) is None:
            raise HTTPException(status_code=404, detail="Deck not found")
        if card_id is not None and session.get(Card, card_id) is None:
            raise HTTPException(status_code=404, detail="Card not found")

        query = (
            select(ReviewLog, Card, Deck)
            .join(Card, Card.id == ReviewLog.card_id)
            .join(Deck, Deck.id == Card.deck_id, isouter=True)
            .where(ReviewLog.trigger_type == "scheduled")
            .where(ReviewLog.is_undone == False)  # noqa: E712
            .order_by(ReviewLog.reviewed_at.desc(), ReviewLog.id.desc())
        )
        if deck_id is not None:
            query = query.where(Card.deck_id == deck_id)
        if card_id is not None:
            query = query.where(ReviewLog.card_id == card_id)

        rows = session.exec(query.limit(max(limit, 0))).all()
        items: list[ReviewHistoryItem] = []
        for review_log, card, deck in rows:
            items.append(
                ReviewHistoryItem(
                    id=review_log.id or 0,
                    card_id=card.id or 0,
                    deck_id=card.deck_id,
                    card_front=card.front,
                    deck_name=deck.name if deck is not None else None,
                    grade=review_log.grade,
                    interval_days=review_log.interval_days,
                    reviewed_at=review_log.reviewed_at,
                    session_id=review_log.session_id,
                )
            )
        return items

    def learning_event_to_activity_item(self, event: LearningEvent) -> CardActivityItem:
        return CardActivityItem(
            id=f"learning_event:{event.id}",
            event_type=event.event_type,
            created_at=event.created_at,
            summary=self._learning_event_summary(event),
            payload=dict(event.payload_json or {}),
        )

    def review_log_to_activity_item(self, card: Card, review_log: ReviewLog) -> CardActivityItem:
        return CardActivityItem(
            id=f"review_log:{review_log.id}",
            event_type="review",
            created_at=review_log.reviewed_at,
            summary=self._review_summary(review_log),
            payload={
                "card_id": card.id,
                "card_front": card.front,
                "grade": review_log.grade,
                "interval_days": review_log.interval_days,
                "reviewed_at": review_log.reviewed_at.isoformat(),
                "session_id": review_log.session_id,
                "trigger_type": review_log.trigger_type,
                "note": review_log.note or "",
            },
        )

    def _learning_event_summary(self, event: LearningEvent) -> str:
        payload = event.payload_json or {}
        if event.event_type == "report_error":
            reason = str(payload.get("reason") or "").strip()
            return f"Reported issue: {reason}" if reason else "Reported issue"
        if event.event_type == "note":
            return "Note added"
        if event.event_type == "evaluation":
            return "Evaluation recorded"
        return event.event_type.replace("_", " ").title()

    def _review_summary(self, review_log: ReviewLog) -> str:
        if review_log.interval_days is None:
            return f"Review: {review_log.grade}"
        return f"Review: {review_log.grade} ({review_log.interval_days:g} days)"


def _evaluation_evidence_snapshot(provider_meta: dict[str, object]) -> dict[str, object]:
    context_debug = provider_meta.get("context_debug")
    if not isinstance(context_debug, dict):
        return {}
    keys = {
        "evidence_strategy",
        "rag_context_present",
        "retrieved_context_count",
        "question_plan_count",
        "support_linked_member_count",
        "relation_linked_member_count",
        "related_evidence_count",
        "related_provider_unit_ids",
    }
    return {key: context_debug[key] for key in keys if key in context_debug}
