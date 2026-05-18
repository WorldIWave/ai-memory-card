from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GenerateCardsDocument(BaseModel):
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


class GenerateCardsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v1"] = "v1"
    deck: dict[str, Any] = Field(default_factory=dict)
    documents: list[GenerateCardsDocument] = Field(min_length=1)
    topics: list[str] | None = None
    generation_prefs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topics")
    @classmethod
    def normalize_topics(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [item.strip() for item in value if item and item.strip()]
        return normalized or None


class GenerateCardsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deck: dict[str, Any] = Field(default_factory=dict)
    cards: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_units: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider_meta: dict[str, Any] = Field(default_factory=dict)
