# Input: 设置页提交的学习上限与 ORM AppStudySettings 实例  |  Output: StudySettingsRead/StudySettingsUpdate DTO
# Output: 统一全局学习设置的读写格式，供 settings API 和 review session 调度复用
# Role: 这是“全应用一套学习设置”的 API 契约层
# Use: 这里的字段会直接影响调度逻辑，新增设置项时要同步 service、前端设置页和迁移
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SchedulerMode = Literal["traditional", "ai_rl"]


class StudySettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    daily_new_limit: int
    daily_review_limit: int
    scheduler_mode: SchedulerMode
    updated_at: datetime


class StudySettingsUpdate(BaseModel):
    daily_new_limit: int = Field(ge=0)
    daily_review_limit: int = Field(ge=0)
    scheduler_mode: SchedulerMode | None = None
