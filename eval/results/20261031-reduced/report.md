# Evaluation run

Started 2026-10-31T17:13:34+00:00, finished 2026-10-31T17:14:08+00:00, API http://localhost:8000. 20 manifest documents, 0 not uploaded.

## 1. Extraction accuracy

### Field accuracy

| Field | all | katanaml | katanaml/image_clean | synthetic |
|---|---|---|---|---|
| invoice_number | 100.0% | 100.0% | 100.0% | 100.0% |
| invoice_date | 100.0% | 100.0% | 100.0% | 100.0% |
| supplier_name | 100.0% | 100.0% | 100.0% | 100.0% |
| customer_name | 100.0% | 100.0% | 100.0% | 100.0% |
| currency | 100.0% | 100.0% | 100.0% | 100.0% |
| subtotal | 100.0% | 100.0% | 100.0% | 100.0% |
| tax | 100.0% | 100.0% | 100.0% | 100.0% |
| total | 100.0% | 100.0% | 100.0% | 100.0% |
| micro average | 100.0% | 100.0% | 100.0% | 100.0% |

### By group

| Group | Docs | Field acc. | Exact match | Line P | Line R | Line F1 | Hallucination | Invoices matched |
|---|---|---|---|---|---|---|---|---|
| all | 12 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 35/35 |
| katanaml | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 2/2 |
| katanaml/image_clean | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 2/2 |
| synthetic | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 33/33 |
| synthetic/csv_semicolon_eu | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 6/6 |
| synthetic/digital_pdf | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 3/3 |
| synthetic/image_photo | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 1/1 |
| synthetic/scanned_pdf | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 2/2 |
| synthetic/xls_ledger | 1 | 100.0% | 100.0% | n/a | n/a | n/a | n/a | 6/6 |
| synthetic/xlsx_multisheet_register | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 10/10 |
| synthetic/xlsx_register | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 5/5 |

## 2. Validation

| Check | Precision | Recall | Counts |
|---|---|---|---|
| Arithmetic and field rules | 100.0% | 100.0% | TP 3, FP 0, FN 0 |
| Duplicate detection | n/a | n/a | 0/0 groups, 0 false flags |

| Cross-check pair | Kind | Result | Differences |
|---|---|---|---|

## 3. Robustness and operations

| Metric | Value |
|---|---|
| Valid documents | 12 |
| Completed / needs review / failed / rejected | 9 / 3 / 0 / 0 |
| Success rate | 100.0% |
| Failure rate | 0.0% |
| Document review rate | 25.0% |
| Invoices routed to review (with known fault) | 3 (3) |
| Graceful handling of invalid files | 8/8 |
| HTTP 5xx responses | 0 |
| Stuck documents | 0 |

## 4. Performance (processing time in seconds)

| Category | Docs | Pages | Doc p50 | Doc p95 | Page p50 | Page p95 | Pages/min | Invoices found/expected |
|---|---|---|---|---|---|---|---|---|
| all | 12 | 14 | 2.76 | 4.50 | 2.31 | 4.50 | 26.44 | 35/35 |
| csv_semicolon_eu | 1 | 1 | 1.51 | 1.51 | 1.51 | 1.51 | 39.76 | 6/6 |
| digital_pdf | 3 | 3 | 1.97 | 3.29 | 1.97 | 3.29 | 25.63 | 3/3 |
| image_clean | 2 | 2 | 3.14 | 3.58 | 3.14 | 3.58 | 19.13 | 2/2 |
| image_photo | 1 | 1 | 5.47 | 5.47 | 5.47 | 5.47 | 10.97 | 1/1 |
| scanned_pdf | 2 | 2 | 3.63 | 3.69 | 3.63 | 3.69 | 16.53 | 2/2 |
| xls_ledger | 1 | 1 | 0.42 | 0.42 | 0.42 | 0.42 | 141.51 | 6/6 |
| xlsx_multisheet_register | 1 | 3 | 2.88 | 2.88 | 0.96 | 0.96 | 62.61 | 10/10 |
| xlsx_register | 1 | 1 | 0.94 | 0.94 | 0.94 | 0.94 | 63.97 | 5/5 |

## 5. LLM usage

Not reported by `/api/v1/stats`.
