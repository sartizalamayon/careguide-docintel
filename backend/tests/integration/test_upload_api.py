"""M1 acceptance and integration cases I1-I3 (SPEC §6.1, §10, §12)."""

from conftest import SYN

from app.config import get_settings
from app.models import Document, ProcessingEvent


def _file(path):
    return ("files", (path.name, path.read_bytes(), "application/octet-stream"))


def test_mixed_upload_accepts_valid_and_rejects_invalid(client, db):
    """I1 and the M1 acceptance check: one valid file, three rejected files with the right codes."""
    files = [
        _file(SYN / "digital_pdf" / "digital_00.pdf"),
        ("files", ("unsupported.docx", b"PK\x03\x04 word", "application/octet-stream")),
        ("files", ("not_really_a.pdf", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "application/pdf")),
        ("files", ("zero_bytes.pdf", b"", "application/pdf")),
    ]
    response = client.post("/api/v1/documents", files=files)
    assert response.status_code == 202
    body = response.json()
    assert len(body["documents"]) == 1
    assert body["documents"][0]["status"] == "queued"
    codes = sorted(r["code"] for r in body["rejected"])
    assert codes == ["EMPTY_FILE", "FILE_TYPE_MISMATCH", "UNSUPPORTED_FILE_TYPE"]
    assert db.query(Document).count() == 1


def test_stored_file_has_server_generated_name_and_events(client, db):
    response = client.post("/api/v1/documents", files=[_file(SYN / "digital_pdf" / "digital_00.pdf")])
    doc_id = response.json()["documents"][0]["id"]
    doc = db.get(Document, __import__("uuid").UUID(doc_id))
    assert doc.storage_path.endswith(f"{doc_id}.pdf")
    assert doc.family == "document"
    assert len(doc.sha256) == 64
    events = [e.event for e in db.query(ProcessingEvent).filter_by(document_id=doc.id).order_by(ProcessingEvent.id)]
    assert events[:2] == ["uploaded", "queued"]


def test_identical_bytes_set_duplicate_of(client):
    path = SYN / "digital_pdf" / "digital_03.pdf"
    first = client.post("/api/v1/documents", files=[_file(path)]).json()["documents"][0]
    second = client.post("/api/v1/documents", files=[_file(path)]).json()["documents"][0]
    assert second["duplicate_of"] == first["id"]


def test_requests_without_api_key_are_rejected(client):
    """I2: no key and a wrong key both get 401 with the error shape."""
    anonymous = client.__class__(client.app)  # fresh client without default headers
    response = anonymous.post("/api/v1/documents", files=[_file(SYN / "digital_pdf" / "digital_00.pdf")])
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    wrong = client.post(
        "/api/v1/documents",
        files=[_file(SYN / "digital_pdf" / "digital_00.pdf")],
        headers={"X-API-Key": "not-the-key-0000000000"},
    )
    assert wrong.status_code == 401


def test_file_over_the_size_limit_is_rejected(client, monkeypatch):
    """I3: a file above MAX_FILE_MB is rejected with FILE_TOO_LARGE and not stored."""
    monkeypatch.setattr(get_settings(), "MAX_FILE_MB", 1)
    big = ("files", ("big.csv", b"Invoice,Total\n" + b"AP-1,1.00\n" * 200_000, "text/csv"))
    response = client.post("/api/v1/documents", files=[big])
    body = response.json()
    assert response.status_code == 422
    assert body["rejected"][0]["code"] == "FILE_TOO_LARGE"


def test_list_detail_status_and_file_endpoints(client):
    path = SYN / "digital_pdf" / "digital_00.pdf"
    doc_id = client.post("/api/v1/documents", files=[_file(path)]).json()["documents"][0]["id"]
    listing = client.get("/api/v1/documents").json()
    assert listing["total"] == 1
    assert client.get(f"/api/v1/documents/{doc_id}").json()["filename"] == "digital_00.pdf"
    status = client.get(f"/api/v1/documents/{doc_id}/status").json()
    assert status["id"] == doc_id
    file_response = client.get(f"/api/v1/documents/{doc_id}/file")
    assert file_response.status_code == 200
    assert file_response.content == path.read_bytes()
    assert "inline" in file_response.headers["content-disposition"]
    assert client.get(f"/api/v1/documents/{doc_id}/events").status_code == 200
    assert client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000").status_code == 404
