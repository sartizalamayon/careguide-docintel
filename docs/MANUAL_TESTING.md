# Manual testing guide

Every file below is in the repo under `datasets/eval/synthetic/`. Upload them through the Documents page or the Dashboard drop zone, then compare the result with the expected outcome.

Expected outcomes come from `datasets/eval/manifest_synthetic.jsonl`, the same ground truth the automated evaluation uses.

Path on the Mac clone: `~/docintel-run/repo/datasets/eval/synthetic/`

## digital_pdf (20)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/digital_pdf/digital_00.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_01.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_02.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_03.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_04.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_05.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_06.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_07.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_08.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_09.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_10.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_11.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_12.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_13.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_14.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_15.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_16.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_17.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_18.pdf` | success | - | 1 |
| `synthetic/digital_pdf/digital_19.pdf` | success | - | 1 |

## digital_pdf_multipage (4)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/digital_pdf/multipage_00.pdf` | success | - | 1 |
| `synthetic/digital_pdf/multipage_01.pdf` | success | - | 1 |
| `synthetic/digital_pdf/multipage_02.pdf` | success | - | 1 |
| `synthetic/digital_pdf/multipage_03.pdf` | success | - | 1 |

## scanned_pdf (8)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/scanned_pdf/scanned_00.pdf` | success | - | 1 |
| `synthetic/scanned_pdf/scanned_01.pdf` | success | - | 1 |
| `synthetic/scanned_pdf/scanned_02.pdf` | success | - | 1 |
| `synthetic/scanned_pdf/scanned_03.pdf` | success | - | 1 |
| `synthetic/scanned_pdf/scanned_04.pdf` | success | - | 1 |
| `synthetic/scanned_pdf/scanned_05.pdf` | success | - | 1 |
| `synthetic/scanned_pdf/scanned_06.pdf` | success | - | 1 |
| `synthetic/scanned_pdf/scanned_07.pdf` | success | - | 1 |

## image_clean (4)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/images/clean_00.png` | success | - | 1 |
| `synthetic/images/clean_01.png` | success | - | 1 |
| `synthetic/images/clean_02.png` | success | - | 1 |
| `synthetic/images/clean_03.png` | success | - | 1 |

## image_photo (4)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/images/photo_00.jpg` | success | - | 1 |
| `synthetic/images/photo_01.jpg` | success | - | 1 |
| `synthetic/images/photo_02.jpg` | success | - | 1 |
| `synthetic/images/photo_03.jpg` | success | - | 1 |

## image_tiff (2)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/images/scan_00.tiff` | success | - | 1 |
| `synthetic/images/scan_01.tiff` | success | - | 1 |

## image_tiff_multipage (1)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/images/scan_02.tiff` | success | - | 1 |

## xlsx_multisheet_register (1)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/spreadsheets/ap_register_2025.xlsx` | success | - | 10 |

## xls_ledger (1)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/spreadsheets/supplier_ledger.xls` | success | - | 6 |

## csv_semicolon_eu (1)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/spreadsheets/erp_export_eu.csv` | success | - | 6 |

## xlsx_invoice_layout (2)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/spreadsheets/invoice_layout_00.xlsx` | success | - | 1 |
| `synthetic/spreadsheets/invoice_layout_01.xlsx` | success | - | 1 |

## pdf_multi_invoice (2)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/crosscheck/batch_5_invoices.pdf` | success | - | 5 |
| `synthetic/crosscheck/pdfpair_original.pdf` | success | - | 2 |

## xlsx_register (1)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/crosscheck/erp_export.xlsx` | success | - | 5 |

## scanned_pdf_multi_invoice (1)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/crosscheck/pdfpair_received_scan.pdf` | success | - | 2 |

## corrupted (8)

| File | Expected outcome | Expected error | Invoices expected |
|---|---|---|---|
| `synthetic/corrupted/zero_bytes.pdf` | rejected | EMPTY_FILE | 0 |
| `synthetic/corrupted/not_really_a.pdf` | rejected | FILE_TYPE_MISMATCH | 0 |
| `synthetic/corrupted/unsupported.docx` | rejected | UNSUPPORTED_FILE_TYPE | 0 |
| `synthetic/corrupted/broken_body.pdf` | failed | CORRUPTED_FILE | 0 |
| `synthetic/corrupted/password_protected.pdf` | failed | ENCRYPTED_FILE | 0 |
| `synthetic/corrupted/corrupt_workbook.xlsx` | failed | CORRUPTED_FILE | 0 |
| `synthetic/corrupted/blank_page.png` | failed | NO_CONTENT | 0 |
| `synthetic/corrupted/header_only.csv` | failed | NO_CONTENT | 0 |

## Edge cases to try by hand

- Upload the same file twice. The second upload should show `duplicate_of` on the Documents page.
- Drop 3 files at once, and mix good and bad files in one batch. Each file should finish independently.
- Open a processing document and watch the progress bar move without refreshing.
- Reprocess a failed document with the Reprocess button. It should go back to queued.
- Search for an invoice number, a supplier name, and a word from the invoice body in each of the three search modes.
- Edit a value on an invoice in the Review queue, save it, and check that the correction is logged.
- Approve an invoice that still has an error. It should be allowed, and the issue should stay visible.
