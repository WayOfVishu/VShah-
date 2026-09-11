"""The backend skeleton: it starts, it reports health, and it says "not yet"
properly instead of crashing."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_reports_the_patch():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["gameVersion"].count(".") == 1  # "16.18" -- client numbering, see config.py


def test_recommend_is_501_until_built():
    r = client.post("/api/recommend", json={"champion": "Ahri", "enemy": "Zed", "role": "MIDDLE"})
    assert r.status_code == 501
    assert "#REC-1" in r.json()["detail"]


def test_recommend_rejects_a_role_that_does_not_exist():
    r = client.post("/api/recommend", json={"champion": "Ahri", "enemy": "Zed", "role": "MID"})
    assert r.status_code == 422
