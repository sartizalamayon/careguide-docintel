"""Split an ordered list of pages into invoice segments (SPEC §6.6). Deterministic, no LLM."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from app.log import log
from app.pipeline.normalize import norm_invoice_number
from app.pipeline.types import PageText, Segment

INV_RE = re.compile(r"(?i)\b(?:invoice|inv|bill)\s*(?:no\.?|number|num|#|id)?\s*[:#.]?\s*([A-Z0-9][A-Z0-9\-/]{2,24})")
PAGE_RE = re.compile(r"(?i)\bpage\s+(\d{1,4})\s*(?:of|/)\s*(\d{1,4})\b")

HEADER_SHARE = 0.4
NO_CUE_PAGE_LIMIT = 10
MAX_SEGMENT_PAGES = 25
PAGE_JOINER = "\n\n----- page {n} -----\n\n"
MAX_TEXT_CHARS = 60_000
HEAD_CHARS = 40_000
TAIL_CHARS = 20_000
TRUNCATION_MARK = "\n[... truncated ...]\n"


def header_lines(text: str) -> list[str]:
    """The top 40% of the page's non-empty lines, each with whitespace collapsed."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return lines[: math.ceil(len(lines) * HEADER_SHARE)]


def find_invoice_number(text: str) -> str | None:
    """First INV_RE capture in the page header that contains a digit, normalised (SPEC §5)."""
    header = "\n".join(header_lines(text))
    pos = 0
    while match := INV_RE.search(header, pos):
        if any(ch.isdigit() for ch in match.group(1)):
            return norm_invoice_number(match.group(1))
        pos = match.start() + 1
    return None


def find_page_index(text: str) -> int | None:
    """The N of a 'Page N of M' cue, if the page has one."""
    match = PAGE_RE.search(text)
    return int(match.group(1)) if match else None


def _group_by_cues(
    pages: Sequence[PageText], numbers: list[str | None], indexes: list[int | None]
) -> list[list[PageText]]:
    groups: list[list[PageText]] = []
    current: str | None = None
    for page, number, index in zip(pages, numbers, indexes, strict=True):
        new_number = number is not None and current is not None and number != current
        if not groups or index == 1 or new_number:
            groups.append([page])
            current = number
        else:
            groups[-1].append(page)
            current = current or number
    return groups


def _cap(group: list[PageText]) -> list[list[PageText]]:
    if len(group) <= MAX_SEGMENT_PAGES:
        return [group]
    log.warning(
        "segment_split",
        page_start=group[0].page_no,
        page_end=group[-1].page_no,
        pages=len(group),
        max_pages=MAX_SEGMENT_PAGES,
    )
    return [group[i : i + MAX_SEGMENT_PAGES] for i in range(0, len(group), MAX_SEGMENT_PAGES)]


def join_pages(pages: Sequence[PageText]) -> str:
    text = pages[0].text + "".join(PAGE_JOINER.format(n=page.page_no) + page.text for page in pages[1:])
    if len(text) > MAX_TEXT_CHARS:
        text = text[:HEAD_CHARS] + TRUNCATION_MARK + text[-TAIL_CHARS:]
    return text


def segment_pages(pages: Sequence[PageText]) -> list[Segment]:
    if not pages:
        return []
    numbers = [find_invoice_number(page.text) for page in pages]
    indexes = [find_page_index(page.text) for page in pages]
    no_cues = all(n is None for n in numbers) and all(i is None for i in indexes)
    if no_cues and len(pages) > NO_CUE_PAGE_LIMIT:
        groups = [[page] for page in pages]
    else:
        groups = _group_by_cues(pages, numbers, indexes)
    return [
        Segment(page_start=chunk[0].page_no, page_end=chunk[-1].page_no, text=join_pages(chunk))
        for group in groups
        for chunk in _cap(group)
    ]
