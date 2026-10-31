"""End-to-end pipeline through the REST API with eager Celery and FakeLLM (SPEC 6, 7, 9, 10; PLAN I4-I20).

Each upload runs the whole pipeline inside the request, because CELERY_TASK_ALWAYS_EAGER=true.
"""

import uuid
from decimal import Decimal

from conftest import SYN

from app.models import Document, DocumentPage, Invoice, ValidationIssue


def _upload(client, *rel_paths):
    files = [
        ("files", (SYN.joinpath(p).name, SYN.joinpath(p).read_bytes(), "application/octet-stream")) for p in rel_paths
    ]
    response = client.post("/api/v1/documents", files=files)
    assert response.status_code == 202, response.text
    return response.json()


def _doc_id(client, rel_path):
    body = _upload(client, rel_path)
    return body["documents"][0]["id"]


def _status(client, doc_id):
    return client.get(f"/api/v1/documents/{doc_id}/status").json()


def _invoices(client, doc_id):
    return client.get(f"/api/v1/documents/{doc_id}").json()["invoices"]


def _issue_codes(client, invoice_id):
    return [i["code"] for i in client.get(f"/api/v1/invoices/{invoice_id}").json()["issues"]]


def test_i4_spreadsheet_register_is_processed_end_to_end(client, db, fake_llm):
    doc_id = _doc_id(client, "spreadsheets/ap_register_2025.xlsx")
    status = _status(client, doc_id)
    assert status["status"] in ("completed", "needs_review")
    assert len(_invoices(client, doc_id)) == 10
    events = client.get(f"/api/v1/documents/{doc_id}/events").json()
    stages = {e["stage"] for e in events if e["event"] == "stage_completed"}
    assert {"parsing", "validating", "indexing"} <= stages
    assert fake_llm.calls == []  # table mode needs no LLM


def test_i5_status_reports_progress_100_and_no_stage_after_completion(client, fake_llm):
    doc_id = _doc_id(client, "digital_pdf/digital_00.pdf")
    status = _status(client, doc_id)
    assert status["progress"] == 100
    assert status["stage"] is None


def test_i6_broken_pdf_fails_cleanly_and_api_stays_healthy(client):
    doc_id = _doc_id(client, "corrupted/broken_body.pdf")
    status = _status(client, doc_id)
    assert status["status"] == "failed"
    assert status["error_code"] == "CORRUPTED_FILE"
    assert client.get("/api/v1/health").status_code == 200


def test_i7_llm_outage_fails_then_reprocess_extracts_again(client, db, fake_llm):
    from app.errors import ProcessingError

    working_answers = fake_llm.responses

    def unavailable(purpose, system, user):
        raise ProcessingError("LLM_UNAVAILABLE", "provider down", retryable=True)

    fake_llm.responses = unavailable
    doc_id = _doc_id(client, "digital_pdf/digital_00.pdf")
    status = _status(client, doc_id)
    assert status["status"] == "failed"
    assert status["error_code"] == "LLM_UNAVAILABLE"
    page_rows_before = db.query(DocumentPage).filter(DocumentPage.document_id == uuid.UUID(doc_id)).count()

    fake_llm.responses = working_answers
    retry = client.post("/api/v1/documents/reprocess-failed", json={"error_code": "LLM_UNAVAILABLE"})
    assert retry.status_code == 202
    assert retry.json()["requeued"] == 1
    assert _status(client, doc_id)["status"] == "completed"
    events = client.get(f"/api/v1/documents/{doc_id}/events").json()
    requested = [e for e in events if e["event"] == "reprocess_requested"]
    assert requested[-1]["data"]["from_stage"] == "extract"
    assert db.query(DocumentPage).filter(DocumentPage.document_id == uuid.UUID(doc_id)).count() == page_rows_before


def test_i8_reprocess_while_processing_returns_409(client, db):
    doc_id = _doc_id(client, "digital_pdf/digital_00.pdf")
    doc = db.get(Document, uuid.UUID(doc_id))
    doc.status = "processing"
    db.commit()
    response = client.post(f"/api/v1/documents/{doc_id}/reprocess", json={"from_stage": "extract"})
    assert response.status_code == 409


def test_i9_total_mismatch_needs_review(client, fake_llm):
    doc_id = _doc_id(client, "digital_pdf/digital_02.pdf")
    detail = client.get(f"/api/v1/documents/{doc_id}").json()
    assert detail["status"] == "needs_review"
    invoice_id = detail["invoices"][0]["id"]
    assert "TOTAL_MISMATCH" in _issue_codes(client, invoice_id)


def test_i10_correction_clears_the_issue_and_completes_the_document(client, fake_llm, manifest):
    doc_id = _doc_id(client, "digital_pdf/digital_02.pdf")
    invoice_id = client.get(f"/api/v1/documents/{doc_id}").json()["invoices"][0]["id"]
    gt = manifest["syn-digital_02"]["invoices"][0]
    correct_total = f"{Decimal(gt['subtotal']) + Decimal(gt['tax']):.2f}"  # the printed total is the injected error
    response = client.patch(
        f"/api/v1/invoices/{invoice_id}", json={"reviewer": "Ayon", "note": "fixed", "fields": {"total": correct_total}}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert "TOTAL_MISMATCH" not in [i["code"] for i in body["issues"]]
    assert body["corrections"][-1]["field"] == "total"
    assert client.get(f"/api/v1/documents/{doc_id}").json()["status"] == "completed"


def test_i11_invalid_amount_is_rejected(client, fake_llm):
    doc_id = _doc_id(client, "digital_pdf/digital_02.pdf")
    invoice_id = client.get(f"/api/v1/documents/{doc_id}").json()["invoices"][0]["id"]
    response = client.patch(f"/api/v1/invoices/{invoice_id}", json={"reviewer": "Ayon", "fields": {"total": "abc"}})
    assert response.status_code == 422


def test_i12_approve_sets_status_and_records_an_event(client, fake_llm):
    doc_id = _doc_id(client, "digital_pdf/digital_02.pdf")
    invoice_id = client.get(f"/api/v1/documents/{doc_id}").json()["invoices"][0]["id"]
    response = client.post(f"/api/v1/invoices/{invoice_id}/approve", json={"reviewer": "Ayon"})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    events = client.get(f"/api/v1/documents/{doc_id}/events").json()
    assert any(e["event"] == "approved" for e in events)


def test_i13_duplicate_across_pdfs_is_flagged_on_the_later_copy(client, fake_llm):
    _doc_id(client, "digital_pdf/digital_03.pdf")
    scanned_id = _doc_id(client, "scanned_pdf/scanned_00.pdf")
    invoice_id = _invoices(client, scanned_id)[0]["id"]
    assert "DUPLICATE_INVOICE" in _issue_codes(client, invoice_id)


def test_i15_invoice_filters(client, fake_llm):
    _doc_id(client, "digital_pdf/digital_02.pdf")
    _doc_id(client, "digital_pdf/digital_00.pdf")
    everything = client.get("/api/v1/invoices").json()
    assert everything["total"] >= 2
    assert client.get("/api/v1/invoices", params={"status": "needs_review"}).json()["total"] >= 1
    assert client.get("/api/v1/invoices", params={"currency": "usd"}).json()["total"] >= 1
    assert client.get("/api/v1/invoices", params={"has_issues": "true"}).json()["total"] >= 1
    assert client.get("/api/v1/invoices", params={"total_min": "9999999999"}).json()["total"] == 0
    assert client.get("/api/v1/invoices", params={"date_from": "2100-01-01"}).json()["total"] == 0


def test_i16_keyword_search_finds_an_invoice_number_fragment(client, db, fake_llm):
    _doc_id(client, "digital_pdf/digital_00.pdf")
    number = db.query(Invoice.invoice_number).first()[0]
    fragment = number[:-2]
    hits = client.get("/api/v1/search", params={"q": fragment, "mode": "keyword"}).json()
    assert any(h["invoice_number"] == number for h in hits["items"])


def test_i18_hybrid_search_paginates_and_reports_matched_by(client, db, fake_llm):
    _doc_id(client, "digital_pdf/digital_00.pdf")
    number = db.query(Invoice.invoice_number).first()[0]
    body = client.get("/api/v1/search", params={"q": number, "mode": "hybrid", "page_size": 1}).json()
    assert body["total"] >= 1
    assert body["items"][0]["invoice_number"] == number
    assert "keyword" in body["items"][0]["matched_by"]
    page_two = client.get("/api/v1/search", params={"q": number, "mode": "hybrid", "page": 2, "page_size": 1})
    assert page_two.json()["page"] == 2


def test_i19_page_image_is_png_for_pdf_and_404_for_csv(client, fake_llm):
    doc_id = _doc_id(client, "digital_pdf/digital_00.pdf")
    image = client.get(f"/api/v1/documents/{doc_id}/pages/1/image", params={"dpi": 60})
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content[:8] == b"\x89PNG\r\n\x1a\n"
    csv_id = _doc_id(client, "spreadsheets/erp_export_eu.csv")
    assert client.get(f"/api/v1/documents/{csv_id}/pages/1/image").status_code == 404


def test_i20_stats_match_the_database(client, db, fake_llm):
    _doc_id(client, "digital_pdf/digital_02.pdf")
    stats = client.get("/api/v1/stats").json()
    assert stats["invoices"]["total"] == db.query(Invoice).count()
    assert stats["invoices"]["needs_review"] == db.query(Invoice).filter_by(status="needs_review").count()
    assert stats["documents"]["total"] == db.query(Document).count()
    assert sum(i["count"] for i in stats["top_issue_codes"]) == db.query(ValidationIssue).count()
