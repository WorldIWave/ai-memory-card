# Input: cleaned textbook blocks and extracted evidence spans.
# Output: compact structured knowledge point data models.
# Role: define stable enums and dataclasses for structured extraction.
# Note: keep this module independent from schemas imports back into it.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from textbook_qa.schemas import EvidenceSpan


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    FORMULA = "formula"
    IMAGE_REF = "image_ref"
    METADATA = "metadata"


class KnowledgePointType(str, Enum):
    DEFINITION = "definition"
    NOTATION = "notation"
    FORMULA = "formula"
    PROCEDURE = "procedure"
    MISCONCEPTION = "misconception"
    APPLICATION = "application"
    DEEP_REASONING = "deep_reasoning"


@dataclass
class DocumentBlock:
    id: str
    type: BlockType
    text: str
    line_start: int
    line_end: int
    heading_path: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VariableDefinition:
    symbol: str
    meaning: str
    condition: str = ""


@dataclass
class KnowledgeRelation:
    type: str
    source_concept: str
    target_concept: str
    evidence_text: str = ""
    confidence: float = 0.0


@dataclass
class StructuredKnowledgePoint:
    id: str
    type: KnowledgePointType
    title: str
    statement: str
    conditions: list[str]
    formula: str
    variables: list[VariableDefinition]
    common_mistakes: list[str]
    source_block_ids: list[str]
    evidence: list[EvidenceSpan]
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    fact_type: str = ""
    pedagogical_value: float = 0.0
    standalone: bool = True
    relations: list[KnowledgeRelation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.fact_type:
            self.fact_type = self.type.value
