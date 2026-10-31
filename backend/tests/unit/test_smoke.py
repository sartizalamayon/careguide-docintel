"""Scaffold smoke test - keeps CI green until real tests exist. Safe to keep."""
from conftest import fake_from_gt, load_manifest


def test_app_has_health_route():
    from app.main import app

    assert any(getattr(r, "path", "") == "/api/v1/health" for r in app.routes)


def test_manifest_and_fake_llm_helper():
    m = load_manifest()
    row = m["syn-digital_00"]
    out = fake_from_gt(row["invoices"][0])
    assert out["is_invoice"] is True
    assert out["total"]["value"] == float(row["invoices"][0]["total"])
