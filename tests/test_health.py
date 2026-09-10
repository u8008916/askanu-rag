from fastapi.testclient import TestClient

from askanu_rag.main import app, create_configured_app

client = TestClient(app)


def test_health_returns_only_safe_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_production_health_never_exposes_environment_or_secrets(monkeypatch) -> None:
    secret_values = {
        "ASKANU_ENV": "production",
        "GEMINI_API_KEY": "gemini-secret-sentinel",
        "GEMINI_MODEL": "gemini-model-sentinel",
        "DATABASE_URL": "postgresql://db-secret-sentinel@db.internal/askanu",
        "DB_PASSWORD": "db-password-secret-sentinel",
        "GOOGLE_CLOUD_PROJECT": "project-secret-sentinel",
        "CLOUD_SQL_INSTANCE_CONNECTION_NAME": "project:region:instance-secret-sentinel",
        "RAG_RUNTIME_SERVICE_ACCOUNT": "service-account-sentinel@example.invalid",
        "GOOGLE_APPLICATION_CREDENTIALS": "C:\\private\\credentials-sentinel.json",
    }
    for name in [
        "COURSE_RECORDS_PATH", "REQUEST_TIMEOUT_SECONDS", "MAX_OUTPUT_TOKENS",
        "SEMANTIC_TOP_K", "SEMANTIC_MIN_SCORE", "PORT", "LOG_LEVEL",
    ]:
        monkeypatch.delenv(name, raising=False)
    for name, value in secret_values.items():
        monkeypatch.setenv(name, value)

    with TestClient(create_configured_app()) as production_client:
        response = production_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    serialized = response.text.lower()
    for value in secret_values.values():
        assert value.lower() not in serialized
