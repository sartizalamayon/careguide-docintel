# Evaluation Report

> Scope: **full run, all 160 files** (60 synthetic, 100 Katana ML). Every number below is copied from `eval/results/20261101-full-v2/metrics.json` and `report.md`, produced by `eval/run_eval.py`. The first full run (`eval/results/20261101-full/`) found two extraction problems; section 5 explains them and the fix, and both runs are committed.

## Setup

| Item | Value |
|---|---|
| Run ID / date | `20261101-full-v2`, 2026-11-01 |
| Machine | Cloud container: 2 CPU cores, 7 GB RAM, no Docker (native Postgres 16 + pgvector, Redis, Tesseract) |
| Workers | 1 Celery worker, concurrency 2, `LLM_CONCURRENCY=4`, `OCR_THREADS=4` |
| LLM | Google Gemini, free tier, through the OpenAI-compatible endpoint. Main model `gemini-3.5-flash-lite` (131 calls), fallback `gemini-3.1-flash-lite` (25 calls, used when the main model returned HTTP 429). Prompt `extract-v2` |
| Embeddings | BAAI/bge-small-en-v1.5 (local, CPU) |
| Data | `datasets/eval/manifest_synthetic.jsonl` and `manifest_katanaml.jsonl`: 152 valid documents with 181 invoices, plus 8 invalid files |
| Method | End to end through the REST API (upload, background processing, results) on an empty database, scored against ground truth by `eval/metrics.py` |

## 1. Extraction accuracy

Correct means: amounts within 0.01, equal dates and currency, names with token-set similarity of at least 90, and a null ground truth is correct only when the prediction is null.

| Field | All (152 docs) | Katana ML (100) | Synthetic (52) |
|---|---|---|---|
| invoice_number | 100.0% | 100.0% | 100.0% |
| invoice_date | 100.0% | 100.0% | 100.0% |
| supplier_name | 99.4% | 99.0% | 100.0% |
| customer_name | 100.0% | 100.0% | 100.0% |
| currency | 100.0% | 100.0% | 100.0% |
| subtotal | 100.0% | 100.0% | 100.0% |
| tax | 100.0% | 100.0% | 100.0% |
| total | 100.0% | 100.0% | 100.0% |
| **Micro-average** | **99.9%** | **99.9%** | **100.0%** |
| Document exact match | 99.3% | 99.0% | 100.0% |
| Line items P / R / F1 | 99.7% / 99.7% / 99.7% | 99.8% | 99.7% |
| Hallucination rate (value where the truth is null) | 0.0% | n/a | 0.0% |
| Invoices found / expected | 181 / 181 | 100 / 100 | 81 / 81 |

Katana ML degraded scans (26 files: noise, blur, rotation) scored 100.0% on fields. Every synthetic category scored 100% on fields, including multi-page PDFs, multi-invoice PDFs, TIFFs, photos and all spreadsheet layouts.

The single field counted wrong is not an extraction error: the ground truth for `kat-test_22` gives the supplier as `907-77-8965`, which is the seller's tax ID printed below the name. The system read the name, "George, Casey and Harris".

## 2. Validation

| Check | Precision | Recall | Counts |
|---|---|---|---|
| Arithmetic and field rules | 100.0% | 100.0% | TP 11, FP 0, FN 0 |
| Duplicate detection | 100.0% | 100.0% | 29 / 29 groups, 0 false flags |
| Cross-verification pairs | 2 / 2 passed | | PDF↔Excel (`batch_5_invoices` vs `erp_export`), PDF↔PDF (`pdfpair_original` vs `pdfpair_received_scan`) |

Review rate is 69.1% of documents (107 invoices). 62 of those carry a known fault or are a known duplicate. Most of the rest are Katana invoices whose date is printed as an ambiguous number such as `07/04/2016`: the spec reads it month-first for USD but caps its confidence at 0.5, so a person confirms it. That is deliberate. Lowering the review rate means trusting a guess about the date order.

## 3. Robustness

| Metric | Value |
|---|---|
| Document success rate (completed + needs_review) / valid docs | 152 / 152 (100.0%) |
| Completed / needs review / failed / rejected (valid docs) | 47 / 105 / 0 / 0 |
| Graceful handling of invalid files (expected code returned) | 8 / 8 |
| HTTP 5xx during the run | 0 |
| Documents stuck in `processing` at the end | 0 |
| LLM rate limits (HTTP 429) during the run | 109 responses, all absorbed by retries and the fallback model |

The 8 invalid files returned their expected outcomes: `EMPTY_FILE`, `FILE_TYPE_MISMATCH`, `UNSUPPORTED_FILE_TYPE` on upload, and failures for the broken PDF, password-protected PDF, corrupt workbook, blank page and header-only CSV.

## 4. Performance

Measured on 2 cores with a free-tier key that rate-limited the run 109 times, so these numbers are conservative.

| Metric | Value |
|---|---|
| Whole run, 160 files | 6 min 24 s |
| Processing time per document, median / p95 | 3.30 / 10.63 s |
| Digital PDF, median / p95 | 1.93 / 3.95 s |
| Scanned PDF, median / p95 | 4.68 / 11.29 s |
| Clean image / degraded image, median | 3.21 / 3.64 s |
| Multi-invoice PDF (3–4 invoices), median | 3.54 s |
| Spreadsheet registers (table mode, no LLM) | 0.30 to 2.30 s |
| Invoice-layout spreadsheets | 40.6 s (both waited out rate limits) |
| LLM calls | 156 calls, 160,778 input and 90,598 output tokens, extraction call median 1.8 s |
| 1000-page digital PDF, parse and segmentation only (no LLM) | 0.7 to 1.5 s, peak 140 MB, 499 segments for 499 expected invoices |
| 50-page scanned PDF, OCR parse only (no LLM) | 40.1 s, 75 pages/min, peak 438 MB, 50 segments for 50 expected invoices |
| Full pipeline on the 1000-page file | not run: 499 LLM calls on a free key |

The 1000-page figures were measured by calling the parser and segmenter directly, not through the API. End-to-end time for a 499-invoice file is dominated by the LLM calls (one per invoice): at about 2 s per call and `LLM_CONCURRENCY=4`, roughly 4–5 minutes with a key that is not rate-limited.

## 5. Error analysis

The first full run (`20261101-full`, same models, prompt `extract-v1`) scored 97.1% on fields, 82.1% line-item F1 and 12% validation precision. Two causes explained almost all of it.

| Problem | Effect in run 1 | Cause | Fix | Run 2 |
|---|---|---|---|---|
| Line amounts | 81 false `LINE_AMOUNT_MISMATCH` / `SUBTOTAL_MISMATCH` flags; Katana line F1 61% | Katana invoices print Net worth and Gross worth (net + 10% VAT) per line. The prompt said "the line total as printed" and the model took gross | Prompt `extract-v2`, rule 7: use the net line total when both are printed | 0 false flags, line F1 99.7% |
| Dates | Katana dates 61% (39 wrong) | Every miss was a day/month swap of an ambiguous US date (`07/04/2016` read as 7 April). The prompt already had the rule; the lite model did not follow it | The same rule is applied in code after extraction (`resolve_ambiguous_date`): it only picks between the two readings of the date printed in the text | 100% |

Earlier, the 1000-page file also exposed a segmentation bug (646 segments instead of 499: a street number on the line after "INVOICE" was read as an invoice number). It was fixed before these runs.

## 6. Limitations

- Synthetic invoices are cleaner and more regular than real supplier documents, and Katana ML is a single layout. Accuracy should be re-measured on CareGuide's own documents.
- The high review rate on Katana comes from ambiguous numeric dates. With documents from one known region, a fixed date order would remove most of these reviews.
- Free-tier rate limits slowed the run (109 HTTP 429 responses). They did not cause failures, but they make timing noisy.
- The 1000-page file was measured without the LLM stage.
- English only, with Tesseract `eng`. Bangla documents need the `ben` traineddata and a re-test.
- Segmentation relies on invoice-number and "Page x of y" cues. Multi-invoice PDFs without those cues fall back to one invoice per page.
