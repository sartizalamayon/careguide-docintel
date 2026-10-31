# Evaluation Report

> Status: **TEMPLATE**. The coding agent fills every `TODO` with numbers copied from `eval/results/<run>/metrics.json` produced by `eval/run_eval.py`. Do not estimate or round differently from the runner's output. Delete this note when done.

## Setup

| Item | Value |
|---|---|
| Run ID / date | TODO (folder name under `eval/results/`) |
| Commit | TODO (`git rev-parse --short HEAD`) |
| Machine | TODO (CPU, cores, RAM; Docker Desktop resources) |
| Workers | TODO (`--scale worker=N`, concurrency, OCR_THREADS) |
| LLM | TODO (provider, model, prompt version `extract-v1`) |
| Embeddings | BAAI/bge-small-en-v1.5 (local, CPU) |
| Datasets | Synthetic (60 files / 81 invoices) + Katana ML (100 files / 100 invoices) + perf (1000-page PDF, 50-page scan). See `docs/DATASETS.md` |
| Method | End-to-end through the REST API (upload → background processing → results), scored against ground truth by `eval/metrics.py` |

## 1. Extraction accuracy (per field)

A field counts as correct if: amounts are within 0.01, dates are equal, currency is equal, names have token-set similarity ≥ 90 (partial match for Katana supplier/customer, whose labels include addresses), and null GT is correct only when the prediction is null.

| Field | Synthetic | Katana clean | Katana degraded | All |
|---|---|---|---|---|
| invoice_number | TODO | TODO | TODO | TODO |
| invoice_date | TODO | TODO | TODO | TODO |
| supplier_name | TODO | TODO | TODO | TODO |
| customer_name | TODO | TODO | TODO | TODO |
| currency | TODO | TODO | TODO | TODO |
| subtotal | TODO | TODO | TODO | TODO |
| tax | TODO | TODO | TODO | TODO |
| total | TODO | TODO | TODO | TODO |
| **Micro-average** | TODO | TODO | TODO | TODO |
| Document exact match (all 8 correct) | TODO | TODO | TODO | TODO |
| Line items P / R / F1 | TODO | TODO | TODO | TODO |
| **Hallucination rate** (value predicted where GT is null) | TODO | – | – | TODO |

Accuracy by input type:

| Category | Docs | Field accuracy | Line-item F1 |
|---|---|---|---|
| Digital PDF (single + multi-page) | TODO | TODO | TODO |
| Scanned PDF | TODO | TODO | TODO |
| Images: clean / photo / TIFF | TODO | TODO | TODO |
| Spreadsheets: xlsx / xls / csv (table mode) | TODO | TODO | TODO |
| Spreadsheets: invoice layout (LLM) | TODO | TODO | TODO |
| Multi-invoice PDFs (segmentation) | TODO | TODO | TODO |

## 2. Validation

| Check | Precision | Recall | Notes |
|---|---|---|---|
| Arithmetic and field rules (MISSING / INVALID / *_MISMATCH) | TODO | TODO | TODO |
| Duplicate detection (29 groups) | TODO | TODO | TODO |
| Cross-verification pairs (PDF↔Excel, PDF↔PDF) | TODO pass / 2 | | TODO |

Review rate: TODO % of invoices were routed to human review. Of those, TODO % carried an injected fault, and the rest were low confidence or ungrounded.

## 3. Robustness

| Metric | Value |
|---|---|
| Document success rate (completed + needs_review) / valid docs | TODO |
| Failure rate (failed / valid docs) | TODO |
| Graceful handling of the 8 invalid/corrupted files (expected code returned) | TODO / 8 |
| HTTP 5xx during the run | TODO |
| Documents stuck in `processing` at the end | TODO |

## 4. Performance

| Metric | Value |
|---|---|
| Median / p95 processing time per document: digital PDF | TODO / TODO s |
| Median / p95: scanned PDF or image (OCR) | TODO / TODO s |
| Median / p95: spreadsheet | TODO / TODO s |
| OCR time per page (median) | TODO s |
| 1000-page digital PDF: total time, pages/min, invoices found vs expected | TODO |
| 50-page scanned PDF: total time, pages/min | TODO |
| LLM calls, input/output tokens, cache hits | TODO |
| Peak worker memory during the 1000-page PDF | TODO (`docker stats`) |

## 5. Error analysis

TODO: 5–8 bullets drawn from `per_document.csv`, covering the most common wrong fields and why (OCR misread, segmentation, the LLM picking the due date…). Give a concrete example file for each, and say what would fix it.

## 6. Limitations

- Synthetic invoices are cleaner and more regular than real supplier documents. The Katana set is single-layout. Real-world accuracy should be re-measured on CareGuide's own documents.
- English only, and Tesseract `eng`. Bangla documents need the `ben` traineddata and a re-test.
- Segmentation relies on invoice-number and "Page x of y" cues. Multi-invoice PDFs without those cues fall back to one invoice per page.
- LLM free-tier rate limits affect throughput numbers. They are reported as measured, with the model named above.
