# Input: 当前复习状态、评分结果与 session 上下文  |  Output: 间隔调度决策与同日 again/hard/good/easy 动作
# Output: 提供默认 BasicSchedulerProvider 和 BasicSessionScheduler 两套具体调度实现
# Role: 这是当前产品默认的非 AI 调度算法实现，覆盖长期间隔与当日重排两层逻辑
# Use: 改公式或重排规则时优先改这里，并同步 review service 测试与文档说明
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.models import Card, CardReviewState
from app.schemas.review import (
    DuePreview,
    ReviewContext,
    ReviewOutcome,
    ReviewSessionContext,
    ScheduleDecision,
    SessionAction,
    SessionScheduleResult,
)


class BasicSchedulerProvider:
    def get_name(self) -> str:
        return "sm2_basic"

    def initialize_state(self, card: Card) -> CardReviewState:
        if card.id is None:
            raise ValueError("initialize_state requires card.id to be set")
        return CardReviewState(card_id=card.id, scheduler_type=self.get_name())

    def plan_next(
        self,
        state: CardReviewState,
        outcome: ReviewOutcome,
        context: ReviewContext,
    ) -> ScheduleDecision:
        grade_map = {"again": 0.5, "hard": 1.2, "good": 2.0, "easy": 3.0}
        multiplier = grade_map[outcome.grade]
        base_interval = max(state.interval_days, 1.0)
        next_interval = 1.0 if outcome.grade == "again" else round(base_interval * multiplier, 2)
        next_due_at = context.now + timedelta(days=next_interval)

        return ScheduleDecision(
            card_id=state.card_id,
            scheduler_type=self.get_name(),
            next_due_at=next_due_at,
            interval_days=next_interval,
            reason=f"basic rule applied for grade={outcome.grade}",
            state_patch={
                "interval_days": next_interval,
                "repetition_count": state.repetition_count + (0 if outcome.grade == "again" else 1),
                "lapses": state.lapses + (1 if outcome.grade == "again" else 0),
                "last_reviewed_at": context.now.isoformat(),
                "next_due_at": next_due_at.isoformat(),
            },
            explainability={
                "multiplier": multiplier,
                "starting_interval": base_interval,
            },
        )

    def preview_due(self, states: list[CardReviewState], now: datetime) -> list[DuePreview]:
        previews: list[DuePreview] = []

        for state in states:
            if state.next_due_at is None:
                previews.append(
                    DuePreview(
                        card_id=state.card_id,
                        is_due=True,
                        due_in_days=0.0,
                        next_due_at=None,
                        bucket="due_today",
                    )
                )
                continue

            due_delta = state.next_due_at - now
            due_in_days = round(due_delta.total_seconds() / 86400, 2)
            if due_in_days < 0:
                bucket = "overdue"
            elif due_in_days == 0:
                bucket = "due_today"
            elif due_in_days <= 3:
                bucket = "due_soon"
            else:
                bucket = "future"

            previews.append(
                DuePreview(
                    card_id=state.card_id,
                    is_due=state.next_due_at <= now,
                    due_in_days=due_in_days,
                    next_due_at=state.next_due_at,
                    bucket=bucket,
                )
            )

        return previews


class BasicSessionScheduler(BasicSchedulerProvider):
    def get_name(self) -> str:
        return "sm2_basic_v3"

    def initialize_state(self, card: Card) -> CardReviewState:
        state = super().initialize_state(card)
        state.scheduler_type = self.get_name()
        state.learning_state = "new"
        state.learning_step = 0
        return state

    def build_session_queue(
        self,
        rows: list[tuple[Card, CardReviewState]],
        context: ReviewSessionContext,
    ) -> list[Card]:
        def to_utc(value: datetime) -> datetime:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)

        now = to_utc(context.now)

        def due_key(row: tuple[Card, CardReviewState]) -> tuple[int, datetime, int]:
            card, state = row
            if state.session_due_at is not None:
                return (0, to_utc(state.session_due_at), card.id or 0)
            if state.next_due_at is None:
                return (1, datetime.min.replace(tzinfo=timezone.utc), card.id or 0)
            next_due_at = to_utc(state.next_due_at)
            if next_due_at <= now:
                return (2, next_due_at, card.id or 0)
            return (3, next_due_at, card.id or 0)

        return [card for card, _state in sorted(rows, key=due_key)]

    def apply_grade(
        self,
        state: CardReviewState,
        grade: str,
        context: ReviewSessionContext,
    ) -> SessionScheduleResult:
        if grade not in {"again", "hard", "good", "easy"}:
            raise ValueError(f"Unsupported review grade: {grade}")

        base_interval = max(state.interval_days, 1.0)
        learning_state = state.learning_state or "new"
        learning_step = state.learning_step
        hard_attempts = state.hard_attempts_today
        session_repeats = state.session_repeats_today + 1
        repetition_delta = 0
        lapses_delta = 0
        session_action: SessionAction = "remove"
        reinsert_after: int | None = None
        reason = f"session v3 grade={grade}"

        if grade == "again":
            interval_days = 1.0
            learning_state = "relearning" if learning_state == "review" else "learning"
            lapses_delta = 1 if state.repetition_count > 0 else 0
            if len(context.remaining_card_ids) >= 3:
                session_action = "reinsert"
                reinsert_after = 3
            elif len(context.remaining_card_ids) > 0:
                session_action = "reinsert"
                reinsert_after = len(context.remaining_card_ids)
            else:
                session_action = "repeat_now"
                reinsert_after = 0
        elif grade == "hard":
            hard_attempts += 1
            interval_days = 1.0 if base_interval <= 1 else round(base_interval * 1.2, 2)
            if hard_attempts < 3:
                session_action = "reinsert"
                reinsert_after = len(context.remaining_card_ids)
            else:
                session_action = "remove"
        elif grade == "good":
            interval_days = round(base_interval * 2.0, 2)
            if learning_state in {"new", "learning"} and learning_step < 1:
                learning_state = "learning"
                learning_step = 1
                session_action = "reinsert"
                reinsert_after = len(context.remaining_card_ids)
            else:
                learning_state = "review"
                repetition_delta = 1
                session_action = "remove"
        else:
            interval_days = round(base_interval * 3.0, 2)
            learning_state = "review"
            repetition_delta = 1
            session_action = "remove"

        next_due_at = context.now + timedelta(days=interval_days)
        return SessionScheduleResult(
            card_id=state.card_id,
            scheduler_type=self.get_name(),
            next_due_at=next_due_at,
            interval_days=interval_days,
            reason=reason,
            session_action=session_action,
            reinsert_after=reinsert_after,
            learning_state=learning_state,
            learning_step=learning_step,
            session_repeats_today=session_repeats,
            hard_attempts_today=hard_attempts,
            repetition_delta=repetition_delta,
            lapses_delta=lapses_delta,
            state_patch={
                "learning_state": learning_state,
                "learning_step": learning_step,
                "session_repeats_today": session_repeats,
                "hard_attempts_today": hard_attempts,
                "interval_days": interval_days,
                "next_due_at": next_due_at.isoformat(),
            },
            explainability={
                "remaining_cards": len(context.remaining_card_ids),
                "hard_attempts_today": hard_attempts,
            },
        )

    def restore_state(self, snapshot: dict) -> CardReviewState:
        return CardReviewState(**snapshot)
