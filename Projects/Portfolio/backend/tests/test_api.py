"""API surface tests.

These cover the contract the frontend relies on: the shapes it destructures at
build time, and the demo endpoint it calls at runtime.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_summary_carries_every_section(client):
    body = client.get("/api/summary").json()
    for key in ("profile", "projects", "experience", "skills", "education", "notable"):
        assert key in body, f"summary is missing {key}"
    assert body["projects"], "no projects"
    assert body["experience"], "no experience"


def test_summary_strips_case_studies(client):
    """Case studies are large and only the detail view needs them."""
    for project in client.get("/api/summary").json()["projects"]:
        assert "caseStudy" not in project
        assert "hasCaseStudy" in project


def test_project_detail_includes_case_study(client):
    body = client.get("/api/projects/jobs-workbench").json()
    assert body["caseStudy"]["approach"]
    assert body["caseStudy"]["deepDive"]["result"]


def test_unknown_project_is_404(client):
    assert client.get("/api/projects/does-not-exist").status_code == 404


def test_projects_are_ordered(client):
    orders = [p.get("order", 999) for p in client.get("/api/projects").json()]
    assert orders == sorted(orders)


def test_proprietary_roles_are_flagged(client):
    """The site renders a marker off this flag. Losing it would silently imply
    that employer-owned work is available to look at."""
    roles = client.get("/api/experience").json()
    assert all(r["proprietary"] for r in roles)


def test_remote_samples_are_served(client):
    samples = client.get("/api/demos/remote-classifier/samples").json()
    assert len(samples) >= 6
    for s in samples:
        assert {"id", "label", "note", "location", "description"} <= set(s)


def test_classify_returns_verdict_gates_and_evidence(client):
    r = client.post(
        "/api/demos/remote-classifier",
        json={
            "location": "Remote - Canada",
            "remote_status": "remote",
            "description": "We are a hybrid team with over 1,500 employees across North America.",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "qualifies"
    assert len(body["gates"]) == 3
    assert body["evidence"]


def test_classify_rejects_empty_input(client):
    assert client.post("/api/demos/remote-classifier", json={}).status_code == 422


def test_classify_caps_oversized_input(client):
    """A posting body is prose. Refuse a payload big enough to be a denial of
    service against the regex engine."""
    r = client.post(
        "/api/demos/remote-classifier",
        json={"location": "Remote", "description": "x" * 20_000},
    )
    assert r.status_code == 422
