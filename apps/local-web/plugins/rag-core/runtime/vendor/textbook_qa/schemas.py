# Input: textbook content and intermediate extraction records.
# Output: dataclasses used by pipeline, QA, and serialization.
# Role: provide stable public schemas without pipeline dependencies.
# Note: keep structured artifact slots typed as Any to avoid circular imports.

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any


class QuestionType(str, Enum):
    DEFINITION = "definition"
    APPLICATION = "application"
    REASONING = "reasoning"
    MISCONCEPTION = "misconception"
    FORMULA = "formula"
    DEEP = "deep"


class Difficulty(str, Enum):
    BASIC = "basic"
    MEDIUM = "medium"
    ADVANCED = "advanced"


@dataclass
class TextbookDocument:
    source_path: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RejectedSpan:
    text: str
    reason: str
    line_start: int | None = None
    line_end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CleanedDocument:
    source_path: str
    title: str
    content: str
    rejected_spans: list[RejectedSpan] = field(default_factory=list)
    line_map: dict[int, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TextbookSection:
    title: str
    content: str
    level: int
    line_start: int
    line_end: int
    source: str
    parent_title: str | None = None
    heading_path: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SentenceSpan:
    text: str
    line_start: int
    line_end: int
    source: str
    section_title: str | None = None
    sentence_index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceSpan:
    source: str
    text: str
    line_start: int
    line_end: int
    section_title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedEntity:
    name: str
    entity_type: str
    evidence: list[EvidenceSpan] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedRelation:
    subject: str
    predicate: str
    object: str
    evidence: list[EvidenceSpan] = field(default_factory=list)
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgePoint:
    concept: str
    summary: str = ""
    evidence: list[EvidenceSpan] = field(default_factory=list)
    related_concepts: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    misconceptions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def primary_evidence(self) -> EvidenceSpan:
        if not self.evidence:
            raise ValueError("knowledge point has no evidence")
        return self.evidence[0]


@dataclass
class QuestionAnswerPair:
    question: str
    answer: str
    question_type: QuestionType
    difficulty: Difficulty
    source: EvidenceSpan
    concepts: list[str] = field(default_factory=list)
    correction_tip: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineArtifacts:
    cleaned_document: CleanedDocument | None = None
    sections: list[TextbookSection] = field(default_factory=list)
    sentences: list[SentenceSpan] = field(default_factory=list)
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    knowledge_points: list[KnowledgePoint] = field(default_factory=list)
    raw_qa_pairs: list[QuestionAnswerPair] = field(default_factory=list)
    optimized_qa_pairs: list[QuestionAnswerPair] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocks: list[Any] = field(default_factory=list)
    structured_knowledge_points: list[Any] = field(default_factory=list)
    schema_qa_pairs: list[QuestionAnswerPair] = field(default_factory=list)


@dataclass
class PipelineResult:
    qa_pairs: list[QuestionAnswerPair] = field(default_factory=list)
    artifacts: PipelineArtifacts = field(default_factory=PipelineArtifacts)


def dataclass_to_dict(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: dataclass_to_dict(getattr(value, item.name))
            for item in fields(value)
        }

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]

    if isinstance(value, tuple):
        return [dataclass_to_dict(item) for item in value]

    if isinstance(value, dict):
        return {
            dataclass_to_dict(key): dataclass_to_dict(item)
            for key, item in value.items()
        }

    return value
