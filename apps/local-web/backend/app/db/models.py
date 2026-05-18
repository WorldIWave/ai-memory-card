# Input: 无（定义文件）  |  Output: Folder/Deck/Card/CardReviewState/ReviewLog ORM 类
# Role: 数据库 Schema 的单一来源，包含 Folder/Deck/Card/KnowledgeUnit/Review 等 ORM 模型
# Note: tags/scheduler_state_blob 以 JSON 列存储；软删除通过 deleted_at 字段实现
# Usage: 在 Service 层通过 Session 直接增删查改，Alembic 迁移需与本文件字段保持同步
"""
models.py - 数据库模型定义

职责: 定义所有 SQLModel ORM 模型（Deck、Card、CardReviewState 等）
输入: 无
输出: ORM 类，供 Service 层和 Session 使用
位置: DB层
关联: services/*.py, db/session.py, schemas/*.py
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import DateTime
from sqlmodel import JSON, Column, Field, SQLModel


class Folder(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Deck(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    default_scheduler_type: str = "sm2_basic"
    visibility: str = "normal"
    deleted_at: datetime | None = None
    source_type: str = "manual"
    folder_id: int | None = Field(default=1, foreign_key="folder.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Card(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    deck_id: int = Field(foreign_key="deck.id", index=True)
    knowledge_unit_ref_id: int | None = Field(default=None, index=True)
    card_type: str
    front: str
    back: str
    hint: str | None = None
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    render_format: str = "markdown"
    sort_order: int | None = None
    source_type: str = "manual"
    status: str = "active"
    deleted_at: datetime | None = None
    ai_lock_status: str = "user_locked"
    last_ai_task_id: int | None = Field(default=None, index=True)
    content_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeUnit(SQLModel, table=True):
    __tablename__ = "knowledge_unit"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    deck_id: int = Field(foreign_key="deck.id", index=True)
    provider_unit_id: str = Field(index=True)
    topic: str
    summary: str = ""
    source_document: str | None = None
    source_span: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    raw_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CardReviewState(SQLModel, table=True):
    card_id: int = Field(primary_key=True, foreign_key="card.id")
    scheduler_type: str = "sm2_basic"
    state_version: int = 1
    interval_days: float = 0.0
    ease_factor: float = 2.5
    repetition_count: int = 0
    lapses: int = 0
    last_reviewed_at: datetime | None = None
    next_due_at: datetime | None = None
    stability_score: float | None = None
    difficulty_score: float | None = None
    scheduler_state_blob: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    last_scheduler_decision_id: int | None = None
    learning_state: str = "new"
    learning_step: int = 0
    session_due_at: datetime | None = None
    session_repeats_today: int = 0
    hard_attempts_today: int = 0
    last_session_date: date | None = None


class ReviewLog(SQLModel, table=True):
    __tablename__ = "review_log"  # type: ignore[assignment]
    id: int | None = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="card.id", index=True)
    grade: str
    interval_days: float | None = None
    ease_factor: float | None = None
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str | None = None
    session_id: str | None = Field(default=None, index=True)
    trigger_type: str = "scheduled"
    state_before: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    state_after: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    is_undone: bool = False
    undone_at: datetime | None = None


class LearningEvent(SQLModel, table=True):
    __tablename__ = "learning_event"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="card.id", index=True)
    deck_id: int = Field(foreign_key="deck.id", index=True)
    event_type: str = Field(index=True)
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )


class ReviewSession(SQLModel, table=True):
    __tablename__ = "review_session"  # type: ignore[assignment]

    id: str = Field(primary_key=True)
    session_date: date
    scope: str
    deck_id: int | None = Field(default=None, foreign_key="deck.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "active"


class AppStudySettings(SQLModel, table=True):
    __tablename__ = "app_study_settings"

    id: int = Field(default=1, primary_key=True)
    daily_new_limit: int = 20
    daily_review_limit: int = 100
    scheduler_mode: str = "traditional"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AppSeedState(SQLModel, table=True):
    __tablename__ = "app_seed_state"

    seed_key: str = Field(primary_key=True)
    seed_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
