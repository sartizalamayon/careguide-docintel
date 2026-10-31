# Evaluation Report

> Scope: **reduced run, 20 files.** The full set (160 files) could not be run because the only available LLM key is on the Gemini free tier, which allows 20 requests per day per model. This report covers a deterministic 20-file subset and says plainly what it does and does not show. Every number below is copied from `eval/results/20261031-reduced/metrics.json` and `report.md`, produced by `eval/run_eval.py`.

## Setup

| Item | Value |
|---|---|
| Run ID / date | `20261031-reduced`, 2026-10-31 |
| Code version | `a38ba5d` (the run folder and this report are committed after it) |
| Machine | Cloud container: 2 CPU cores, 7 GB RAM, no Docker (native Postgres 16 + pgvector, Redis, Tesseract) |
| Workers | 1 Celery worker, concurrency 1, `LLM_CONCURRENCY=1`, `OCR_THREADS=4` |
| LLM | Google Gemini via the OpenAI-compatible endpoint, model `gemini-2.5-flash-lite`, prompt version `extract-v1`. The spec's default `gemini-3.8-flash` was overloaded (HTTP 503) and `gemini-2.5-flash` hit its free daily quota |
| Embeddings | BAAI/bge-small-en-v1.5 (local, CPU) |
| Subset | `eval/manifest_reduced.jsonl`: the first N files of each chosen category, picked before the run and not by outcome. 12 valid documents (35 invoices) and 8 invalid files |
| Method | End to end through the REST API (upload, background processing, results), scored against ground truth by `eval/metrics.py` |

What is in the subset: 3 digital PDFs, 2 scanned PDFs, 1 photo, 2 Katana ML images, and 4 spreadsheets in table mode (no LLM). All 8 invalid or corrupted files are included.

What is not in it: invoice-layout spreadsheets, multi-invoice and multi-page PDFs, TIFFs, degraded Katana images, duplicate-detection groups, the cross-verification pairs, and the 1000-page and 50-page performance files.

## 1. Extraction accuracy

Correct means: amounts within 0.01, equal dates and currency, names with token-set similarity of at least 90, and a null ground truth is correct only when the prediction is null.

| Field | All (12 docs, 35 invoices scored) |
|---|---|
| invoice_number | 100.0% (35/35) |
| invoice_date | 100.0% (35/35) |
| supplier_name | 100.0% (35/35) |
| customer_name | 100.0% (35/35) |
| currency | 100.0% (35/35) |
| subtotal | 100.0% (35/35) |
| tax | 100.0% (35/35) |
| total | 100.0% (35/35) |
| **Micro-average** | **100.0%** |
| Document exact match | 12/12 |
| Line items P / R / F1 | 100% / 100% / 100% (118 of 118) |
| Hallucination rate | 0.0% (0 of 1 fields whose ground truth is null) |
| Invoices found / expected | 35 / 35 |

By group: synthetic (10 docs, 33 invoices) and Katana ML clean images (2 docs, 2 invoices) both scored 100%.

How to read this: 100% on 12 documents is a clean result, not proof of 100% in general. Only 8 documents used the LLM, and 4 of the 12 were spreadsheets parsed without it. The null-field check rests on a single field, so the hallucination rate is weakly supported.

## 2. Validation

| Check | Precision | Recall | Counts |
|---|---|---|---|
| Arithmetic and field rules | 100.0% | 100.0% | TP 3, FP 0, FN 0 |
| Duplicate detection | not measured | not measured | no duplicate groups in the subset |
| Cross-verification pairs | not measured | not measured | no pairs in the subset |

Three invoices were routed to review (`syn-digital_02`, `syn-erp_export_eu`, `syn-erp_export`), and all three carried a known injected fault. Review rate: 25.0% of valid documents.

A separate manual cross-check of `batch_5_invoices.pdf` against `erp_export.xlsx` (not part of this scored run) matched 2 invoices and reported a total mismatch, a date mismatch, and one unmatched invoice on each side. It is shown in `docs/screenshots/compare.png`.

## 3. Robustness

| Metric | Value |
|---|---|
| Document success rate (completed + needs_review) / valid docs | 12 / 12 (100.0%) |
| Completed / needs review / failed / rejected (valid docs) | 9 / 3 / 0 / 0 |
| Failure rate (failed / valid docs) | 0.0% |
| Graceful handling of invalid files (expected code returned) | 8 / 8 |
| HTTP 5xx during the run | 0 |
| Documents stuck in `processing` at the end | 0 |

The 8 invalid files returned their expected outcomes: `EMPTY_FILE`, `FILE_TYPE_MISMATCH`, `UNSUPPORTED_FILE_TYPE` on upload, and failures for the broken PDF, password-protected PDF, corrupt workbook, blank page and header-only CSV.

## 4. Performance

Measured on 2 cores with one worker and one LLM call at a time, so these are conservative.

| Metric | Value |
|---|---|
| Processing time per document, median / p95, all 12 | 2.76 / 4.50 s |
| Digital PDF, median / p95 | 1.97 / 3.29 s |
| Scanned PDF, median / p95 | 3.63 / 3.69 s |
| Clean image, median / p95 | 3.14 / 3.58 s |
| Photo | 5.47 s |
| Spreadsheet (csv, xls, xlsx, multi-sheet) | 0.42 to 2.88 s |
| Throughput, all 12 | 26.4 pages/min |
| LLM calls, tokens, cache hits | 8 calls, 7,197 input and 3,985 output tokens, 0 cache hits (cache emptied first) |
| OCR time per page, 1000-page and 50-page runs, peak memory | not measured |

## 5. Error analysis

There were no wrong fields in this run, so there is nothing to attribute to OCR misreads or LLM mistakes. The full 160-file run is needed to find real failure modes, and this section should be written from its `per_document.csv`.

## 6. Limitations

- This is a 20-file subset. It checks that the pipeline works end to end and handles bad files, not how accurate it is on hard cases.
- The free-tier LLM key limits throughput and made a full run impossible. A key with a paid quota (or several days of free quota) is needed to run `make eval` on all 160 files.
- The model used was `gemini-2.5-flash-lite`, not the spec's default.
- Synthetic invoices are cleaner and more regular than real supplier documents. The Katana ML set is single-layout. Accuracy should be re-measured on CareGuide's own documents.
- English only, with Tesseract `eng`. Bangla documents need the `ben` traineddata and a re-test.
- Segmentation relies on invoice-number and "Page x of y" cues. Multi-invoice PDFs without those cues fall back to one invoice per page.
