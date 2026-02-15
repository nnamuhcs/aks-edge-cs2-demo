import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_recommendations_top5(client):
    r = client.get("/recommendations?limit=5")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 5
    assert all("score" in row for row in data)


def test_manual_track_endpoint(client):
    r = client.post("/track")
    assert r.status_code == 200
    assert "created_snapshots" in r.json()
