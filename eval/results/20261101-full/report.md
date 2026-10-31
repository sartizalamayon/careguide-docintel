# Evaluation run

Started 2026-10-31T20:08:00+00:00, finished 2026-10-31T20:14:13+00:00, API http://localhost:8000. 160 manifest documents, 0 not uploaded.

## 1. Extraction accuracy

### Field accuracy

| Field | all | katanaml | katanaml/image_clean | katanaml/image_poor_quality | synthetic |
|---|---|---|---|---|---|
| invoice_number | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| invoice_date | 78.5% | 61.0% | 60.8% | 61.5% | 100.0% |
| supplier_name | 99.4% | 99.0% | 98.6% | 100.0% | 100.0% |
| customer_name | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| currency | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| subtotal | 99.4% | 100.0% | 100.0% | 100.0% | 98.8% |
| tax | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| total | 99.4% | 100.0% | 100.0% | 100.0% | 98.8% |
| micro average | 97.1% | 95.0% | 94.9% | 95.2% | 99.7% |

### By group

| Group | Docs | Field acc. | Exact match | Line P | Line R | Line F1 | Hallucination | Invoices matched |
|---|---|---|---|---|---|---|---|---|
| all | 152 | 97.1% | 73.0% | 82.1% | 82.1% | 82.1% | 0.0% | 181/181 |
| katanaml | 100 | 95.0% | 60.0% | 61.1% | 61.1% | 61.1% | n/a | 100/100 |
| katanaml/image_clean | 74 | 94.9% | 59.5% | 64.2% | 64.2% | 64.2% | n/a | 74/74 |
| katanaml/image_poor_quality | 26 | 95.2% | 61.5% | 51.9% | 51.9% | 51.9% | n/a | 26/26 |
| synthetic | 52 | 99.7% | 98.1% | 99.6% | 99.6% | 99.6% | 0.0% | 81/81 |
| synthetic/csv_semicolon_eu | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 6/6 |
| synthetic/digital_pdf | 20 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 20/20 |
| synthetic/digital_pdf_multipage | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 4/4 |
| synthetic/image_clean | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | n/a | 4/4 |
| synthetic/image_photo | 4 | 93.8% | 75.0% | 100.0% | 100.0% | 100.0% | n/a | 4/4 |
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
| Arithmetic and field rules | 12.0% | 100.0% | TP 11, FP 81, FN 0 |
| Duplicate detection | 100.0% | 100.0% | 29/29 groups, 0 false flags |

| Cross-check pair | Kind | Result | Differences |
|---|---|---|---|
| syn-batch_5_invoices vs syn-erp_export | pdf_excel | pass |  |
| syn-pdfpair_original vs syn-pdfpair_received_scan | pdf_pdf | pass |  |

## 3. Robustness and operations

| Metric | Value |
|---|---|
| Valid documents | 152 |
| Completed / needs review / failed / rejected | 70 / 82 / 0 / 0 |
| Success rate | 100.0% |
| Failure rate | 0.0% |
| Document review rate | 53.9% |
| Invoices routed to review (with known fault) | 83 (50) |
| Graceful handling of invalid files | 8/8 |
| HTTP 5xx responses | 0 |
| Stuck documents | 0 |

## 4. Performance (processing time in seconds)

| Category | Docs | Pages | Doc p50 | Doc p95 | Page p50 | Page p95 | Pages/min | Invoices found/expected |
|---|---|---|---|---|---|---|---|---|
| all | 152 | 167 | 3.49 | 10.70 | 3.40 | 10.07 | 13.71 | 181/181 |
| csv_semicolon_eu | 1 | 1 | 1.32 | 1.32 | 1.32 | 1.32 | 45.32 | 6/6 |
| digital_pdf | 20 | 20 | 2.06 | 9.05 | 2.06 | 9.05 | 20.09 | 20/20 |
| digital_pdf_multipage | 4 | 9 | 13.19 | 15.07 | 5.47 | 7.49 | 11.47 | 4/4 |
| image_clean | 78 | 78 | 3.37 | 10.11 | 3.37 | 10.11 | 12.61 | 78/78 |
| image_photo | 4 | 4 | 5.71 | 6.02 | 5.71 | 6.02 | 11.75 | 4/4 |
| image_poor_quality | 26 | 26 | 3.79 | 10.46 | 3.79 | 10.46 | 11.54 | 26/26 |
| image_tiff | 2 | 2 | 3.27 | 3.34 | 3.27 | 3.34 | 18.35 | 2/2 |
| image_tiff_multipage | 1 | 2 | 6.92 | 6.92 | 3.46 | 3.46 | 17.34 | 1/1 |
| pdf_multi_invoice | 2 | 7 | 7.77 | 10.61 | 2.25 | 2.30 | 27.04 | 7/7 |
| scanned_pdf | 8 | 9 | 3.81 | 5.46 | 3.72 | 4.99 | 16.47 | 8/8 |
| scanned_pdf_multi_invoice | 1 | 2 | 4.56 | 4.56 | 2.28 | 2.28 | 26.33 | 2/2 |
| xls_ledger | 1 | 1 | 0.49 | 0.49 | 0.49 | 0.49 | 122.95 | 6/6 |
| xlsx_invoice_layout | 2 | 2 | 13.06 | 15.99 | 13.06 | 15.99 | 4.60 | 2/2 |
| xlsx_multisheet_register | 1 | 3 | 2.19 | 2.19 | 0.73 | 0.73 | 82.19 | 10/10 |
| xlsx_register | 1 | 1 | 0.86 | 0.86 | 0.86 | 0.86 | 70.09 | 5/5 |

## 5. LLM usage

Not reported by `/api/v1/stats`.
