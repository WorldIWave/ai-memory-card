# Input: generated QA pairs and pipeline artifacts.
# Output: deduplicated QA, JSON data, and Markdown reports.
# Role: rank, filter, and serialize final question sets.
# Note: keep ordering stable for reproducible outputs.

from __future__ import annotations

import re

from textbook_qa.qa_guard import qa_rejection_reason
from textbook_qa.qa_quality import semantic_duplicate_reason
from textbook_qa.schemas import (
    Difficulty,
    PipelineArtifacts,
    QuestionAnswerPair,
    QuestionType,
    dataclass_to_dict,
)

_DIFFICULTY_ORDER = {
    Difficulty.BASIC: 0,
    Difficulty.MEDIUM: 1,
    Difficulty.ADVANCED: 2,
}
_FILE_LIKE_RE = re.compile(r"(?:^|\b)(?:test_|.*\.md\b|.*\.pdf\b|[A-Za-z]+_[A-Za-z0-9_-]+)")
_LEAD_IN_ANSWERS = {
    "we use the following notation",
    "the following notation is used",
    "\u6211\u4eec\u4f7f\u7528\u4ee5\u4e0b\u7b26\u53f7",
    "\u5982\u4e0b\u6240\u793a",
    "\u5176\u4e2d",
}


def optimize_qa_pairs(
    pairs: list[QuestionAnswerPair],
    max_questions: int | None = None,
    *,
    apply_guard_checks: bool = True,
) -> list[QuestionAnswerPair]:
    candidates = [
        (index, pair)
        for index, pair in enumerate(pairs)
        if pair.question.strip()
        and pair.answer.strip()
        and pair.source.text.strip()
        and not _is_low_quality_pair(pair)
        and (not apply_guard_checks or not qa_rejection_reason(pair))
    ]
    ordered_candidates = sorted(candidates, key=lambda item: _rank_key(item[1], item[0]))
    filtered: list[tuple[int, QuestionAnswerPair]] = []
    seen_questions: set[str] = set()
    seen_semantic_keys: set[str] = set()

    for original_index, pair in ordered_candidates:
        normalized_question = _normalize_question(pair.question)
        if normalized_question in seen_questions:
            continue

        semantic_key = _semantic_key(pair)
        if semantic_key and semantic_key in seen_semantic_keys:
            continue
        if any(semantic_duplicate_reason(kept_pair, pair) for _kept_index, kept_pair in filtered):
            continue

        seen_questions.add(normalized_question)
        if semantic_key:
            seen_semantic_keys.add(semantic_key)
        filtered.append((original_index, pair))

    optimized = [pair for _, pair in filtered]
    if max_questions is not None and len(optimized) > max_questions:
        return _balanced_truncate(optimized, max_questions)
    return optimized


def qa_pairs_to_jsonable(pairs: list[QuestionAnswerPair]) -> list[dict[str, object]]:
    return dataclass_to_dict(pairs)


def markdown_report(pairs: list[QuestionAnswerPair]) -> str:
    lines = ["# Textbook QA Report"]
    for index, pair in enumerate(pairs, start=1):
        lines.extend(
            [
                "",
                f"## {index}. {pair.question}",
                f"- Type: {pair.question_type.value}",
                f"- Difficulty: {pair.difficulty.value}",
                f"- Answer: {pair.answer}",
                f"- Evidence: {pair.source.source}:{pair.source.line_start}-{pair.source.line_end}",
            ]
        )
        if pair.source.section_title:
            lines.append(f"- Section: {pair.source.section_title}")
        lines.append(f"> {pair.source.text}")
    return "\n".join(lines) + "\n"


def artifacts_to_jsonable(artifacts: PipelineArtifacts) -> dict[str, object]:
    return dataclass_to_dict(artifacts)


def _rank_key(pair: QuestionAnswerPair, original_index: int) -> tuple[int, float, int]:
    return (_DIFFICULTY_ORDER.get(pair.difficulty, 99), -_quality_score(pair), original_index)


def _quality_score(pair: QuestionAnswerPair) -> float:
    value = pair.metadata.get("qa_quality_score", 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _balanced_truncate(
    pairs: list[QuestionAnswerPair], max_questions: int
) -> list[QuestionAnswerPair]:
    if max_questions <= 0:
        return []

    selected_indexes: set[int] = set()
    seen_types: set[object] = set()

    for index, pair in enumerate(pairs):
        if len(selected_indexes) >= max_questions:
            break
        if pair.question_type in seen_types:
            continue
        seen_types.add(pair.question_type)
        selected_indexes.add(index)

    for index, _pair in enumerate(pairs):
        if len(selected_indexes) >= max_questions:
            break
        selected_indexes.add(index)

    return [pair for index, pair in enumerate(pairs) if index in selected_indexes]


def _is_low_quality_pair(pair: QuestionAnswerPair) -> bool:
    question = _normalize_question(pair.question)
    answer = _normalize_answer(pair.answer)
    concepts = " ".join(pair.concepts).casefold()

    if _looks_like_document_name(question) or _looks_like_document_name(concepts):
        return True
    if answer in _LEAD_IN_ANSWERS:
        return True
    if answer.endswith((":", "\uff1a")) and len(answer) <= 40:
        return True
    if len(answer) < 12 and not re.search(r"[=$]|\\mathbb|\\in", answer):
        return True
    return False


def _looks_like_document_name(text: str) -> bool:
    compact = text.strip().strip(" ?!#*`\"'")
    return bool(_FILE_LIKE_RE.search(compact))


def _normalize_answer(answer: str) -> str:
    return re.sub(r"\s+", " ", answer.casefold()).strip().strip(".?:?")


def _semantic_key(pair: QuestionAnswerPair) -> str:
    if pair.question_type is not QuestionType.DEFINITION:
        return ""
    concepts = sorted({_normalize_concept(concept) for concept in pair.concepts if _normalize_concept(concept)})
    compact_answer = re.sub(r"\s+", "", _normalize_answer(pair.answer))
    if not concepts or len(compact_answer) < 6:
        return ""
    return "|".join(concepts) + "::" + compact_answer


def _normalize_concept(concept: str) -> str:
    return re.sub(r"\s+", "", concept.casefold()).strip()


def _normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.casefold()).strip()
