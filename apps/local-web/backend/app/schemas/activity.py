# Input: 前端提交的 note / report 参数与活动查询结果  |  Output: 学习事件、卡片活动、复习历史的 API DTO
# Output: 统一约束活动事件的入参与回包格式，供 routes/service/前端时间线共用
# Role: 这是 activity 模块在 API 边界上的数据契约层
# Use: 新增事件类型或活动字段时先改这里，再同步 service 转换逻辑与前端 types
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LearningEventCreate(BaseModel):
    reason: str = Field(min_length=1)
    note: str | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class CardNoteCreate(BaseModel):
    note: str = Field(min_length=1)
    source: str | None = None

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class CardActivityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    created_at: datetime
    summary: str
    payload: dict[str, object]


class ReviewHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    card_id: int
    deck_id: int | None
    card_front: str
    deck_name: str | None
    grade: str
    interval_days: float | None
    reviewed_at: datetime
    session_id: str | None
