# Input: document blocks prepared for model-backed extraction.
# Output: provider-neutral extraction candidates and availability results.
# Role: define stable interfaces shared by pretrained extractor providers.
# Note: keep this module free of concrete model dependencies.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

from textbook_qa.structured_kp import DocumentBlock


@dataclass
class ExtractionCandidate:
    provider: str
    block_id: str
    label: str
    text: str
    start_char: int | None = None
    end_char: int | None = None
    confidence: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionProviderResult:
    provider: str
    candidates: list[ExtractionCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractorAvailability:
    provider: str
    available: bool
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ExtractionProviderRequestError(RuntimeError):
    def __init__(self, provider: str, message: str, *, retryable: bool = False) -> None:
        self.provider = provider
        self.retryable = retryable
        super().__init__(f"{provider} request failed: {message}")


class ModelExtractorProvider(Protocol):
    name: str

    def availability(self) -> ExtractorAvailability:
        ...

    def extract(self, blocks: Sequence[DocumentBlock]) -> ExtractionProviderResult:
        ...
