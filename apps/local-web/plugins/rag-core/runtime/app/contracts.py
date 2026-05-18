from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

GradeValue = Literal["again", "hard", "good", "easy"]


class PluginDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = "document.txt"
    content_type: str = "text/plain"
    text: str

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("document text is required")
        return value


class PluginTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: Literal["rag.generate_cards"]
    mode: Literal["api"] = "api"
    provider_profile: str = "openai_compatible"
    deck: dict[str, Any] = Field(default_factory=dict)
    documents: list[PluginDocument] = Field(min_length=1)
    topics: list[str] | None = None
    generation_prefs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topics")
    @classmethod
    def normalize_topics(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [item.strip() for item in value if item and item.strip()]
        return normalized or None


class PluginEvaluationTargetCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    card_type: str = ""
    front: str
    back: str
    tags: list[str] = Field(default_factory=list)


class PluginEvaluationTargetUnit(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    provider_unit_id: str | None = None
    topic: str | None = None
    summary: str | None = None
    source_span: dict[str, Any] | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class PluginEvaluationTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: Literal["evaluation.score_explanation"]
    mode: Literal["api"] = "api"
    provider_profile: str = "openai_compatible"
    rubric_version: str = "v1"
    target_card: PluginEvaluationTargetCard
    target_unit: PluginEvaluationTargetUnit | None = None
    learner_explanation: str

    @field_validator("learner_explanation")
    @classmethod
    def explanation_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("learner_explanation is required")
        return value.strip()


class PluginSchedulerTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: Literal["scheduler.plan_review"]
    mode: Literal["local"] = "local"
    grade: GradeValue
    card: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    review_history: list[dict[str, Any]] = Field(default_factory=list)
    understanding: dict[str, Any] | None = None
    recent_burden: dict[str, Any] = Field(default_factory=dict)
    baseline_decision: dict[str, Any] = Field(default_factory=dict)


class PluginTaskError(BaseModel):
    code: str
    message: str


class PluginTaskResponse(BaseModel):
    task_id: str
    status: Literal["succeeded", "failed"]
    result: dict[str, Any] | None = None
    error: PluginTaskError | None = None
