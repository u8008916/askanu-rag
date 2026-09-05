from fastapi.testclient import TestClient

from askanu_rag.main import app

client = TestClient(app)


def test_health_returns_only_safe_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
