# Input: candidate QuestionAnswerPair records before API judge or final optimization.
# Output: kept QA pairs plus auditable rejection metadata.
# Role: apply structural and metadata-based QA checks before model judging.
# Note: content relevance should come from extractor content_role, not keyword blacklists.

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from textbook_qa.qa_quality import standalone_anchor_issue
from textbook_qa.schemas import QuestionAnswerPair

_NON_INSTRUCTIONAL_CONTENT_ROLES = {
    "course_logistics",
    "metadata",
    "navigation",
    "tooling_instruction",
    "administrative",
    "assignment_submission",
    "account_setup",
    "source_note",
    "non_instructional",
    "download_instruction",
}
_CONTEXT_MARKERS = (
    "\u6587\u4e2d", "\u672c\u6587", "\u4e0a\u6587", "\u4e0a\u8ff0", "\u4e0a\u9762", "\u8fd9\u6bb5",
    "\u8fd9\u91cc", "\u4e0b\u5217", "\u7ed9\u51fa\u7684", "\u793a\u4f8b\u4e0b", "\u4f8b\u5b50\u4e2d",
    "in the text", "above", "given example", "this example",
)
_WEAK_REFERENCE_RE = re.compile(r"^(\u8fd9\u4e2a|\u8be5|\u4e0a\u8ff0|\u6587\u4e2d|\u8fd9\u91cc)")


def filter_qa_pairs(pairs: Sequence[QuestionAnswerPair]) -> tuple[list[QuestionAnswerPair], list[dict[str, Any]]]:
    kept: list[QuestionAnswerPair] = []
    rejected: list[dict[str, Any]] = []
    for index, pair in enumerate(pairs):
        reason = qa_rejection_reason(pair)
        if not reason:
            kept.append(pair)
            continue
        rejected.append(
            {
                "index": index,
                "reason": reason,
                "question": pair.question,
                "source": pair.source.source,
                "line_start": pair.source.line_start,
                "line_end": pair.source.line_end,
            }
        )
    return kept, rejected


def qa_rejection_reason(pair: QuestionAnswerPair) -> str:
    question = _normalize(pair.question)
    answer = _normalize(pair.answer)

    if _content_role(pair) in _NON_INSTRUCTIONAL_CONTENT_ROLES:
        return "non_instructional_content_role"
    if _support_usage_status(pair) == "unused_required_support":
        return "unused_required_support"
    if _is_context_dependent(question):
        return "context_dependent_question"
    anchor_issue = standalone_anchor_issue(pair)
    if anchor_issue:
        return anchor_issue
    if _has_incomplete_latex(pair.question) or _has_incomplete_latex(pair.answer):
        return "incomplete_latex"
    if len(question) < 8 or len(answer) < 6:
        return "too_short"
    return ""


def _support_usage_status(pair: QuestionAnswerPair) -> str:
    return str(pair.metadata.get("support_usage_status", "") or "").strip().casefold()


def _content_role(pair: QuestionAnswerPair) -> str:
    role = pair.metadata.get("content_role") or pair.source.metadata.get("content_role")
    return str(role or "").strip().casefold().replace("-", "_").replace(" ", "_")


def _is_context_dependent(question: str) -> bool:
    if any(marker.casefold() in question for marker in _CONTEXT_MARKERS):
        return True
    return bool(_WEAK_REFERENCE_RE.search(question))


def _has_incomplete_latex(text: str) -> bool:
    if not _looks_like_latex(text):
        return False
    if _unescaped_dollar_count(text) % 2 == 1:
        return True
    if text.count(r"\left") != text.count(r"\right"):
        return True
    if text.count("{") != text.count("}"):
        return True
    return False


def _looks_like_latex(text: str) -> bool:
    return "$" in text or "\\" in text or "{" in text or "}" in text


def _unescaped_dollar_count(text: str) -> int:
    count = 0
    escaped = False
    for char in text:
        if char == "\\" and not escaped:
            escaped = True
            continue
        if char == "$" and not escaped:
            count += 1
        escaped = False
    return count


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()
