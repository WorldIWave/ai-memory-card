# Input: target_unit、learner_explanation、reference_material（API 请求体）
# Output: EvaluationRead（mastery_score + 四维度分数 + trace_id）
# Role: AI 评估接口的请求/响应 Schema，定义多维度评分结构
# Note: 四个维度分数默认 0.0；trace_id 用于追踪远端 AI 调用链路
from __future__ import annotations

from pydantic import BaseModel, Field


class EvaluationRequest(BaseModel):
    card_id: int | None = None
    target_card: dict[str, object] | None = None
    target_unit: dict[str, object] = Field(default_factory=dict)
    learner_explanation: str
    reference_material: str | None = None
    rubric_version: str = "v1"
    persist: bool = True


class EvaluationRead(BaseModel):
    mastery_score: float
    accuracy_score: float = Field(default=0.0)
    concept_score: float = Field(default=0.0)
    mechanism_score: float = Field(default=0.0)
    boundary_score: float = Field(default=0.0)
    misconception_score: float = Field(default=0.0)
    misconception_detected: bool = False
    confidence_score: float = Field(default=0.0)
    uncertain: bool = False
    feedback: str = ""
    weak_points: list[str] = Field(default_factory=list)
    reinforcement_advice: list[str] = Field(default_factory=list)
    rubric_version: str = "v1"
    provider_meta: dict[str, object] = Field(default_factory=dict)
    trace_id: str | None = None


class EvaluationRecordRequest(BaseModel):
    card_id: int
    learner_explanation: str
    result: EvaluationRead
