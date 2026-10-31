"""Pure scoring functions for the evaluation runner (SPEC §14). No network and no database."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from rapidfuzz import fuzz

FIELDS = ("invoice_number", "invoice_date", "supplier_name", "customer_name", "currency", "subtotal", "tax", "total")
AMOUNT_FIELDS = ("subtotal", "tax", "total")
NAME_FIELDS = ("supplier_name", "customer_name")
AMOUNT_TOLERANCE = Decimal("0.01")
FUZZY_THRESHOLD = 90
LINE_DESCRIPTION_THRESHOLD = 80
PARTIAL_MIN_LENGTH = 3

VALIDATION_CODES = frozenset(
    {
        "MISSING_FIELD",
        "INVALID_NUMBER",
        "INVALID_AMOUNT",
        "INVALID_DATE",
        "LINE_AMOUNT_MISMATCH",
        "SUBTOTAL_MISMATCH",
        "TOTAL_MISMATCH",
    }
)
FIELD_SCOPED_CODES = frozenset({"MISSING_FIELD", "INVALID_NUMBER"})

IssueKey = tuple[str, int, str, str | None]


def _div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


@dataclass(frozen=True)
class PR:
    """True positives, false positives and false negatives with the derived scores."""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float | None:
        return _div(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        return _div(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float | None:
        return _div(2 * self.tp, 2 * self.tp + self.fp + self.fn)

    def __add__(self, other: PR) -> PR:
        return PR(self.tp + other.tp, self.fp + other.fp, self.fn + other.fn)

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
        }


# ---------------------------------------------------------------- field correctness


def norm_invoice_number(value: str | None) -> str | None:
    """Same rule as the backend: upper case, letters and digits only, empty -> None."""
    if value is None:
        return None
    cleaned = re.sub(r"[^A-Z0-9]", "", value.upper())
    return cleaned or None


def norm_text(value: str | None) -> str:
    """Case-folded text with punctuation removed and whitespace collapsed."""
    return re.sub(r"\W+", " ", (value or "").casefold()).strip()


def is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def to_decimal(value: object) -> Decimal | None:
    if is_blank(value):
        return None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def amounts_close(pred: object, gt: object) -> bool:
    """True when both parse and differ by at most 0.01 (inclusive)."""
    a, b = to_decimal(pred), to_decimal(gt)
    return a is not None and b is not None and abs(a - b) <= AMOUNT_TOLERANCE


def text_match(field_name: str, pred: str, gt: str, hint: str | None = None) -> bool:
    """Normalised exact; partial_ratio for a "partial" hint; token_set_ratio for names."""
    norm = norm_invoice_number if field_name == "invoice_number" else norm_text
    p, g = norm(pred) or "", norm(gt) or ""
    if p == g:
        return True
    if hint == "partial":
        return len(p) >= PARTIAL_MIN_LENGTH and fuzz.partial_ratio(p, g) >= FUZZY_THRESHOLD
    return field_name in NAME_FIELDS and fuzz.token_set_ratio(p, g) >= FUZZY_THRESHOLD


def field_correct(field_name: str, pred: object, gt: object, hint: str | None = None) -> bool:
    if is_blank(gt):
        return is_blank(pred)
    if is_blank(pred):
        return False
    if field_name in AMOUNT_FIELDS:
        return amounts_close(pred, gt)
    if field_name == "invoice_date":
        return str(pred).strip() == str(gt).strip()
    if field_name == "currency":
        return str(pred).strip().upper() == str(gt).strip().upper()
    return text_match(field_name, str(pred), str(gt), hint)


def is_hallucination(pred: object, gt: object) -> bool:
    """A value was predicted although the ground truth says the field is not printed."""
    return is_blank(gt) and not is_blank(pred)


# ---------------------------------------------------------------- matching


def match_invoices(gt_numbers: Sequence[str | None], pred_numbers: Sequence[str | None]) -> dict[int, int]:
    """Map GT index -> predicted index by normalised number; GT without a number pairs by order."""
    matches: dict[int, int] = {}
    used: set[int] = set()
    for gi, number in enumerate(gt_numbers):
        key = norm_invoice_number(number)
        if key is None:
            continue
        for pi, candidate in enumerate(pred_numbers):
            if pi not in used and norm_invoice_number(candidate) == key:
                matches[gi] = pi
                used.add(pi)
                break
    free = [pi for pi in range(len(pred_numbers)) if pi not in used]
    for gi, number in enumerate(gt_numbers):
        if norm_invoice_number(number) is None and free:
            matches[gi] = free.pop(0)
    return matches


def _amounts_equal(a: object, b: object) -> bool:
    if is_blank(a) and is_blank(b):
        return True
    return amounts_close(a, b)


def _description_ratio(a: object, b: object) -> float:
    na, nb = (norm_text(None if a is None else str(a)), norm_text(None if b is None else str(b)))
    if not na and not nb:
        return 100.0
    return fuzz.token_set_ratio(na, nb)


def match_line_items(gt_lines: Sequence[Mapping[str, Any]], pred_lines: Sequence[Mapping[str, Any]]) -> PR:
    """Greedy matching on amount equality and description token_set_ratio >= 80."""
    used: set[int] = set()
    tp = 0
    for gt in gt_lines:
        best, best_ratio = None, -1.0
        for pi, pred in enumerate(pred_lines):
            if pi in used or not _amounts_equal(pred.get("amount"), gt.get("amount")):
                continue
            ratio = _description_ratio(pred.get("description"), gt.get("description"))
            if ratio >= LINE_DESCRIPTION_THRESHOLD and ratio > best_ratio:
                best, best_ratio = pi, ratio
        if best is not None:
            used.add(best)
            tp += 1
    return PR(tp=tp, fp=len(pred_lines) - tp, fn=len(gt_lines) - tp)


# ---------------------------------------------------------------- per-document scoring


@dataclass
class DocScore:
    matches: dict[int, int]
    fields_correct: dict[str, int]
    fields_total: dict[str, int]
    hallucinations: int
    null_gt_fields: int
    lines: PR
    gt_invoices: int
    pred_invoices: int
    exact: bool

    @property
    def correct_count(self) -> int:
        return sum(self.fields_correct.values())

    @property
    def total_count(self) -> int:
        return sum(self.fields_total.values())


def score_document(
    gt_invoices: Sequence[Mapping[str, Any]], pred_invoices: Sequence[Mapping[str, Any]], hints: Mapping[str, str]
) -> DocScore:
    """Score one document. Unmatched GT invoices count every field as wrong and every GT line as missed."""
    matches = match_invoices(
        [gt.get("invoice_number") for gt in gt_invoices], [pred.get("invoice_number") for pred in pred_invoices]
    )
    correct = dict.fromkeys(FIELDS, 0)
    hallucinations = null_gt = 0
    lines = PR()
    exact = bool(gt_invoices)
    for gi, gt in enumerate(gt_invoices):
        pred = pred_invoices[matches[gi]] if gi in matches else None
        flags = {f: pred is not None and field_correct(f, pred.get(f), gt.get(f), hints.get(f)) for f in FIELDS}
        for f in FIELDS:
            correct[f] += flags[f]
            null_gt += is_blank(gt.get(f))
            hallucinations += pred is not None and is_hallucination(pred.get(f), gt.get(f))
        exact = exact and all(flags.values())
        lines += match_line_items(gt.get("line_items") or [], (pred or {}).get("line_items") or [])
    matched_preds = set(matches.values())
    for pi, pred in enumerate(pred_invoices):
        if pi not in matched_preds:
            lines += PR(fp=len(pred.get("line_items") or []))
    return DocScore(
        matches=matches,
        fields_correct=correct,
        fields_total=dict.fromkeys(FIELDS, len(gt_invoices)),
        hallucinations=hallucinations,
        null_gt_fields=null_gt,
        lines=lines,
        gt_invoices=len(gt_invoices),
        pred_invoices=len(pred_invoices),
        exact=exact,
    )


@dataclass
class Tally:
    """Accumulates DocScore objects for one group of documents."""

    docs: int = 0
    exact_docs: int = 0
    fields_correct: dict[str, int] = field(default_factory=lambda: dict.fromkeys(FIELDS, 0))
    fields_total: dict[str, int] = field(default_factory=lambda: dict.fromkeys(FIELDS, 0))
    hallucinations: int = 0
    null_gt_fields: int = 0
    lines: PR = field(default_factory=PR)
    gt_invoices: int = 0
    pred_invoices: int = 0
    matched_invoices: int = 0

    def add(self, score: DocScore) -> None:
        self.docs += 1
        self.exact_docs += score.exact
        for f in FIELDS:
            self.fields_correct[f] += score.fields_correct[f]
            self.fields_total[f] += score.fields_total[f]
        self.hallucinations += score.hallucinations
        self.null_gt_fields += score.null_gt_fields
        self.lines += score.lines
        self.gt_invoices += score.gt_invoices
        self.pred_invoices += score.pred_invoices
        self.matched_invoices += len(score.matches)

    def summary(self) -> dict[str, Any]:
        per_field = {
            f: {
                "correct": self.fields_correct[f],
                "total": self.fields_total[f],
                "accuracy": _div(self.fields_correct[f], self.fields_total[f]),
            }
            for f in FIELDS
        }
        return {
            "documents": self.docs,
            "field_accuracy": per_field,
            "micro_accuracy": _div(sum(self.fields_correct.values()), sum(self.fields_total.values())),
            "document_exact_match": {"correct": self.exact_docs, "rate": _div(self.exact_docs, self.docs)},
            "line_items": self.lines.as_dict(),
            "hallucination": {
                "count": self.hallucinations,
                "null_gt_fields": self.null_gt_fields,
                "rate": _div(self.hallucinations, self.null_gt_fields),
            },
            "invoices": {
                "expected": self.gt_invoices,
                "predicted": self.pred_invoices,
                "matched": self.matched_invoices,
                "precision": _div(self.matched_invoices, self.pred_invoices),
                "recall": _div(self.matched_invoices, self.gt_invoices),
            },
        }


# ---------------------------------------------------------------- validation issues


def issue_key(doc_id: str, index: int, code: str, field_name: str | None) -> IssueKey:
    scoped = field_name if code in FIELD_SCOPED_CODES else None
    return (doc_id, index, code, scoped)


def observed_issue_keys(doc_id: str, index: int, issues: Iterable[Mapping[str, Any]]) -> set[IssueKey]:
    return {
        issue_key(doc_id, index, issue["code"], issue.get("field"))
        for issue in issues
        if issue["code"] in VALIDATION_CODES
    }


def expected_issue_keys(
    doc_id: str, gt_invoices: Sequence[Mapping[str, Any]], expected_issues: Iterable[Mapping[str, Any]]
) -> set[IssueKey]:
    """Key the manifest's expected issues by the GT invoice index (matched on invoice number)."""
    numbers = [norm_invoice_number(gt.get("invoice_number")) for gt in gt_invoices]
    keys: set[IssueKey] = set()
    for issue in expected_issues:
        if issue["code"] not in VALIDATION_CODES:
            continue
        wanted = norm_invoice_number(issue.get("invoice_number"))
        index = numbers.index(wanted) if wanted in numbers else 0
        keys.add(issue_key(doc_id, index, issue["code"], issue.get("field")))
    return keys


def score_issue_sets(expected: set[IssueKey], observed: set[IssueKey]) -> PR:
    return PR(tp=len(expected & observed), fp=len(observed - expected), fn=len(expected - observed))


# ---------------------------------------------------------------- duplicates


@dataclass(frozen=True)
class DuplicateScore:
    groups: int
    detected_groups: int
    flagged: int
    correct_flags: int

    @property
    def precision(self) -> float | None:
        return _div(self.correct_flags, self.flagged)

    @property
    def recall(self) -> float | None:
        return _div(self.detected_groups, self.groups)

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "groups": self.groups,
            "detected_groups": self.detected_groups,
            "flagged": self.flagged,
            "correct_flags": self.correct_flags,
        }


def score_duplicates(groups: Sequence[Sequence[str]], flags: Sequence[tuple[str, str | None]]) -> DuplicateScore:
    """Score DUPLICATE_INVOICE flags given as (document, duplicate_of_document) pairs of manifest ids.

    A flag is correct when both documents belong to the same group; a group is detected by any correct flag.
    """
    member_sets = [set(group) for group in groups]

    def group_of(doc: str, other: str | None) -> int | None:
        for index, members in enumerate(member_sets):
            if doc in members and other in members:
                return index
        return None

    hits = [group_of(doc, other) for doc, other in flags]
    correct = [h for h in hits if h is not None]
    return DuplicateScore(
        groups=len(member_sets), detected_groups=len(set(correct)), flagged=len(flags), correct_flags=len(correct)
    )


# ---------------------------------------------------------------- cross-checks


def _numbers(items: Iterable[Mapping[str, Any]] | Iterable[str]) -> set[str | None]:
    return {norm_invoice_number(i if isinstance(i, str) else i["invoice_number"]) for i in items}


def _mismatch_fields(items: Iterable[Mapping[str, Any]], key: str) -> dict[str | None, frozenset[str]]:
    result: dict[str | None, frozenset[str]] = {}
    for item in items:
        fields = item[key]
        names = [f if isinstance(f, str) else f["field"] for f in fields]
        result[norm_invoice_number(item["invoice_number"])] = frozenset(names)
    return result


def _set_differences(label: str, expected: set[str | None], observed: set[str | None]) -> list[str]:
    missing = sorted(str(n) for n in expected - observed)
    extra = sorted(str(n) for n in observed - expected)
    return [f"{label}: missing {n}" for n in missing] + [f"{label}: unexpected {n}" for n in extra]


def crosscheck_differences(expected: Mapping[str, Any], summary: Mapping[str, Any]) -> list[str]:
    """Compare an observed cross-check summary with the expected sets. Empty list means pass."""
    differences: list[str] = []
    for label in ("matched", "only_in_a", "only_in_b"):
        differences += _set_differences(label, _numbers(expected[label]), _numbers(summary.get(label, [])))
    want = _mismatch_fields(expected["mismatched"], "fields")
    got = _mismatch_fields(summary.get("mismatched", []), "differences")
    differences += _set_differences("mismatched", set(want), set(got))
    for number in sorted(set(want) & set(got), key=str):
        if want[number] != got[number]:
            differences.append(
                f"mismatched {number}: fields expected {sorted(want[number])}, observed {sorted(got[number])}"
            )
    return differences


# ---------------------------------------------------------------- percentiles


def percentile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolated percentile, q in 0..100. None for an empty sequence."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def p50(values: Sequence[float]) -> float | None:
    return percentile(values, 50)


def p95(values: Sequence[float]) -> float | None:
    return percentile(values, 95)
