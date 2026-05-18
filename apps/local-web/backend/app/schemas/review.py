# Input: 复习评分、调度上下文、session 状态和 ORM card 数据  |  Output: 调度决策、session 响应与 undo 回包 DTO
# Output: 同时承载 legacy submit 与 session v3 两套复习链路共享的数据模型
# Role: 这是 scheduler、review service、review routes 之间最关键的契约文件
# Use: 改 grade/session 语义时优先改这里，再同步 scheduler 实现、前端 review API 与测试
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.card import CardRead


class ReviewOutcome(BaseModel):
    grade: Literal["again", "hard", "good", "easy"]
    response_time_ms: int | None = None
    self_report_confidence: float | None = None
    ai_mastery_score: float | None = None
    ai_dimension_scores: dict[str, float] | None = None
    lapse: bool


class ReviewContext(BaseModel):
    now: datetime
    today_load: int
    pending_count: int
    deck_policy: dict[str, int | float | str]
    review_mode: str
    is_new_card: bool
    recent_fail_count: int
    related_weakness_tags: list[str] = Field(default_factory=list)


class DuePreview(BaseModel):
    card_id: int
    is_due: bool
    due_in_days: float
    next_due_at: datetime | None
    bucket: str


class ScheduleDecision(BaseModel):
    card_id: int
    scheduler_type: str
    next_due_at: datetime
    interval_days: float
    reason: str
    state_patch: dict[str, int | float | str | None | dict]
    explainability: dict[str, str | float | int]


GradeValue = Literal["again", "hard", "good", "easy"]
SessionScope = Literal["deck", "all"]
SessionAction = Literal["remove", "reinsert", "repeat_now"]


class ReviewSessionContext(BaseModel):
    now: datetime
    session_id: str
    session_date: date
    scope: SessionScope
    deck_id: int | None = None
    remaining_card_ids: list[int] = Field(default_factory=list)


class SessionScheduleResult(BaseModel):
    card_id: int
    scheduler_type: str
    next_due_at: datetime
    interval_days: float
    reason: str
    session_action: SessionAction
    reinsert_after: int | None = None
    learning_state: str
    learning_step: int
    session_repeats_today: int
    hard_attempts_today: int
    repetition_delta: int = 0
    lapses_delta: int = 0
    state_patch: dict[str, int | float | str | None | dict] = Field(default_factory=dict)
    explainability: dict[str, str | float | int] = Field(default_factory=dict)


class ReviewSessionCounts(BaseModel):
    new: int = 0
    learning: int = 0
    review: int = 0
    relearning: int = 0
    total: int = 0


class ReviewSessionRead(BaseModel):
    session_id: str
    scope: SessionScope
    deck_id: int | None = None
    queue: list[CardRead]
    counts: ReviewSessionCounts
    can_undo: bool


class ReviewSessionSubmitRequest(BaseModel):
    card_id: int
    grade: GradeValue
    review_mode: str = "flip_card"
    trigger_type: str = "scheduled"
    note: str | None = None


class ReviewSessionSubmitResponse(ReviewSessionRead):
    decision: SessionScheduleResult


class ReviewSessionUndoResponse(ReviewSessionRead):
    restored_card_id: int | None = None
