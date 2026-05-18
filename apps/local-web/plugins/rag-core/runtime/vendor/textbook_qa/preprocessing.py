# Input: raw textbook documents and optional metadata.
# Output: cleaned documents, sections, sentences, and rejects.
# Role: normalize source text before extraction begins.
# Note: preserve source locations for evidence tracing.

from __future__ import annotations

import re
from collections.abc import Iterable

from textbook_qa.schemas import (
    CleanedDocument,
    RejectedSpan,
    SentenceSpan,
    TextbookDocument,
    TextbookSection,
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LINK_ONLY_RE = re.compile(r"^\s*(?:\[[^\]]+\]\([^\)]+\)|<?https?://\S+>?)\s*$")
_PAGE_NUMBER_RE = re.compile(r"^\s*\d+\s*$")
_SENTENCE_RE = re.compile(r".+?(?:[\u3002\uff01\uff1f\uff1b!?;.]|$)", re.DOTALL)
_METADATA_RE = re.compile(
    r"^>\s*(source|author|title|publisher|date|isbn|version)\s*:",
    re.IGNORECASE,
)
_METADATA_MARKERS = (
    "source:",
    "author:",
    "publisher:",
    "isbn",
    "download",
    "github",
    "\u539f\u59cb\u6587\u4ef6\u4e0b\u8f7d",
    "\u539f\u6587\u4f5c\u8005",
    "\u4f5c\u8005\u4ecb\u7ecd",
    "\u4e0b\u8f7d\u94fe\u63a5",
    "\u672c\u6587\u662f",
    "\u7ffb\u8bd1",
    "\u5907\u6ce8",
)


def clean_document(document: TextbookDocument) -> CleanedDocument:
    cleaned_lines: list[str] = []
    rejected_spans: list[RejectedSpan] = []
    line_map: dict[int, int] = {}
    previous_blank = False
    seen_content = False

    for original_line_number, line in enumerate(document.content.splitlines(), start=1):
        stripped = line.strip()
        reason = _rejection_reason(line, seen_content)

        if reason is not None:
            rejected_spans.append(
                RejectedSpan(
                    text=line,
                    reason=reason,
                    line_start=original_line_number,
                    line_end=original_line_number,
                )
            )
            continue

        if stripped == "":
            if previous_blank:
                continue
            previous_blank = True
        else:
            previous_blank = False
            seen_content = True

        cleaned_lines.append(line)
        line_map[len(cleaned_lines)] = original_line_number

    text = "\n".join(cleaned_lines)
    return CleanedDocument(
        source_path=document.source_path,
        title=document.title,
        content=text,
        rejected_spans=rejected_spans,
        line_map=line_map,
        metadata=dict(document.metadata),
    )


def split_sections(cleaned: CleanedDocument) -> list[TextbookSection]:
    sections: list[TextbookSection] = []
    heading_stack: dict[int, str] = {}
    current_title: str | None = None
    current_level = 0
    current_parent: str | None = None
    current_path: list[str] = []
    content_lines: list[str] = []
    content_line_numbers: list[int] = []
    content_cleaned_numbers: list[int] = []

    def clear_content() -> None:
        nonlocal content_lines, content_line_numbers, content_cleaned_numbers
        content_lines = []
        content_line_numbers = []
        content_cleaned_numbers = []

    def flush() -> None:
        if not any(line.strip() for line in content_lines):
            clear_content()
            return

        if current_title is None:
            clear_content()
            return

        start = 0
        end = len(content_lines)
        while start < end and not content_lines[start].strip():
            start += 1
        while end > start and not content_lines[end - 1].strip():
            end -= 1

        trimmed_lines = content_lines[start:end]
        trimmed_line_numbers = content_line_numbers[start:end]
        trimmed_cleaned_numbers = content_cleaned_numbers[start:end]

        section = TextbookSection(
            title=current_title,
            content="\n".join(trimmed_lines),
            level=current_level,
            line_start=trimmed_line_numbers[0],
            line_end=trimmed_line_numbers[-1],
            source=cleaned.source_path,
            parent_title=current_parent,
            heading_path=current_path.copy(),
            metadata={
                "line_numbers": trimmed_line_numbers.copy(),
                "cleaned_line_numbers": trimmed_cleaned_numbers.copy(),
            },
        )
        sections.append(section)
        clear_content()

    line_map = cleaned.line_map
    for cleaned_line_number, line in enumerate(cleaned.content.splitlines(), start=1):
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            for existing_level in list(heading_stack):
                if existing_level >= level:
                    del heading_stack[existing_level]
            heading_stack[level] = title
            ordered_levels = sorted(heading_stack)
            current_path = [heading_stack[item] for item in ordered_levels]
            current_title = title
            current_level = level
            current_parent = current_path[-2] if len(current_path) > 1 else None
            continue

        original_line_number = line_map.get(cleaned_line_number, cleaned_line_number)
        content_lines.append(line)
        content_line_numbers.append(original_line_number)
        content_cleaned_numbers.append(cleaned_line_number)

    if current_title is None and any(line.strip() for line in content_lines):
        current_title = cleaned.title or cleaned.source_path
        current_level = 0
        current_parent = None
        current_path = [current_title] if current_title else []
    flush()
    return sections


def split_sentences(section: TextbookSection) -> list[SentenceSpan]:
    sentences: list[SentenceSpan] = []
    line_numbers = section.metadata.get("line_numbers") or list(
        range(section.line_start, section.line_end + 1)
    )

    for line, original_line_number in _zip_longest_fill(
        section.content.splitlines(),
        line_numbers,
    ):
        stripped = line.strip()
        if not stripped:
            continue

        parts = [stripped] if _is_formula_only(stripped) else _sentence_parts(stripped)
        for part in parts:
            sentence = SentenceSpan(
                text=part,
                line_start=original_line_number,
                line_end=original_line_number,
                source=section.source,
                section_title=section.title,
                sentence_index=len(sentences),
                metadata={"heading_path": section.heading_path},
            )
            sentences.append(sentence)

    return sentences


def preprocess_document(
    document: TextbookDocument,
) -> tuple[CleanedDocument, list[TextbookSection], list[SentenceSpan]]:
    cleaned = clean_document(document)
    sections = split_sections(cleaned)
    sentences = [
        sentence
        for section in sections
        for sentence in split_sentences(section)
    ]
    return cleaned, sections, sentences


def _rejection_reason(line: str, seen_content: bool) -> str | None:
    stripped = line.strip()
    if stripped == "[TOC]":
        return "table_of_contents_marker"
    if stripped == ">":
        return "empty_blockquote"
    if _LINK_ONLY_RE.match(line):
        return "link_only"
    if _PAGE_NUMBER_RE.match(line):
        return "page_number"
    if not seen_content and _METADATA_RE.match(line):
        return "leading_metadata_blockquote"
    if not seen_content and stripped.startswith(">") and _has_metadata_marker(stripped):
        return "metadata_marker"
    return None


def _has_metadata_marker(text: str) -> bool:
    normalized = text.lstrip("> ").strip().casefold()
    return any(marker.casefold() in normalized for marker in _METADATA_MARKERS)


def _is_formula_only(text: str) -> bool:
    if text in {"$$", "\\[", "\\]"}:
        return True
    formula_chars = r"[A-Za-z0-9_{}\\\s+\-*/=(),.^]+"
    return bool(re.fullmatch(formula_chars, text) and "=" in text)


def _sentence_parts(text: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in _SENTENCE_RE.finditer(text)
        if match.group(0).strip()
    ]


def _zip_longest_fill(
    lines: Iterable[str],
    line_numbers: Iterable[int],
) -> Iterable[tuple[str, int]]:
    last_line_number = None
    line_number_iter = iter(line_numbers)
    for line in lines:
        try:
            last_line_number = next(line_number_iter)
        except StopIteration:
            if last_line_number is None:
                last_line_number = 1
        yield line, last_line_number
