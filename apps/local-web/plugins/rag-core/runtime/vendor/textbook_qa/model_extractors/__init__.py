# Input: model extractor provider interface definitions.
# Output: public model extractor interface exports.
# Role: expose stable provider dataclasses and protocols.
# Note: keep imports lightweight for optional provider dependencies.

from __future__ import annotations

from textbook_qa.model_extractors.base import (
    ExtractionCandidate,
    ExtractionProviderResult,
    ExtractorAvailability,
    ModelExtractorProvider,
)

__all__ = [
    "ExtractionCandidate",
    "ExtractionProviderResult",
    "ExtractorAvailability",
    "ModelExtractorProvider",
]
