# Input: Session、评分动作、session_id/deck_id 等复习上下文  |  Output: legacy 决策、ReviewSessionRead、提交/撤销结果
# Output: 统一封装旧 submit 与 session v3 的建队列、同日重排、跨天间隔调度和 undo
# Role: 这是核心学习闭环的业务主脑，连接 review routes、study settings 与 scheduler providers
# Use: 新逻辑优先加在 session v3 路径；保持 scheduler 纯算法、service 负责持久化和一致性
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.db.models import Card, CardReviewState, Deck, ReviewLog, ReviewSession
from app.providers.scheduler.base import SchedulerProvider, SessionSchedulerProvider
from app.providers.scheduler.basic import BasicSchedulerProvider, BasicSessionScheduler
from app.schemas.review import (
    ReviewContext,
    ReviewOutcome,
    ReviewSessionContext,
    ReviewSessionCounts,
    ReviewSessionRead,
    ReviewSessionSubmitResponse,
    ReviewSessionUndoResponse,
    ScheduleDecision,
    SessionScheduleResult,
)
from app.services.ai_scheduler_decision_service import AISchedulerDecisionService
from app.services.ai_plugin_host_service import AIPluginHostService
from app.services.study_settings_service import StudySettingsService


class ReviewService:
    def __init__(
        self,
        scheduler: SchedulerProvider | None = None,
        session_scheduler: SessionSchedulerProvider | None = None,
        study_settings_service: StudySettingsService | None = None,
        ai_plugin_host_service: AIPluginHostService | None = None,
        ai_scheduler_decision_service: AISchedulerDecisionService | None = None,
    ) -> None:
        self.scheduler = scheduler or BasicSchedulerProvider()
        self.session_scheduler: SessionSchedulerProvider = (
            session_scheduler or BasicSessionScheduler()
        )
        self.study_settings_service = study_settings_service or StudySettingsService()
        self.ai_plugin_host_service = ai_plugin_host_service or AIPluginHostService.from_settings()
        self.ai_scheduler_decision_service = ai_scheduler_decision_service or AISchedulerDecisionService(
            study_settings_service=self.study_settings_service,
            ai_plugin_host_service=self.ai_plugin_host_service,
        )

    def list_queue(self, session: Session) -> list[Card]:
        # SQL JOIN: only active cards with their review state, sorted at DB level
        statement = (
            select(Card, CardReviewState)
            .join(CardReviewState, CardReviewState.card_id == Card.id)
            .where(Card.status == "active")
            .order_by(CardReviewState.next_due_at.asc().nullsfirst())
        )
        rows = session.exec(statement).all()

        now = datetime.now(timezone.utc)

        def to_utc(value: datetime) -> datetime:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)

        def sort_key(row: tuple) -> tuple[int, datetime]:
            state = row[1]
            next_due_at = state.next_due_at if state is not None else None
            if next_due_at is None:
                return (0, datetime.min.replace(tzinfo=timezone.utc))
            due_at = to_utc(next_due_at)
            return (0, due_at) if due_at <= now else (1, due_at)

        rows_sorted = sorted(rows, key=sort_key)
        return [card for card, _ in rows_sorted]

    def submit(
        self,
        session: Session,
        *,
        card_id: int,
        grade: str,
        review_mode: str,
        trigger_type: str,
        note: str | None = None,
    ) -> ScheduleDecision:
        state = session.get(CardReviewState, card_id)
        if state is None:
            raise ValueError(f"Card review state not found for card_id={card_id}")

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        today_load = session.exec(
            select(func.count(CardReviewState.card_id)).where(
                CardReviewState.last_reviewed_at >= today_start
            )
        ).one()

        pending_count = session.exec(
            select(func.count(CardReviewState.card_id))
            .join(Card, Card.id == CardReviewState.card_id)
            .where(Card.status == "active")
            .where(
                (CardReviewState.next_due_at.is_(None)) |
                (CardReviewState.next_due_at <= now)
            )
        ).one()

        is_new_card = state.repetition_count == 0

        outcome = ReviewOutcome(grade=grade, lapse=grade == "again")
        context = ReviewContext(
            now=now,
            today_load=today_load,
            pending_count=pending_count,
            deck_policy={"daily_limit": 30},
            review_mode=review_mode,
            is_new_card=is_new_card,
            recent_fail_count=0,
            related_weakness_tags=[],
        )
        decision = self.scheduler.plan_next(state, outcome, context)

        state.scheduler_type = decision.scheduler_type
        state.interval_days = decision.interval_days
        state.next_due_at = decision.next_due_at
        state.repetition_count += 0 if grade == "again" else 1
        state.lapses += 1 if grade == "again" else 0
        state.last_reviewed_at = now

        session.add(state)
        log = ReviewLog(
            card_id=card_id,
            grade=grade,
            interval_days=decision.interval_days,
            ease_factor=state.ease_factor,
            reviewed_at=now,
            note=note,
        )
        session.add(log)
        session.commit()
        session.refresh(state)
        return decision

    def get_session(
        self,
        db: Session,
        *,
        scope: str = "deck",
        deck_id: int | None = None,
    ) -> ReviewSessionRead:
        review_session = self._ensure_session(db, scope=scope, deck_id=deck_id)
        return self._response(db, review_session)

    def submit_session(
        self,
        db: Session,
        *,
        session_id: str,
        card_id: int,
        grade: str,
        review_mode: str,
        trigger_type: str,
        note: str | None = None,
    ) -> ReviewSessionSubmitResponse:
        review_session = db.get(ReviewSession, session_id)
        if review_session is None:
            raise HTTPException(status_code=404, detail="Review session not found")
        self._require_current_session(review_session)
        self._validate_session_submit_inputs(grade=grade, trigger_type=trigger_type)

        card = db.get(Card, card_id)
        state = db.get(CardReviewState, card_id)
        if card is None or state is None or not self._card_in_session(card, review_session):
            raise HTTPException(status_code=404, detail="Card not found in review session")

        now = datetime.now(timezone.utc)
        validation_rows = self._session_rows(db, review_session, now=now, reset_daily_state=False)
        if card_id not in {queued_card.id for queued_card, _queued_state in validation_rows}:
            raise HTTPException(
                status_code=400,
                detail="Card is not in the current review session",
            )

        current_rows = self._session_rows(db, review_session, now=now)
        if card_id not in {queued_card.id for queued_card, _queued_state in current_rows}:
            raise HTTPException(
                status_code=400,
                detail="Card is not in the current review session",
            )
        context = self._context(
            review_session,
            now=now,
            remaining_card_ids=[
                queued_card.id
                for queued_card, _queued_state in current_rows
                if queued_card.id is not None and queued_card.id != card_id
            ],
        )
        before = self._state_snapshot(state)
        before["_session_order_snapshot"] = self._session_order_snapshot(current_rows)
        decision = self._plan_session_decision(db, card=card, state=state, grade=grade, context=context)
        self._apply_decision(state, decision, context)
        self._apply_session_order(db, review_session, current_rows, card_id, decision)
        after = self._state_snapshot(state)
        after["_session_order_snapshot"] = self._session_order_snapshot(current_rows)

        db.add(state)
        review_session.updated_at = now
        db.add(review_session)
        db.add(
            ReviewLog(
                card_id=card_id,
                grade=grade,
                interval_days=decision.interval_days,
                ease_factor=state.ease_factor,
                reviewed_at=now,
                note=note,
                session_id=review_session.id,
                trigger_type=trigger_type,
                state_before=before,
                state_after=after,
            )
        )
        db.commit()
        return self._response(db, review_session, decision=decision)

    def undo_session(self, db: Session, *, session_id: str) -> ReviewSessionUndoResponse:
        review_session = db.get(ReviewSession, session_id)
        if review_session is None:
            raise HTTPException(status_code=404, detail="Review session not found")
        self._require_current_session(review_session)

        log = db.exec(
            select(ReviewLog)
            .where(ReviewLog.session_id == session_id)
            .where(ReviewLog.trigger_type == "scheduled")
            .where(ReviewLog.is_undone == False)  # noqa: E712
            .order_by(ReviewLog.reviewed_at.desc(), ReviewLog.id.desc())
        ).first()
        if log is None:
            return self._response(db, review_session, restored_card_id=None, undo=True)

        state = db.get(CardReviewState, log.card_id)
        if state is None:
            state = CardReviewState(card_id=log.card_id)
        if log.state_before is not None:
            self._restore_session_order_snapshot(db, log.state_before)
            self._apply_snapshot(state, log.state_before)
            db.add(state)

        now = datetime.now(timezone.utc)
        log.is_undone = True
        log.undone_at = now
        review_session.updated_at = now
        db.add(log)
        db.add(review_session)
        db.commit()
        return self._response(db, review_session, restored_card_id=log.card_id, undo=True)

    def _today(self, now: datetime | None = None) -> date:
        return self._to_utc(now or datetime.now(timezone.utc)).date()

    def _session_id(self, *, scope: str, deck_id: int | None, session_date: date) -> str:
        if scope == "all":
            return f"{session_date.isoformat()}:all"
        return f"{session_date.isoformat()}:deck:{deck_id}"

    def _ensure_session(self, db: Session, *, scope: str, deck_id: int | None) -> ReviewSession:
        if scope not in {"deck", "all"}:
            raise HTTPException(status_code=400, detail="Unsupported review session scope")
        if scope == "deck":
            if deck_id is None:
                raise HTTPException(status_code=400, detail="deck_id is required for deck sessions")
            deck = db.get(Deck, deck_id)
            if deck is None or deck.deleted_at is not None:
                raise HTTPException(status_code=404, detail="Deck not found")
        else:
            deck_id = None

        session_date = self._today()
        session_id = self._session_id(scope=scope, deck_id=deck_id, session_date=session_date)
        review_session = db.get(ReviewSession, session_id)
        if review_session is not None:
            return review_session

        now = datetime.now(timezone.utc)
        review_session = ReviewSession(
            id=session_id,
            session_date=session_date,
            scope=scope,
            deck_id=deck_id,
            created_at=now,
            updated_at=now,
        )
        db.add(review_session)
        db.commit()
        db.refresh(review_session)
        return review_session

    def _require_current_session(self, review_session: ReviewSession) -> None:
        today = self._today()
        expected_id = self._session_id(
            scope=review_session.scope,
            deck_id=review_session.deck_id,
            session_date=today,
        )
        if (
            review_session.status != "active"
            or review_session.session_date != today
            or review_session.id != expected_id
        ):
            raise HTTPException(status_code=409, detail="Review session is not current")

    def _validate_session_submit_inputs(self, *, grade: str, trigger_type: str) -> None:
        if grade not in {"again", "hard", "good", "easy"}:
            raise HTTPException(status_code=400, detail="Unsupported review grade")
        if trigger_type != "scheduled":
            raise HTTPException(status_code=400, detail="Session submit only supports scheduled reviews")

    def _reset_daily_state_if_needed(self, state: CardReviewState, today: date) -> bool:
        if not self._needs_daily_reset(state, today):
            return False

        state.session_due_at = None
        state.session_repeats_today = 0
        state.hard_attempts_today = 0
        state.last_session_date = today
        return True

    def _needs_daily_reset(self, state: CardReviewState, today: date) -> bool:
        session_due_day = (
            self._to_utc(state.session_due_at).date()
            if state.session_due_at is not None
            else None
        )
        return (
            (state.last_session_date is not None and state.last_session_date != today)
            or (session_due_day is not None and session_due_day != today)
        )

    def _state_snapshot(self, state: CardReviewState) -> dict[str, Any]:
        return {
            "card_id": state.card_id,
            "scheduler_type": state.scheduler_type,
            "state_version": state.state_version,
            "interval_days": state.interval_days,
            "ease_factor": state.ease_factor,
            "repetition_count": state.repetition_count,
            "lapses": state.lapses,
            "last_reviewed_at": self._serialize_temporal(state.last_reviewed_at),
            "next_due_at": self._serialize_temporal(state.next_due_at),
            "stability_score": state.stability_score,
            "difficulty_score": state.difficulty_score,
            "scheduler_state_blob": deepcopy(state.scheduler_state_blob or {}),
            "last_scheduler_decision_id": state.last_scheduler_decision_id,
            "learning_state": state.learning_state,
            "learning_step": state.learning_step,
            "session_due_at": self._serialize_temporal(state.session_due_at),
            "session_repeats_today": state.session_repeats_today,
            "hard_attempts_today": state.hard_attempts_today,
            "last_session_date": self._serialize_temporal(state.last_session_date),
        }

    def _apply_snapshot(self, state: CardReviewState, snapshot: dict[str, Any]) -> None:
        for key, value in snapshot.items():
            if key.startswith("_"):
                continue
            if key in {"last_reviewed_at", "next_due_at", "session_due_at"}:
                value = self._parse_datetime(value)
            elif key == "last_session_date":
                value = self._parse_date(value)
            setattr(state, key, value)

    def _session_rows(
        self,
        db: Session,
        review_session: ReviewSession,
        *,
        now: datetime | None = None,
        reset_daily_state: bool = True,
    ) -> list[tuple[Card, CardReviewState]]:
        current_time = self._to_utc(now or datetime.now(timezone.utc))
        statement = (
            select(Card, CardReviewState)
            .join(CardReviewState, CardReviewState.card_id == Card.id)
            .where(Card.status == "active")
            .where(Card.deleted_at.is_(None))
            .order_by(Card.id.asc())
        )
        if review_session.scope == "deck":
            statement = statement.where(Card.deck_id == review_session.deck_id)

        raw_rows = list(db.exec(statement).all())
        rows: list[tuple[Card, CardReviewState, bool]] = []
        changed = False
        today = self._today(current_time)

        for card, state in raw_rows:
            was_in_today_loop = (
                state.session_due_at is not None
                and self._to_utc(state.session_due_at).date() == today
            )
            row_state = state
            if self._needs_daily_reset(state, today):
                if reset_daily_state:
                    self._reset_daily_state_if_needed(state, today)
                    self._clear_session_order(state, review_session)
                    db.add(state)
                    changed = True
                else:
                    row_state = self._state_copy_for_read(state)
                    self._reset_daily_state_if_needed(row_state, today)
                    self._clear_session_order(row_state, review_session)
            rows.append((card, row_state, was_in_today_loop))

        if changed:
            db.commit()

        filtered = [
            (card, state, was_in_today_loop)
            for card, state, was_in_today_loop in rows
            if state.session_due_at is not None
            or state.next_due_at is None
            or self._to_utc(state.next_due_at) <= current_time
        ]
        settings = self.study_settings_service.get(db)
        filtered = self._apply_daily_admission_limits(
            filtered,
            daily_review_limit=settings.daily_review_limit,
            daily_new_limit=settings.daily_new_limit,
        )
        context = self._context(review_session, now=current_time)
        sorted_cards = self.session_scheduler.build_session_queue(filtered, context)
        rows_by_id = {card.id: (card, state) for card, state in filtered}
        sorted_rows = [
            rows_by_id[card.id]
            for card in sorted_cards
            if card.id is not None and card.id in rows_by_id
        ]
        return self._apply_persisted_reinsert_order(sorted_rows, review_session)

    def _apply_daily_admission_limits(
        self,
        rows: list[tuple[Card, CardReviewState, bool]],
        *,
        daily_review_limit: int,
        daily_new_limit: int,
    ) -> list[tuple[Card, CardReviewState]]:
        admitted_rows: list[tuple[Card, CardReviewState]] = []
        remaining_review_slots = max(
            daily_review_limit
            - sum(
                1
                for _card, state, was_in_today_loop in rows
                if state.repetition_count > 0 and was_in_today_loop
            ),
            0,
        )
        remaining_new_slots = max(
            daily_new_limit
            - sum(
                1
                for _card, state, was_in_today_loop in rows
                if state.repetition_count == 0 and was_in_today_loop
            ),
            0,
        )
        for card, state, was_in_today_loop in rows:
            already_in_today_loop = was_in_today_loop
            is_new_card = state.repetition_count == 0
            if already_in_today_loop:
                admitted_rows.append((card, state))
                continue
            if is_new_card:
                if remaining_new_slots <= 0:
                    continue
                remaining_new_slots -= 1
                admitted_rows.append((card, state))
                continue
            if remaining_review_slots <= 0:
                continue
            remaining_review_slots -= 1
            admitted_rows.append((card, state))
        return admitted_rows

    def _context(
        self,
        review_session: ReviewSession,
        *,
        now: datetime,
        remaining_card_ids: list[int] | None = None,
    ) -> ReviewSessionContext:
        return ReviewSessionContext(
            now=self._to_utc(now),
            session_id=review_session.id,
            session_date=review_session.session_date,
            scope=review_session.scope,
            deck_id=review_session.deck_id,
            remaining_card_ids=remaining_card_ids or [],
        )

    def _response(
        self,
        db: Session,
        review_session: ReviewSession,
        *,
        decision: SessionScheduleResult | None = None,
        restored_card_id: int | None = None,
        undo: bool = False,
    ) -> ReviewSessionRead | ReviewSessionSubmitResponse | ReviewSessionUndoResponse:
        db.refresh(review_session)
        rows = self._session_rows(db, review_session)
        queue = [card for card, _state in rows]
        counts = self._counts(rows)
        payload = {
            "session_id": review_session.id,
            "scope": review_session.scope,
            "deck_id": review_session.deck_id,
            "queue": queue,
            "counts": counts,
            "can_undo": self._can_undo(db, review_session.id),
        }
        if decision is not None:
            return ReviewSessionSubmitResponse(**payload, decision=decision)
        if undo:
            return ReviewSessionUndoResponse(**payload, restored_card_id=restored_card_id)
        return ReviewSessionRead(**payload)

    def _apply_decision(
        self,
        state: CardReviewState,
        decision: SessionScheduleResult,
        context: ReviewSessionContext,
    ) -> None:
        state.scheduler_type = decision.scheduler_type
        state.interval_days = decision.interval_days
        state.next_due_at = decision.next_due_at
        state.last_reviewed_at = context.now
        state.learning_state = decision.learning_state
        state.learning_step = decision.learning_step
        state.session_repeats_today = decision.session_repeats_today
        state.hard_attempts_today = decision.hard_attempts_today
        state.repetition_count += decision.repetition_delta
        state.lapses += decision.lapses_delta
        state.last_session_date = context.session_date

        if decision.session_action == "remove":
            state.session_due_at = None
        else:
            state.session_due_at = context.now

        scheduler_meta = decision.state_patch.get("scheduler_meta")
        if isinstance(scheduler_meta, dict):
            blob = dict(state.scheduler_state_blob or {})
            blob["last_scheduler_meta"] = scheduler_meta
            state.scheduler_state_blob = blob

    def _plan_session_decision(
        self,
        db: Session,
        *,
        card: Card,
        state: CardReviewState,
        grade: str,
        context: ReviewSessionContext,
    ) -> SessionScheduleResult:
        baseline = self.session_scheduler.apply_grade(state, grade, context)
        return self.ai_scheduler_decision_service.plan(
            db,
            card=card,
            state=state,
            grade=grade,
            context=context,
            baseline_decision=baseline,
        )

    def _apply_session_order(
        self,
        db: Session,
        review_session: ReviewSession,
        current_rows: list[tuple[Card, CardReviewState]],
        card_id: int,
        decision: SessionScheduleResult,
    ) -> None:
        row_by_id = {
            card.id: (card, row_state)
            for card, row_state in current_rows
            if card.id is not None
        }
        submitted_row = row_by_id.get(card_id)
        if submitted_row is None:
            raise ValueError("Submitted card is not in current session rows")
        _submitted_card, submitted_state = submitted_row
        remaining_ids = [queued_id for queued_id in row_by_id if queued_id != card_id]

        if decision.session_action == "remove":
            ordered_ids = remaining_ids
        else:
            insert_at = min(decision.reinsert_after or 0, len(remaining_ids))
            ordered_ids = remaining_ids[:insert_at] + [card_id] + remaining_ids[insert_at:]

        order_by_id = {queued_id: index for index, queued_id in enumerate(ordered_ids)}
        for queued_id, (_card, row_state) in row_by_id.items():
            if queued_id in order_by_id:
                self._set_session_order(row_state, review_session, order_by_id[queued_id])
            else:
                self._clear_session_order(row_state, review_session)
            db.add(row_state)

    def _state_copy_for_read(self, state: CardReviewState) -> CardReviewState:
        state_copy = CardReviewState(card_id=state.card_id)
        self._apply_snapshot(state_copy, self._state_snapshot(state))
        return state_copy

    def _session_order_snapshot(
        self,
        rows: list[tuple[Card, CardReviewState]],
    ) -> dict[str, dict[str, Any]]:
        return {
            str(card.id): deepcopy(state.scheduler_state_blob or {})
            for card, state in rows
            if card.id is not None
        }

    def _restore_session_order_snapshot(self, db: Session, snapshot: dict[str, Any]) -> None:
        order_snapshot = snapshot.get("_session_order_snapshot")
        if not isinstance(order_snapshot, dict):
            return

        for raw_card_id, scheduler_state_blob in order_snapshot.items():
            state = db.get(CardReviewState, int(raw_card_id))
            if state is None:
                continue
            state.scheduler_state_blob = deepcopy(scheduler_state_blob or {})
            db.add(state)

    def _counts(self, rows: list[tuple[Card, CardReviewState]]) -> ReviewSessionCounts:
        counts = ReviewSessionCounts(total=len(rows))
        for _card, state in rows:
            bucket = state.learning_state or "new"
            if bucket not in {"new", "learning", "review", "relearning"}:
                bucket = "review"
            setattr(counts, bucket, getattr(counts, bucket) + 1)
        return counts

    def _can_undo(self, db: Session, session_id: str) -> bool:
        return (
            db.exec(
                select(ReviewLog.id)
                .where(ReviewLog.session_id == session_id)
                .where(ReviewLog.trigger_type == "scheduled")
                .where(ReviewLog.is_undone == False)  # noqa: E712
            ).first()
            is not None
        )

    def _card_in_session(self, card: Card, review_session: ReviewSession) -> bool:
        if card.status != "active" or card.deleted_at is not None:
            return False
        return review_session.scope == "all" or card.deck_id == review_session.deck_id

    def _apply_persisted_reinsert_order(
        self,
        rows: list[tuple[Card, CardReviewState]],
        review_session: ReviewSession,
    ) -> list[tuple[Card, CardReviewState]]:
        base_rows: list[tuple[Card, CardReviewState]] = []
        reinsert_rows: list[tuple[int, tuple[Card, CardReviewState]]] = []
        for row in rows:
            _card, state = row
            order = self._session_order(state, review_session)
            if order is None:
                base_rows.append(row)
            else:
                reinsert_rows.append((order, row))

        for order, row in sorted(reinsert_rows, key=lambda item: item[0]):
            insert_at = min(order, len(base_rows))
            base_rows.insert(insert_at, row)
        return base_rows

    def _session_order(self, state: CardReviewState, review_session: ReviewSession) -> int | None:
        order_map = (state.scheduler_state_blob or {}).get("session_order", {})
        value = order_map.get(review_session.id) if isinstance(order_map, dict) else None
        return int(value) if value is not None else None

    def _set_session_order(
        self,
        state: CardReviewState,
        review_session: ReviewSession,
        order: int,
    ) -> None:
        blob = dict(state.scheduler_state_blob or {})
        order_map = dict(blob.get("session_order", {}))
        order_map[review_session.id] = order
        blob["session_order"] = order_map
        state.scheduler_state_blob = blob

    def _clear_session_order(self, state: CardReviewState, review_session: ReviewSession) -> None:
        blob = dict(state.scheduler_state_blob or {})
        order_map = dict(blob.get("session_order", {}))
        order_map.pop(review_session.id, None)
        if order_map:
            blob["session_order"] = order_map
        else:
            blob.pop("session_order", None)
        state.scheduler_state_blob = blob

    def _to_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _serialize_temporal(self, value: datetime | date | None) -> str | None:
        return value.isoformat() if value is not None else None

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)

    def _parse_date(self, value: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value
        return date.fromisoformat(value)
