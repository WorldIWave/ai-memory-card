# Input: CardReviewState、ReviewOutcome、ReviewContext / ReviewSessionContext  |  Output: 调度决策与同日 session 结果协议
# Output: 定义 scheduler provider 需要实现的 plan_next、preview_due、session 调度接口
# Role: 这是 review service 与具体调度算法之间的抽象边界，方便后续替换为 AI/其他算法
# Use: 新调度器先实现这里的协议；尽量别在 service 中依赖具体实现细节
from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.db.models import Card, CardReviewState
from app.schemas.review import (
    DuePreview,
    ReviewContext,
    ReviewOutcome,
    ReviewSessionContext,
    ScheduleDecision,
    SessionScheduleResult,
)


@runtime_checkable
class SchedulerProvider(Protocol):
    def get_name(self) -> str:
        ...

    def initialize_state(self, card: Card) -> CardReviewState:
        ...

    def plan_next(
        self,
        state: CardReviewState,
        outcome: ReviewOutcome,
        context: ReviewContext,
    ) -> ScheduleDecision:
        ...

    def preview_due(self, states: list[CardReviewState], now: datetime) -> list[DuePreview]:
        ...


@runtime_checkable
class SessionSchedulerProvider(SchedulerProvider, Protocol):
    def build_session_queue(
        self,
        rows: list[tuple[Card, CardReviewState]],
        context: ReviewSessionContext,
    ) -> list[Card]:
        ...

    def apply_grade(
        self,
        state: CardReviewState,
        grade: str,
        context: ReviewSessionContext,
    ) -> SessionScheduleResult:
        ...

    def restore_state(self, snapshot: dict) -> CardReviewState:
        ...
