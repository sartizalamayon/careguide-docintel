"""U41-U43: evaluation metric functions (eval/metrics.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "eval"))

import metrics  # noqa: E402

# ---------------------------------------------------------------- U41: field correctness


def test_u41_partial_hint_accepts_name_without_address():
    gt = "Acme Care Services, 12 Main Street, Springfield, IL 62701"
    assert metrics.field_correct("supplier_name", "Acme Care Services", gt, "partial")


def test_u41_partial_hint_rejects_prediction_shorter_than_three():
    assert not metrics.field_correct("supplier_name", "Ac", "Acme Care Services, 12 Main Street", "partial")


def test_u41_partial_hint_rejects_unrelated_name():
    assert not metrics.field_correct(
        "supplier_name", "Globex Corporation", "Acme Care Services, 12 Main Street", "partial"
    )


def test_u41_without_hint_text_must_match_after_normalisation():
    assert metrics.field_correct("invoice_number", "inv 1003", "INV-1003")
    assert not metrics.field_correct("invoice_number", "INV-100", "INV-1003")


def test_u41_names_use_token_set_ratio_without_a_hint():
    assert metrics.field_correct("customer_name", "Doyle Ltd", "Doyle Ltd.")
    assert metrics.field_correct("customer_name", "Ltd Doyle", "Doyle Ltd")
    assert not metrics.field_correct("customer_name", "Stanley LLC", "Doyle Ltd")


def test_u41_null_versus_null_is_correct():
    assert metrics.field_correct("customer_name", None, None)
    assert metrics.field_correct("tax", None, None)
    assert not metrics.is_hallucination(None, None)


def test_u41_value_where_gt_is_null_is_a_hallucination():
    assert not metrics.field_correct("tax", "10.00", None)
    assert metrics.is_hallucination("10.00", None)


def test_u41_missing_prediction_where_gt_has_a_value_is_wrong_not_a_hallucination():
    assert not metrics.field_correct("total", None, "10.00")
    assert not metrics.is_hallucination(None, "10.00")


def test_u41_amount_tolerance_is_inclusive_at_one_cent():
    assert metrics.field_correct("total", "100.01", "100.00")
    assert metrics.field_correct("total", "99.99", "100.00")
    assert not metrics.field_correct("total", "100.02", "100.00")
    assert not metrics.field_correct("total", "abc", "100.00")


def test_u41_currency_and_date_must_be_equal():
    assert metrics.field_correct("currency", "usd", "USD")
    assert not metrics.field_correct("currency", "EUR", "USD")
    assert metrics.field_correct("invoice_date", "2025-06-18", "2025-06-18")
    assert not metrics.field_correct("invoice_date", "2025-06-19", "2025-06-18")


def test_u41_invoice_matching_by_number_then_by_order_for_numberless_gt():
    matches = metrics.match_invoices(["A-1", None, "B-2"], ["b2", "zzz", "a 1"])
    assert matches == {0: 2, 2: 0, 1: 1}


def test_u41_document_exact_match_needs_all_eight_fields():
    gt = {
        "invoice_number": "INV-1",
        "invoice_date": "2025-01-02",
        "supplier_name": "Acme",
        "customer_name": None,
        "currency": "USD",
        "subtotal": "10.00",
        "tax": "1.00",
        "total": "11.00",
        "line_items": [],
    }
    assert metrics.score_document([gt], [dict(gt)], {}).exact
    wrong = {**gt, "tax": "2.00"}
    score = metrics.score_document([gt], [wrong], {})
    assert not score.exact
    assert score.correct_count == 7
    assert score.total_count == 8
    hallucinated = metrics.score_document([gt], [{**gt, "customer_name": "Someone"}], {})
    assert hallucinated.hallucinations == 1
    assert hallucinated.null_gt_fields == 1


# ---------------------------------------------------------------- U42: line items


def _line(description: str, amount: str) -> dict:
    return {"description": description, "quantity": "1", "unit_price": amount, "amount": amount}


def test_u42_greedy_line_matching_two_of_three():
    gt = [
        _line("Nitrile gloves, box of 100", "477.20"),
        _line("Courier delivery", "1367.60"),
        _line("Data entry", "61.30"),
    ]
    pred = [
        _line("Nitrile gloves box of 100", "477.20"),
        _line("Courier delivery", "1367.60"),
        _line("Data entry", "99.99"),
    ]
    result = metrics.match_line_items(gt, pred)
    assert (result.tp, result.fp, result.fn) == (2, 1, 1)
    assert result.precision == 2 / 3
    assert result.recall == 2 / 3
    assert result.f1 == 2 / 3


def test_u42_a_predicted_line_is_used_only_once():
    gt = [_line("Gloves", "10.00"), _line("Gloves", "10.00")]
    pred = [_line("Gloves", "10.00")]
    result = metrics.match_line_items(gt, pred)
    assert (result.tp, result.fp, result.fn) == (1, 0, 1)
    assert result.precision == 1.0
    assert result.recall == 0.5


def test_u42_description_below_threshold_does_not_match():
    result = metrics.match_line_items([_line("Courier delivery", "5.00")], [_line("Laptop", "5.00")])
    assert result.tp == 0


def test_u42_no_lines_gives_undefined_scores():
    result = metrics.match_line_items([], [])
    assert result.precision is None
    assert result.recall is None
    assert result.f1 is None


# ---------------------------------------------------------------- U43: issues, duplicates, cross-checks


def test_u43_issue_precision_and_recall():
    gt = [{"invoice_number": "A-1"}, {"invoice_number": "B-2"}]
    expected = metrics.expected_issue_keys(
        "doc",
        gt,
        [
            {"invoice_number": "A-1", "code": "TOTAL_MISMATCH", "field": None},
            {"invoice_number": "B-2", "code": "MISSING_FIELD", "field": "tax"},
            {"invoice_number": "B-2", "code": "INVALID_DATE", "field": None},
        ],
    )
    observed = metrics.observed_issue_keys(
        "doc",
        0,
        [
            {"code": "TOTAL_MISMATCH", "field": "total"},
            {"code": "SUBTOTAL_MISMATCH", "field": "subtotal"},
            {"code": "LOW_CONFIDENCE", "field": "total"},
        ],
    ) | metrics.observed_issue_keys("doc", 1, [{"code": "MISSING_FIELD", "field": "tax"}])
    result = metrics.score_issue_sets(expected, observed)
    assert (result.tp, result.fp, result.fn) == (2, 1, 1)
    assert result.precision == 2 / 3
    assert result.recall == 2 / 3


def test_u43_missing_field_is_keyed_by_field_but_other_codes_are_not():
    assert metrics.issue_key("d", 0, "MISSING_FIELD", "tax") == ("d", 0, "MISSING_FIELD", "tax")
    assert metrics.issue_key("d", 0, "TOTAL_MISMATCH", "total") == ("d", 0, "TOTAL_MISMATCH", None)


def test_u43_expected_issue_for_numberless_invoice_maps_to_the_numberless_gt():
    gt = [{"invoice_number": "A-1"}, {"invoice_number": None}]
    keys = metrics.expected_issue_keys(
        "d", gt, [{"invoice_number": None, "code": "MISSING_FIELD", "field": "invoice_number"}]
    )
    assert keys == {("d", 1, "MISSING_FIELD", "invoice_number")}


def test_u43_duplicate_groups_detected_false_positive_and_missed():
    groups = [["a", "b"], ["c", "d"]]
    flags = [("b", "a"), ("x", "y")]
    result = metrics.score_duplicates(groups, flags)
    assert (result.groups, result.detected_groups, result.flagged, result.correct_flags) == (2, 1, 2, 1)
    assert result.precision == 0.5
    assert result.recall == 0.5


def test_u43_duplicate_pointing_outside_its_group_is_a_false_positive():
    result = metrics.score_duplicates([["a", "b"], ["c", "d"]], [("a", "c")])
    assert result.correct_flags == 0
    assert result.detected_groups == 0


def test_u43_crosscheck_passes_and_lists_differences():
    expected = {
        "matched": ["AP-1"],
        "mismatched": [{"invoice_number": "AP-2", "fields": ["total"]}],
        "only_in_a": ["AP-3"],
        "only_in_b": [],
    }
    summary = {
        "matched": [{"invoice_number": "ap1"}],
        "mismatched": [{"invoice_number": "AP-2", "differences": [{"field": "total", "a": "1", "b": "2"}]}],
        "only_in_a": [{"invoice_number": "AP-3"}],
        "only_in_b": [],
    }
    assert metrics.crosscheck_differences(expected, summary) == []
    wrong = {
        **summary,
        "mismatched": [{"invoice_number": "AP-2", "differences": [{"field": "tax"}]}],
        "only_in_b": [{"invoice_number": "AP-9"}],
    }
    differences = metrics.crosscheck_differences(expected, wrong)
    assert "only_in_b: unexpected AP9" in differences
    assert any("fields expected ['total'], observed ['tax']" in d for d in differences)


def test_percentiles():
    assert metrics.p50([1, 2, 3, 4, 5]) == 3
    assert metrics.p95([10]) == 10
    assert metrics.percentile([0, 10], 95) == 9.5
    assert metrics.p50([]) is None
