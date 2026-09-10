"""Official SDK adapter/config tests with an intercepted SDK, never real calls."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import httpx
from google import genai
from google.genai import types
from pydantic import SecretStr, ValidationError

from askanu_rag.config import DEFAULT_GEMINI_MODEL, DEFAULT_PORT, Settings
from askanu_rag.gemini import GeminiSynthesisClient
from askanu_rag.synthesis import SYSTEM_INSTRUCTION, SynthesisError, assemble_context
from test_grounded_synthesis import QUESTION, record


def sdk_stub(monkeypatch, response=None, error=None):
    generate = AsyncMock(return_value=response, side_effect=error)
    async_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    async_manager = AsyncMock()
    async_manager.__aenter__.return_value = async_client
    sync_client = SimpleNamespace(aio=async_manager)
    sync_manager = MagicMock()
    sync_manager.__enter__.return_value = sync_client
    constructor = MagicMock(return_value=sync_manager)
    monkeypatch.setattr("askanu_rag.gemini.genai.Client", constructor)
    return constructor, generate, sync_manager, async_manager


def good_response(context):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        finish_reason="STOP",
        content=types.Content(parts=[types.Part(text=json.dumps({
            "answer": context.allowed_answers[0], "supported": True
        }))]),
    )])


def test_sdk_receives_minimal_separated_context_and_structured_output_config(monkeypatch):
    context = assemble_context(record(), QUESTION)
    constructor, generate, sync_manager, async_manager = sdk_stub(
        monkeypatch, good_response(context)
    )
    settings = Settings(api_key=SecretStr("unit-test-placeholder"))
    output = asyncio.run(GeminiSynthesisClient(settings).synthesize(context))
    assert json.loads(output)["supported"] is True
    args = constructor.call_args.kwargs
    assert args["vertexai"] is False
    assert args["http_options"].base_url == "https://generativelanguage.googleapis.com"
    assert args["http_options"].timeout == 30000
    assert args["http_options"].retry_options.attempts == 1
    call = generate.call_args.kwargs
    assert call["model"] == DEFAULT_GEMINI_MODEL
    assert json.loads(call["contents"])["user_question"] == QUESTION
    config = call["config"]
    assert config.system_instruction == SYSTEM_INSTRUCTION
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema["additionalProperties"] is False
    assert config.response_json_schema["properties"]["answer"]["enum"] == list(context.allowed_answers)
    assert config.max_output_tokens == 800
    assert config.tools is None
    assert config.automatic_function_calling.disable
    sync_manager.__exit__.assert_called_once()
    async_manager.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("response", [
    types.GenerateContentResponse(),
    types.GenerateContentResponse(candidates=[types.Candidate(finish_reason="SAFETY")]),
    types.GenerateContentResponse(candidates=[types.Candidate(
        finish_reason="MAX_TOKENS", content=types.Content(parts=[types.Part(text="{}")])
    )]),
    types.GenerateContentResponse(candidates=[types.Candidate(
        finish_reason="STOP", content=types.Content(parts=[])
    )]),
    types.GenerateContentResponse(candidates=[types.Candidate(
        finish_reason="STOP", content=types.Content(parts=[types.Part(function_call=types.FunctionCall(name="bad"))])
    )]),
])
def test_provider_rejects_empty_blocked_truncated_and_tool_responses(monkeypatch, response):
    sdk_stub(monkeypatch, response)
    with pytest.raises(SynthesisError, match="Synthesis could not be validated"):
        asyncio.run(GeminiSynthesisClient(Settings(api_key=SecretStr("unit-test-placeholder"))).synthesize(
            assemble_context(record(), QUESTION)
        ))


def test_provider_exception_never_exposes_raw_diagnostics_and_closes(monkeypatch, caplog):
    _, _, sync_manager, async_manager = sdk_stub(
        monkeypatch, error=RuntimeError("private-key-and-prompt-sentinel")
    )
    with pytest.raises(SynthesisError) as caught:
        asyncio.run(GeminiSynthesisClient(Settings(api_key=SecretStr("unit-test-placeholder"))).synthesize(
            assemble_context(record(), QUESTION)
        ))
    assert "sentinel" not in str(caught.value) + caplog.text
    assert caught.value.__suppress_context__
    sync_manager.__exit__.assert_called_once()
    async_manager.__aexit__.assert_awaited_once()


def test_missing_key_fails_without_constructing_sdk(monkeypatch):
    constructor, *_ = sdk_stub(monkeypatch)
    with pytest.raises(SynthesisError):
        asyncio.run(GeminiSynthesisClient(Settings()).synthesize(assemble_context(record(), QUESTION)))
    constructor.assert_not_called()


def test_settings_read_only_explicit_dotenv_and_environment_wins(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GEMINI_API_KEY=unit-test-placeholder\nGEMINI_MODEL=file-model\n"
        "DATABASE_URL=postgresql://file-secret\n"
        "DB_PASSWORD=db-password-secret\nDB_NAME=askanu\nDB_USER=rag-user\n"
        "REQUEST_TIMEOUT_SECONDS=12\nMAX_OUTPUT_TOKENS=400\nCOURSE_RECORDS_PATH=records\n"
        "GOOGLE_CLOUD_PROJECT=file-project\n"
        "CLOUD_SQL_INSTANCE_CONNECTION_NAME=file-project:region:instance\n"
        "PORT=9090\nLOG_LEVEL=warning\n",
        encoding="utf-8",
    )
    for name in [
        "ASKANU_ENV", "GEMINI_API_KEY", "DATABASE_URL", "DB_PASSWORD",
        "DB_NAME", "DB_USER", "REQUEST_TIMEOUT_SECONDS", "MAX_OUTPUT_TOKENS",
        "COURSE_RECORDS_PATH", "GOOGLE_CLOUD_PROJECT",
        "CLOUD_SQL_INSTANCE_CONNECTION_NAME", "PORT", "LOG_LEVEL",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "environment-model")
    settings = Settings.from_environment(env_file)
    assert settings.model == "environment-model"
    assert settings.api_key.get_secret_value() == "unit-test-placeholder"
    assert settings.database_url.get_secret_value() == "postgresql://file-secret"
    assert settings.database_password.get_secret_value() == "db-password-secret"
    assert settings.database_name == "askanu"
    assert settings.database_user == "rag-user"
    assert settings.timeout_seconds == 12
    assert settings.max_output_tokens == 400
    assert str(settings.course_records_path) == "records"
    assert settings.google_cloud_project == "file-project"
    assert settings.cloud_sql_instance_connection_name == "file-project:region:instance"
    assert settings.port == 9090
    assert settings.log_level == "warning"
    serialized = repr(settings) + settings.model_dump_json()
    assert "unit-test-placeholder" not in serialized
    assert "postgresql://file-secret" not in serialized
    assert "db-password-secret" not in serialized


def test_production_configuration_ignores_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GEMINI_API_KEY=file-secret\nDATABASE_URL=file-db-secret\n"
        "DB_PASSWORD=file-db-password\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASKANU_ENV", "production")
    monkeypatch.setenv("GEMINI_API_KEY", "environment-secret")
    monkeypatch.setenv("DB_PASSWORD", "environment-db-password")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings.from_environment(env_file)
    assert settings.api_key.get_secret_value() == "environment-secret"
    assert settings.database_url.get_secret_value() == ""
    assert settings.database_password.get_secret_value() == "environment-db-password"


def test_local_default_port_is_canonical_rag_port(tmp_path, monkeypatch):
    monkeypatch.delenv("ASKANU_ENV", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    settings = Settings.from_environment(tmp_path / ".env")

    assert DEFAULT_PORT == 8081
    assert settings.port == 8081


def test_cloud_run_supplied_port_is_honoured(monkeypatch):
    monkeypatch.setenv("ASKANU_ENV", "production")
    monkeypatch.setenv("PORT", "8096")

    settings = Settings.from_environment()

    assert settings.port == 8096


@pytest.mark.parametrize("values", [
    {"timeout_seconds": 0}, {"timeout_seconds": 31},
    {"max_output_tokens": 0}, {"max_output_tokens": 801}, {"model": ""},
    {"port": 0}, {"port": 65_536}, {"log_level": "verbose"},
])
def test_settings_reject_unbounded_or_empty_config(values):
    with pytest.raises(ValidationError):
        Settings(**values)


def test_configured_factory_loads_external_json_without_scraper_import(tmp_path, monkeypatch):
    from askanu_rag.main import create_configured_app
    from fastapi.testclient import TestClient

    stored = record()
    record_file = tmp_path / "external.json"
    record_file.write_text(stored.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(Settings, "from_environment", classmethod(lambda cls: Settings(
        course_records_path=record_file, api_key=SecretStr("unit-test-placeholder")
    )))
    _, generate, *_ = sdk_stub(monkeypatch, good_response(assemble_context(stored, QUESTION)))
    with TestClient(create_configured_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.post("/api/v1/ask", json={
            "question": QUESTION, "history": [],
            "conversation_state": {"pending_clarification": None},
        })
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["sources"][0]["url"] == str(stored.canonical_url)
    generate.assert_awaited_once()


def test_real_sdk_serialization_uses_mock_http_transport_without_network(monkeypatch):
    context = assemble_context(record(), QUESTION)
    requests = []
    real_client = genai.Client

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"candidates": [{
            "finishReason": "STOP", "content": {"role": "model", "parts": [{
                "text": json.dumps({"answer": context.allowed_answers[0], "supported": True})
            }]}
        }]})

    def intercepted_client(**kwargs):
        transport = httpx.MockTransport(respond)
        kwargs["http_options"].client_args = {"transport": transport}
        kwargs["http_options"].async_client_args = {"transport": transport}
        return real_client(**kwargs)

    monkeypatch.setattr("askanu_rag.gemini.genai.Client", intercepted_client)
    raw = asyncio.run(GeminiSynthesisClient(Settings(api_key=SecretStr("unit-test-placeholder"))).synthesize(context))
    assert json.loads(raw)["answer"] == context.allowed_answers[0]
    assert len(requests) == 1
    request = requests[0]
    assert request.url.host == "generativelanguage.googleapis.com"
    assert "unit-test-placeholder" not in str(request.url)
    body = json.loads(request.content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseJsonSchema"]["properties"]["answer"]["enum"] == list(context.allowed_answers)
    assert "tools" not in body
