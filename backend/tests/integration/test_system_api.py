"""Health and stats endpoints (SPEC §10)."""


def test_health_reports_db_and_redis(client):
    body = client.get("/api/v1/health").json()
    assert body["db"] is True
    assert body["redis"] is True
    assert body["status"] == "ok"


def test_health_does_not_need_an_api_key(client):
    from fastapi.testclient import TestClient

    anonymous = TestClient(client.app)
    assert anonymous.get("/api/v1/health").status_code == 200


def test_stats_on_an_empty_database(client):
    body = client.get("/api/v1/stats").json()
    assert body["documents"]["total"] == 0
    assert body["invoices"]["total"] == 0
    assert body["top_issue_codes"] == []
