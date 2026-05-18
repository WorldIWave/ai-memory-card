# Input: QA pairs with concepts, metadata, answers, and source evidence.
# Output: deterministic standalone-anchor and semantic-duplicate quality signals.
# Role: centralize P3 QA quality heuristics before optional model-based scoring.
# Note: keep this generic; do not add sample-file or assignment-specific filters.

from __future__ import annotations

import re
from collections.abc import Sequence

from textbook_qa.schemas import QuestionAnswerPair

_GENERIC_CONCEPTS = {
    "concept",
    "term",
    "topic",
    "item",
    "value",
    "question",
    "answer",
    "example",
    "section",
    "公式",
    "概念",
    "问题",
    "答案",
    "例子",
}
_CHINESE_LOOKUP_RE = re.compile(r"^(什么是.+|.+是什么|.+表示什么|.+代表什么)[？?]?$")
_ENGLISH_LOOKUP_RE = re.compile(r"^(what\s+(is|are|does|do)\b|how\s+is\b|how\s+are\b)", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]*|\\[A-Za-z]+|[A-Z]{2,}|\$[^$]+\$|[\u4e00-\u9fff]+")
_SYMBOL_RE = re.compile(r"\$[^$]+\$|\\[A-Za-z]+|[A-Z]{2,}|[A-Za-z]+_[A-Za-z0-9_]+")


def standalone_anchor_issue(pair: QuestionAnswerPair) -> str:
    """Return a rejection reason when a short lookup question drops the real concept anchor."""

    question = _compact(pair.question)
    # English lookup questions often introduce a valid term that is missing from noisy concept metadata.
    # For now this strict anchor check is limited to CJK short lookup fragments.
    if not question or not _contains_cjk(pair.question) or not _looks_like_lookup_question(pair.question):
        return ""

    anchors = _concept_anchors(pair)
    if not anchors:
        return ""
    if any(anchor in question for anchor in anchors):
        return ""
    if _has_symbol_anchor(pair):
        return ""
    return "missing_explicit_concept_anchor"


def semantic_duplicate_reason(left: QuestionAnswerPair, right: QuestionAnswerPair) -> str:
    if left is right:
        return ""
    if _question_type(left) != _question_type(right):
        return ""
    left_plan = _metadata_text(left, "question_plan_id")
    right_plan = _metadata_text(right, "question_plan_id")
    if left_plan and left_plan == right_plan:
        return "same_question_plan"
    if not _same_concept(left, right):
        return ""
    if _questions_share_concept_anchor(left, right):
        if _jaccard(_tokens(left.answer), _tokens(right.answer)) >= 0.58:
            return "same_concept_type_similar_answer"
        if _jaccard(_tokens(left.question), _tokens(right.question)) >= 0.72:
            return "same_concept_type_similar_question"
    return ""


def semantic_duplicate_rate(pairs: Sequence[QuestionAnswerPair]) -> float:
    if not pairs:
        return 0.0
    duplicate_indexes: set[int] = set()
    for index, pair in enumerate(pairs):
        if any(semantic_duplicate_reason(previous, pair) for previous in pairs[:index]):
            duplicate_indexes.add(index)
    return round(len(duplicate_indexes) / len(pairs), 6)


def _concept_anchors(pair: QuestionAnswerPair) -> list[str]:
    anchors: list[str] = []
    for concept in pair.concepts:
        normalized = _compact(concept)
        if _is_meaningful_concept(normalized):
            anchors.append(normalized)
    concept_id = _metadata_text(pair, "concept_id")
    if concept_id:
        normalized = _compact(concept_id.replace("_", " "))
        if _is_meaningful_concept(normalized):
            anchors.append(normalized)
    return _unique(anchors)


def _is_meaningful_concept(text: str) -> bool:
    if not text or text in _GENERIC_CONCEPTS:
        return False
    if _contains_cjk(text):
        return len(text) >= 2
    return len(text) >= 4


def _questions_share_concept_anchor(left: QuestionAnswerPair, right: QuestionAnswerPair) -> bool:
    anchors = set(_concept_anchors(left)) & set(_concept_anchors(right))
    if not anchors:
        return False
    left_question = _compact(left.question)
    right_question = _compact(right.question)
    return any(anchor in left_question and anchor in right_question for anchor in anchors)


def _same_concept(left: QuestionAnswerPair, right: QuestionAnswerPair) -> bool:
    left_id = _metadata_text(left, "concept_id").casefold()
    right_id = _metadata_text(right, "concept_id").casefold()
    if left_id and right_id:
        return left_id == right_id
    left_concepts = set(_concept_anchors(left))
    right_concepts = set(_concept_anchors(right))
    return bool(left_concepts and right_concepts and left_concepts & right_concepts)


def _has_symbol_anchor(pair: QuestionAnswerPair) -> bool:
    question_symbols = _symbols(pair.question)
    if not question_symbols:
        return False
    reference_symbols = _symbols(" ".join([pair.answer, pair.source.text]))
    return bool(question_symbols & reference_symbols)


def _symbols(text: str) -> set[str]:
    return {_compact(match.group(0)) for match in _SYMBOL_RE.finditer(text) if _compact(match.group(0))}


def _looks_like_lookup_question(question: str) -> bool:
    text = question.strip()
    compact = _compact(text)
    if _contains_cjk(text):
        return len(compact) <= 18 and bool(_CHINESE_LOOKUP_RE.match(compact))
    return len(text.split()) <= 12 and bool(_ENGLISH_LOOKUP_RE.match(text))


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in _WORD_RE.finditer(text.casefold()):
        token = match.group(0).strip().casefold()
        if not token:
            continue
        if _contains_cjk(token):
            tokens.update(_cjk_ngrams(token))
        elif len(token) >= 2:
            tokens.add(token)
    return tokens


def _cjk_ngrams(text: str) -> set[str]:
    if len(text) <= 2:
        return {text}
    return {text[index : index + 2] for index in range(len(text) - 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _question_type(pair: QuestionAnswerPair) -> str:
    return str(getattr(pair.question_type, "value", pair.question_type)).strip().casefold()


def _metadata_text(pair: QuestionAnswerPair, key: str) -> str:
    return str(pair.metadata.get(key) or pair.source.metadata.get(key) or "").strip()


def _compact(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text).casefold(), flags=re.UNICODE)


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in str(text))


def _unique(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique_items.append(item)
    return unique_items
