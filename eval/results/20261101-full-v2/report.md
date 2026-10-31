# Evaluation run

Started 2026-10-31T20:17:54+00:00, finished 2026-10-31T20:24:24+00:00, API http://localhost:8000. 160 manifest documents, 0 not uploaded.

## 1. Extraction accuracy

### Field accuracy

| Field | all | katanaml | katanaml/image_clean | katanaml/image_poor_quality | synthetic |
|---|---|---|---|---|---|
| invoice_number | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| invoice_date | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| supplier_name | 99.4% | 99.0% | 98.6% | 100.0% | 100.0% |
| customer_name | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| currency | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| subtotal | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| tax | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| total | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| micro average | 99.9% | 99.9% | 99.8% | 100.0% | 100.0% |

### By group

| Group | Docs | Field acc. | Exact match | Line P | Line R | Line F1 | Hallucination | Invoices matched |
|---|---|---|---|---|---|---|---|---|
| all | 152 | 99.9% | 99.3% | 99.7% | 99.7% | 99.7% | 0.0% | 181/181 |
| katanaml | 100 | 99.9% | 99.0% | 99.8% | 99.8% | 99.8% | n/a | 100/100 |
| katanaml/image_clean | 74 | 99.8% | 98.6% | 100.0% | 100.0% | 100.0% | n/a | 74/74 |
| katanaml/image_poor_quality | 26 | 100.0% | 100.0% | 99.0% | 99.0% | 99.0% | n/a | 26/26 |
| synthetic | 52 | 100.0% | 100.0% | 99.6% | 99.6% | 99.6% | 0.0% | 81/81 |
| synthetic/csv_semicolon_eu | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 6/6 |
| synthetic/digital_pdf | 20 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 20/20 |
| synthetic/digital_pdf_multipage | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 4/4 |
| synthetic/image_clean | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 4/4 |
| synthetic/image_photo | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 4/4 |
| synthetic/image_tiff | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 2/2 |
| synthetic/image_tiff_multipage | 1 | 100.0% | 100.0% | 96.2% | 96.2% | 96.2% | n/a | 1/1 |
| synthetic/pdf_multi_invoice | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 7/7 |
| synthetic/scanned_pdf | 8 | 100.0% | 100.0% | 97.8% | 97.8% | 97.8% | n/a | 8/8 |
| synthetic/scanned_pdf_multi_invoice | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 2/2 |
| synthetic/xls_ledger | 1 | 100.0% | 100.0% | n/a | n/a | n/a | n/a | 6/6 |
| synthetic/xlsx_invoice_layout | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 2/2 |
| synthetic/xlsx_multisheet_register | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 10/10 |
| synthetic/xlsx_register | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 5/5 |

## 2. Validation

| Check | Precision | Recall | Counts |
|---|---|---|---|
| Arithmetic and field rules | 100.0% | 100.0% | TP 11, FP 0, FN 0 |
| Duplicate detection | 100.0% | 100.0% | 29/29 groups, 0 false flags |

| Cross-check pair | Kind | Result | Differences |
|---|---|---|---|
| syn-batch_5_invoices vs syn-erp_export | pdf_excel | pass |  |
| syn-pdfpair_original vs syn-pdfpair_received_scan | pdf_pdf | pass |  |

## 3. Robustness and operations

| Metric | Value |
|---|---|
| Valid documents | 152 |
| Completed / needs review / failed / rejected | 47 / 105 / 0 / 0 |
| Success rate | 100.0% |
| Failure rate | 0.0% |
| Document review rate | 69.1% |
| Invoices routed to review (with known fault) | 107 (62) |
| Graceful handling of invalid files | 8/8 |
| HTTP 5xx responses | 0 |
| Stuck documents | 0 |

## 4. Performance (processing time in seconds)

| Category | Docs | Pages | Doc p50 | Doc p95 | Page p50 | Page p95 | Pages/min | Invoices found/expected |
|---|---|---|---|---|---|---|---|---|
| all | 152 | 167 | 3.30 | 10.63 | 3.26 | 10.51 | 13.07 | 181/181 |
| csv_semicolon_eu | 1 | 1 | 1.52 | 1.52 | 1.52 | 1.52 | 39.55 | 6/6 |
| digital_pdf | 20 | 20 | 1.93 | 3.95 | 1.93 | 3.95 | 25.01 | 20/20 |
| digital_pdf_multipage | 4 | 9 | 12.70 | 13.54 | 5.28 | 6.58 | 11.64 | 4/4 |
| image_clean | 78 | 78 | 3.21 | 9.84 | 3.21 | 9.84 | 13.42 | 78/78 |
| image_photo | 4 | 4 | 5.43 | 5.51 | 5.43 | 5.51 | 12.47 | 4/4 |
| image_poor_quality | 26 | 26 | 3.64 | 10.56 | 3.64 | 10.56 | 11.32 | 26/26 |
| image_tiff | 2 | 2 | 5.16 | 5.19 | 5.16 | 5.19 | 11.63 | 2/2 |
| image_tiff_multipage | 1 | 2 | 6.55 | 6.55 | 3.28 | 3.28 | 18.31 | 1/1 |
| pdf_multi_invoice | 2 | 7 | 3.54 | 4.19 | 1.13 | 1.38 | 59.31 | 7/7 |
| scanned_pdf | 8 | 9 | 4.68 | 11.29 | 3.44 | 11.29 | 10.46 | 8/8 |
| scanned_pdf_multi_invoice | 1 | 2 | 4.89 | 4.89 | 2.45 | 2.45 | 24.52 | 2/2 |
| xls_ledger | 1 | 1 | 0.30 | 0.30 | 0.30 | 0.30 | 202.70 | 6/6 |
| xlsx_invoice_layout | 2 | 2 | 40.64 | 41.05 | 40.64 | 41.05 | 1.48 | 2/2 |
| xlsx_multisheet_register | 1 | 3 | 2.30 | 2.30 | 0.77 | 0.77 | 78.23 | 10/10 |
| xlsx_register | 1 | 1 | 0.80 | 0.80 | 0.80 | 0.80 | 74.72 | 5/5 |

## 5. LLM usage

Not reported by `/api/v1/stats`.
