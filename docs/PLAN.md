# Implementation Plan (for the coding agent)

Work through the milestones in order. Each one ends with green tests and one commit (see AGENTS.md for the commit rules). Do not start a milestone until the previous one meets its acceptance criteria. The deadline is 5 days, and the time boxes below add up to about 3.5 days of work, which leaves room for fixes.

| # | Milestone | Time box |
|---|---|---|
| M1 | Data layer + upload API | 0.5 d |
| M2 | Parsers (PDF, OCR, images, spreadsheets, layout) | 0.75 d |
| M3 | Background processing, status, events, failures, reprocess | 0.5 d |
| M4 | LLM extraction, grounding, segmentation | 0.5 d |
| M5 | Validation, corrections, approve, cross-check | 0.5 d |
| M6 | Search (keyword, semantic, hybrid) | 0.25 d |
| M7 | Frontend | 0.75 d |
| M8 | Evaluation run + docs | 0.25 d |

---

## M1 — Data layer + upload API
Tasks
1. Migration `0001_initial.py` already exists (it applies `docs/schema.sql`). Nothing to do except confirm `make up` runs it.
2. `app/models.py`: ORM classes for every table (`Document`, `DocumentPage`, `Invoice`, `LineItem`, `ValidationIssue`, `Correction`, `ProcessingEvent`, `CrossCheck`, `LlmCall`) with relationships `Document.pages/invoices/events` and `Invoice.line_items/issues/corrections` (cascade delete-orphan).
3. `app/security.py` (`require_api_key` dependency), `app/errors.py` (error-code enum + `ProcessingError(code, message, retryable=False)` + FastAPI exception handlers producing the §10 error shape).
4. `app/pipeline/filetypes.py` (`sniff`, `canonical_ext`, `family_of`) and `app/storage.py` (streaming save with sha256, `open_path(doc)`).
5. `app/api/documents.py`: `POST /documents`, `GET /documents`, `GET /documents/{id}`, `/status`, `/file`, `/events`. For now enqueueing calls `process_document.delay` (a stub task that does nothing yet).
6. `app/api/system.py`: `/health` (already exists, extend with worker ping) and `/stats`.

Acceptance
- `make up && make migrate` works, and `curl localhost:8000/api/v1/health` shows db and redis true.
- Uploading `datasets/eval/synthetic/digital_pdf/digital_00.pdf` + `corrupted/unsupported.docx` + `corrupted/not_really_a.pdf` + `corrupted/zero_bytes.pdf` returns 202 with 1 document and 3 rejections, carrying the codes UNSUPPORTED_FILE_TYPE, FILE_TYPE_MISMATCH and EMPTY_FILE.
- Requests without `X-API-Key` → 401.

## M2 — Parsers
Tasks: `layout.py`, `pdf.py`, `ocr.py`, `images.py`, `spreadsheets.py` (table + layout mode; the LLM column mapper is called through `llm.get_llm()`, but implement the mapper call in M4), `normalize.py` (`parse_amount`, `parse_date`, `amount_variants`, `date_variants`, `norm_invoice_number`, `norm_supplier`).

Acceptance
- Unit tests U1–U16 pass.
- `digital_00.pdf` text contains its invoice number and total. `scanned_01.pdf` OCR mean confidence is > 70. `images/photo_03.jpg` triggers pass B. `scan_02.tiff` yields 2 pages.

## M3 — Background processing
Tasks: `orchestrator.py` + Celery task (SPEC §6.10) with stages, progress, events, retry policy and error handling. Implement the reprocess endpoints. Spreadsheet table mode produces invoices end-to-end now (no LLM needed). Segmentation (`segment.py`) can be written here too.

Acceptance
- Uploading `spreadsheets/ap_register_2025.xlsx` ends `completed` or `needs_review` with 10 invoices.
- `corrupted/broken_body.pdf` → `failed/CORRUPTED_FILE`. `password_protected.pdf` → `failed/ENCRYPTED_FILE`. `blank_page.png` → `failed/NO_CONTENT`.
- `/events` shows the stage timings.
- `POST /documents/{id}/reprocess` on a failed doc runs again and `attempts` increments.
- Integration tests I1–I8 pass.

## M4 — LLM extraction
Tasks: `llm.py`, `prompts.py` (copy verbatim from SPEC §6.7), `extract.py` (grounding), the spreadsheet column mapper and layout mode, and wiring EXTRACT into the orchestrator.

Acceptance
- With a real key: `digital_00.pdf`, `images/clean_00.png`, `katanaml/test_00.jpg` and `spreadsheets/invoice_layout_00.xlsx` extract the correct totals.
- `crosscheck/batch_5_invoices.pdf` yields 5 invoices with the right page ranges.
- `digital_pdf/multipage_00.pdf` (2 pages) yields 1 invoice with all its line items.
- Unit tests U17–U26 pass with `FakeLLM`.
- A second processing of the same file makes 0 new LLM API calls (cache).

## M5 — Validation, corrections, cross-check
Tasks: `validate.py` (SPEC §7), `PATCH /invoices/{id}`, `POST /invoices/{id}/approve`, `GET /invoices`, `GET /invoices/{id}`, `crosscheck.py` + endpoints.

Acceptance
- Unit tests U27–U40 and integration tests I9–I14 pass.
- `digital_02.pdf` → TOTAL_MISMATCH.
- Uploading `digital_03.pdf` and then `scanned_00.pdf` flags DUPLICATE_INVOICE on the scanned one.
- Correcting the total of a TOTAL_MISMATCH invoice to the right value → the invoice becomes `ok` and a corrections row exists.
- Cross-check `batch_5_invoices.pdf` vs `erp_export.xlsx` returns exactly the expected sets from `synthetic_meta.json`.

## M6 — Search
Tasks: `embeddings.py` (download the model at image build — the Dockerfile already does this), `search_tsv` + embedding on save, `GET /search` with the 3 modes and the filters.

Acceptance
- Integration tests I15–I18 pass.
- The query "wheelchair rental" in semantic mode returns invoices containing wheelchair items. "CG-10" in keyword mode returns invoices whose number starts with CG-10.

## M7 — Frontend
Build the 7 pages in SPEC §11 on top of the scaffold. Add shadcn components with `npx shadcn@latest add <name>` (the config is already in `components.json`).

Acceptance (manual, record it in the walkthrough)
- Upload 10 mixed files at once and watch their progress update live.
- A failed doc shows its reason and the Reprocess button works.
- Open a needs_review invoice, fix the total, save, and the issue disappears. Approve it.
- Search in all three modes with filters.
- The compare page shows mismatches.
- `npm run build` and `npm run lint` pass with zero errors.

## M8 — Evaluation + docs
Tasks: `eval/run_eval.py` + `eval/metrics.py` (SPEC §14) and the unit tests U41–U43 for the metric functions. Run on the synthetic + katanaml manifests, then the perf manifest. Commit the `eval/results/<run>/` outputs and fill `docs/EVALUATION.md` and the README "Results" section from `metrics.json`.

Acceptance
- `eval/results/<run>/metrics.json`, `report.md` and `per_document.csv` exist.
- EVALUATION.md has no TODO left.
- `pytest` output saved to `eval/results/test-report.txt`.

---

## Test plan

Fixtures: use files from `datasets/eval/synthetic/` directly (they are committed). `FakeLLM(responses: dict[str, dict] | callable)` returns canned extraction JSON. A helper `fake_from_gt(manifest_row)` builds a perfect response from ground truth so that pipeline tests are deterministic.

### Unit tests (`tests/unit/`)
| ID | Module | Case |
|---|---|---|
| U1 | filetypes | each allowed type with the correct magic → ok; `.pdf` with PNG bytes → FILE_TYPE_MISMATCH; `.docx` → UNSUPPORTED_FILE_TYPE; csv with a NUL byte → FILE_TYPE_MISMATCH |
| U2 | layout | two words on the same line at x=0 and x=300 stay on one line and are ≥ 30 spaces apart |
| U3 | layout | words with slightly different y (±2 px) group into one line; a 40 px gap starts a new line |
| U4 | pdf | `digital_00.pdf` → 1 page, method digital, text contains the GT invoice number |
| U5 | pdf | `scanned_01.pdf` → every page method ocr |
| U6 | pdf | `broken_body.pdf` → CORRUPTED_FILE; `password_protected.pdf` → ENCRYPTED_FILE |
| U7 | ocr | `images/clean_00.png` mean_conf > 80, contains the GT total (any amount variant) |
| U8 | ocr | `images/photo_03.jpg` → pass B chosen, mean_conf > 70 |
| U9 | ocr | `corrupted/blank_page.png` → word_count < 3 |
| U10 | images | `scan_02.tiff` → 2 frames; a truncated PNG → CORRUPTED_FILE |
| U11 | spreadsheets | `ap_register_2025.xlsx` → 10 invoices, title rows skipped, the Notes sheet ignored, line items grouped |
| U12 | spreadsheets | `supplier_ledger.xls` → 6 invoices from the header synonyms Bill No/Net/VAT/Gross, no line items |
| U13 | spreadsheets | `erp_export_eu.csv` → `;` delimiter, comma decimals parsed, BOM stripped; the invoice with the typo total has total None + invalid_number flag |
| U14 | spreadsheets | `invoice_layout_00.xlsx` → layout mode (segment text contains the invoice number) |
| U15 | spreadsheets | `corrupt_workbook.xlsx` → CORRUPTED_FILE; `header_only.csv` → NO_CONTENT |
| U16 | normalize | parse_amount: `"$ 1 234,56"`→1234.56, `"1.234,56"`→1234.56, `"1,234.56"`→1234.56, `"(50.00)"`→-50.00, `"12O.50"`→None; amount_variants(1234.5) contains "1,234.50" and "1.234,50"; norm_supplier("Acme, Inc.")=="acme" |
| U17 | segment | 5-invoice PDF texts → 5 segments, page ranges 1-1..5-5 |
| U18 | segment | 2-page invoice ("Page 1 of 2", "Page 2 of 2", same number) → 1 segment |
| U19 | segment | 12 pages with no cues → 12 segments; 3 pages with no cues → 1 segment |
| U20 | segment | the captured number must contain a digit ("Invoice Date" is not a number) |
| U21 | extract | FakeLLM returns the GT → all fields grounded, confidence copied |
| U22 | extract | FakeLLM returns a total not in the text → grounded false (and validation later gives UNGROUNDED_VALUE) |
| U23 | extract | FakeLLM returns `is_invoice=false` → None |
| U24 | llm | the first response is invalid JSON → the repair call is made → success; two invalid → LLM_BAD_OUTPUT |
| U25 | llm | RateLimitError ×2 then success → returns (tenacity wait patched to 0) |
| U26 | llm | the same input twice → the second served from the llm_calls cache (FakeLLM called once) |
| U27 | validate | a clean invoice → no issues, status ok |
| U28 | validate | missing invoice_number → MISSING_FIELD error; missing customer → warning only, status ok |
| U29 | validate | subtotal + tax ≠ total → TOTAL_MISMATCH |
| U30 | validate | Σ lines ≠ subtotal → SUBTOTAL_MISMATCH; a 0.01 rounding difference → no issue |
| U31 | validate | qty × price ≠ amount → LINE_AMOUNT_MISMATCH with position |
| U32 | validate | future date → INVALID_DATE; total 0 → INVALID_AMOUNT |
| U33 | validate | invalid_number flag → INVALID_NUMBER and NOT MISSING_FIELD |
| U34 | validate | no tax line and total == subtotal → only MISSING_FIELD(tax) warning |
| U35 | validate | duplicate in the same family → DUPLICATE_INVOICE on the later invoice only |
| U36 | validate | the same number in a pdf and an xlsx → no duplicate |
| U37 | validate | ungrounded field → UNGROUNDED_VALUE; manual source → skipped |
| U38 | validate | confidence 0.4 on total → LOW_CONFIDENCE and status needs_review |
| U39 | crosscheck | matched / mismatched(total) / mismatched(date) / only_in_a / only_in_b exactly as in synthetic_meta |
| U40 | crosscheck | null fields are skipped, not reported as mismatches |
| U41 | eval.metrics | partial-match rule, amount tolerance, null-vs-null correct, hallucination counted |
| U42 | eval.metrics | line-item greedy matching P/R/F1 on a hand-made example |
| U43 | eval.metrics | issue precision/recall on a hand-made example |

### Integration tests (`tests/integration/`, real Postgres + Redis, eager Celery, FakeLLM)
| ID | Case |
|---|---|
| I1 | upload 3 valid + 3 invalid files in one request → 3 docs + 3 rejections with the right codes |
| I2 | upload without an API key → 401; a wrong key → 401 |
| I3 | upload > MAX_FILE_MB (set to 1 in the test) → FILE_TOO_LARGE rejection |
| I4 | xlsx register end-to-end → status terminal, invoices persisted, events recorded with every stage |
| I5 | status endpoint returns progress 100 and stage null after completion |
| I6 | broken PDF → failed/CORRUPTED_FILE, the API still healthy |
| I7 | FakeLLM raises an unavailable error → after retries failed/LLM_UNAVAILABLE; `reprocess-failed` with a working FakeLLM → completed, `from_stage=extract` (no new page rows) |
| I8 | reprocess while processing → 409 |
| I9 | `digital_02.pdf` (FakeLLM from GT) → needs_review with TOTAL_MISMATCH; the document is needs_review |
| I10 | PATCH a correction → corrections row, issue gone, invoice ok, document completed |
| I11 | PATCH with an invalid amount "abc" → 422 |
| I12 | approve → status approved, an event exists |
| I13 | duplicate: digital_03 then scanned_00 → DUPLICATE_INVOICE on the second |
| I14 | cross-check endpoint: batch_5 vs erp_export → expected sets; a non-terminal doc → 409 |
| I15 | GET /invoices filters: status, currency, date range, total range, has_issues |
| I16 | search keyword: an invoice number fragment finds the invoice |
| I17 | search semantic: an item description paraphrase returns the right invoice in the top 3 |
| I18 | search hybrid: matched_by contains both when both match; pagination works |
| I19 | GET /documents/{id}/pages/1/image returns a PNG for pdf and tiff, 404 for csv |
| I20 | GET /stats counts match the DB |

## Done = all of
- [ ] `make test` green, coverage ≥ 80 % on `app/pipeline`
- [ ] `docker compose up` from a clean clone + `.env` works on the first try (follow README only)
- [ ] All 7 UI pages work against real data
- [ ] Evaluation run committed, EVALUATION.md + README results filled from `metrics.json`
- [ ] No secrets in git (`git grep -i "api_key=" -- ':!*.example'` returns nothing)
