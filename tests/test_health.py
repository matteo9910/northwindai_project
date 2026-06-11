from fastapi.testclient import TestClient

from backend.health.checks import ServiceHealth
from backend.main import app


def test_health_returns_all_service_keys(monkeypatch):
    monkeypatch.setattr(
        "backend.health.checks.check_postgres",
        lambda settings: ServiceHealth(available=True, detail="postgres ok"),
    )
    monkeypatch.setattr(
        "backend.health.checks.check_neo4j",
        lambda settings: ServiceHealth(available=True, detail="neo4j ok"),
    )
    monkeypatch.setattr(
        "backend.health.checks.check_qdrant",
        lambda settings: ServiceHealth(available=True, detail="qdrant ok"),
    )

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["services"]) == {"postgres", "neo4j", "qdrant"}


def test_health_reports_degraded_when_one_service_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "backend.health.checks.check_postgres",
        lambda settings: ServiceHealth(available=True, detail="postgres ok"),
    )
    monkeypatch.setattr(
        "backend.health.checks.check_neo4j",
        lambda settings: ServiceHealth(available=False, detail="neo4j unavailable"),
    )
    monkeypatch.setattr(
        "backend.health.checks.check_qdrant",
        lambda settings: ServiceHealth(available=True, detail="qdrant ok"),
    )

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["neo4j"] == {
        "available": False,
        "detail": "neo4j unavailable",
    }

