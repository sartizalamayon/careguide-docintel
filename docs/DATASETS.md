# Evaluation Datasets

Two labelled sets are used together. One is public and realistic. The other is synthetic and covers every format and failure the brief names. Every file has ground truth (GT) for all 8 fields + line items.

| Set | Files | Invoices | Formats | Committed? | How to get it |
|---|---|---|---|---|---|
| Katana ML "Sparrow" invoices (public) | 100 (74 clean + 26 degraded) | 100 | JPG, PNG, TIFF | manifest yes, images no (46+44 MB) | `make data` → `python datasets/tools/fetch_katanaml.py` |
| Synthetic (this repo) | 60 | 81 | PDF (digital, scanned, multi-page, multi-invoice), PNG, JPG, TIFF (multi-page), XLSX (multi-sheet, layout), XLS, CSV, corrupted | yes (15 MB) | `python datasets/tools/generate_synthetic.py` (deterministic, seed 42) |
| Performance | 2 | ~450 | 1000-page digital PDF, 50-page scanned PDF | no | `python datasets/tools/generate_synthetic.py --perf` |

## 1. Katana ML invoices (public, MIT)

- Source: https://huggingface.co/datasets/katanaml-org/invoices-donut-data-v1 (revision `d2cde298…` pinned in the script). The original is Kozłowski & Weichbroth (2021), *Samples of electronic invoices*, Mendeley Data, doi:10.17632/tnj49gpmtz.2.
- Used: the `test` (26) and `validation` (50) splits. `train` (425) is not used, because nothing is trained. Two validation rows have malformed upstream annotations and are skipped → **74** clean images.
- Images: 2481×3508 JPEG (300 dpi A4), English, USD (`$`) amounts with comma decimals ("1 234,56"), 1–7 line items, seller/client side by side.
- **Degraded copies**: every 3rd image is also saved after downscaling to ~165 dpi, a ±2.5° skew, blur, noise and a contrast drop, as PNG or TIFF → **26** "poor quality" files.
- **Label audit**: every GT value was checked against the Tesseract text and the invoice arithmetic. **6 upstream label errors were found and corrected** in `fetch_katanaml.py:LABEL_FIXES`: a total typo `1579929.37` → `157929.37`, 5 missing line amounts or prices, and 3 missing currency labels (all invoices print `$`). After the fixes every GT row satisfies Σ lines = subtotal and subtotal + tax = total.
- GT mapping:

  | Katana field | Our field |
  |---|---|
  | `invoice_no` | `invoice_number` |
  | `invoice_date` (MM/DD/YYYY) | `invoice_date` (ISO) |
  | `seller` | `supplier_name` |
  | `client` | `customer_name` |
  | `total_net_worth` | `subtotal` |
  | `total_vat` | `tax` |
  | `total_gross_worth` | `total` |
  | items: `item_desc`, `item_qty`, `item_net_price`, `item_net_worth` | line items: `description`, `quantity`, `unit_price`, `amount` |

- Caveat: upstream `seller`/`client` contain name + address in one string. We extract the name only, so the eval uses a **partial match** for those two fields (`eval_hints`).

## 2. Synthetic set (generated)

`datasets/tools/generate_synthetic.py` renders invoices with ReportLab from random but realistic data. The data uses home-care and back-office items (caregiver hours, medical billing, gloves, HHA training seats…), 4 currencies (USD, EUR, GBP, BDT) with their number and date formats, 3 visual templates, label variants ("Invoice No:", "Bill No.:", "Invoice #"), and distractors (due date, PO number). GT is what is **printed**, so deliberate errors stay in the GT and are listed in `expected_issues`.

| Category | Files | What it tests |
|---|---|---|
| `digital_pdf` | 20 | text-layer PDFs, 3 templates, 6 with injected faults |
| `digital_pdf_multipage` | 4 | 22–60 line items over 2–3 pages, "Page x of y", continued headers |
| `scanned_pdf` | 8 | image-only PDFs (200 dpi, skew, blur, noise, JPEG); 1 duplicate of a digital invoice, 1 wrong total |
| `image_clean` | 4 PNG | 1 with a wrong line amount |
| `image_photo` | 4 JPG | phone-photo look (uneven light, rotation); 1 re-billed duplicate |
| `image_tiff` / `image_tiff_multipage` | 3 TIFF | incl. one 2-page TIFF |
| `xlsx_multisheet_register` | 1 (10 invoices) | 2 data sheets with title rows above the header + a notes sheet; line-item rows grouped by invoice no. |
| `xls_ledger` | 1 (6 invoices) | legacy .xls, header-only rows, different column names (Bill No, Net, VAT, Gross), BDT |
| `csv_semicolon_eu` | 1 (6 invoices) | `;` delimiter, comma decimals, UTF-8 BOM, one unreadable total ("12O,50" style typo) |
| `xlsx_invoice_layout` | 2 | an invoice laid out in cells (needs LLM layout mode) |
| `pdf_multi_invoice` | 2 | 5 invoices in one PDF (segmentation) and a 2-invoice PDF |
| `xlsx_register` / `scanned_pdf_multi_invoice` | 2 | the other side of the cross-check pairs |
| `corrupted` | 8 | empty, spoofed extension, unsupported type, broken PDF body, password-protected PDF, broken xlsx, blank page, header-only CSV |

Injected faults → expected validation codes: TOTAL_MISMATCH ×4, SUBTOTAL_MISMATCH ×1, LINE_AMOUNT_MISMATCH ×1, MISSING_FIELD (invoice_number, customer_name, tax) ×3, INVALID_DATE ×1, INVALID_NUMBER ×1, DUPLICATE_INVOICE groups ×3 (plus 26 Katana groups: each degraded copy duplicates its original, listed in `katanaml_meta.json`).

Cross-check pairs (`synthetic_meta.json`):
- **PDF ↔ Excel**: `batch_5_invoices.pdf` vs `erp_export.xlsx` → 2 matched, 2 mismatched (total +100.00; date +3 days), 1 only in the PDF, 1 only in the ERP export.
- **PDF ↔ PDF**: `pdfpair_original.pdf` vs `pdfpair_received_scan.pdf` (a scanned copy where invoice 2's tax was altered) → 1 matched, 1 mismatched (tax).

Ground truth verification: every GT amount, invoice number and supplier was confirmed to appear in the digital PDFs' text layer (0 mismatches). OCR on the scans and photos misses some values, which is intended. That is the difficulty the pipeline must handle.

Numeric dates with day ≤ 12 were avoided, so that dd/mm vs mm/dd ambiguity does not make the GT itself uncertain. The `INVALID_DATE` case is dated 2027, so it is "in the future" until 2027.

## 3. Manifest format (`manifest_*.jsonl`, one JSON per line)

```json
{
  "doc_id": "syn-digital_02",
  "path": "synthetic/digital_pdf/digital_02.pdf",          // relative to datasets/eval/
  "source": "synthetic" | "katanaml",
  "file_type": "pdf",
  "category": "digital_pdf",
  "expected_outcome": "success" | "rejected" | "failed",
  "expected_error": null | "CORRUPTED_FILE" | ...,
  "invoices": [{
     "invoice_number": "INV-1003", "invoice_date": "2025-06-18", "supplier_name": "…", "customer_name": "…",
     "currency": "USD", "subtotal": "1200.00", "tax": "120.00", "total": "1330.00",
     "line_items": [{"description": "…", "quantity": "2", "unit_price": "600.00", "amount": "1200.00"}]
  }],
  "expected_issues": [{"invoice_number": "INV-1003", "code": "TOTAL_MISMATCH", "field": null}],
  "eval_hints": {"supplier_name": "partial"}
}
```
Amounts are strings with 2 decimals, dates are ISO, and `null` means "not printed on the document" (the correct prediction is null).
