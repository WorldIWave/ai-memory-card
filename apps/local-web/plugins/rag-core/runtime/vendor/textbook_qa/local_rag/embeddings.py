# Input: plain text snippets for local retrieval.
# Output: deterministic hashed lexical embedding vectors.
# Role: provide a CPU-only fallback embedding provider for local RAG.
# Note: vectors are normalized unless the input has no lexical tokens.

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

_CHINESE_SPAN = "\u4e00-\u9fff"
_TOKEN_RE = re.compile(
    r"\$([^$\n]+)\$"
    r"|[A-Za-z]+(?:'[A-Za-z]+)?"
    r"|\d+(?:\.\d+)?"
    r"|[" + _CHINESE_SPAN + r"]+"
)
_CHINESE_TOKEN_RE = re.compile(r"^[" + _CHINESE_SPAN + r"]+$")


class LexicalEmbeddingProvider:
    """Create deterministic lexical embeddings with feature hashing."""

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be a positive integer")
        self.dimensions = dimensions

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.encode_one(text) for text in texts]

    def encode_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokenize(text):
            index = _token_index(token, self.dimensions)
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same length")
    return sum(left_value * right_value for left_value, right_value in zip(left, right))


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        formula_inner = match.group(1)
        if formula_inner is not None:
            tokens.extend(_tokenize(formula_inner))
            continue

        token = match.group(0).lower()
        tokens.append(token)
        if len(token) > 1 and _CHINESE_TOKEN_RE.fullmatch(token):
            tokens.extend(token)
    return tokens


def _token_index(token: str, dimensions: int) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % dimensions
