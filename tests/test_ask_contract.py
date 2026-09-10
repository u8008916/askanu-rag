import json

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from askanu_rag.main import (
    MOCK_CLARIFICATION_TRIGGER,
    app,
    controlled_error_response,
    create_app,
)
from askanu_rag.models import (
    AskResponse,
    Clarification,
    ClarificationOption,
    ErrorResponse,
    InsufficientEvidenceResponse,
    NeedsClarificationResponse,
    OffTopicResponse,
    OkResponse,
    PartialResponse,
)

client = TestClient(app)


def valid_request(question: str = "Does it have prerequisites?") -> dict[str, object]:
    return {
        "question": question,
        "history": [
            {
                "turn_id": "t1",
                "role": "user",
                "content": "Tell me about COMP1110",
            },
            {"turn_id": "t2", "role": "assistant", "content": "..."},
        ],
        "conversation_state": {"pending_clarification": None},
    }


def assert_error_envelope(response: object, expected_status: int) -> dict[str, object]:
    assert getattr(response, "status_code") == expected_status
    body = getattr(response, "json")()
    assert body["status"] == "error"
    assert body["answer"] == "The request could not be completed."
    assert body["items"] == []
    assert body["sources"] == []
    assert body["clarification"] is None
    assert body["request_id"].startswith("req_")
    return body


def test_valid_frozen_request_returns_complete_contract_envelope() -> None:
    response = client.post("/api/v1/ask", json=valid_request())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "status",
        "answer",
        "items",
        "sources",
        "clarification",
        "request_id",
    }
    assert body["status"] == "insufficient_evidence"
    assert body["clarification"] is None
    assert body["request_id"].startswith("req_")


def test_pending_clarification_request_shape_is_accepted() -> None:
    payload = valid_request("both")
    payload["conversation_state"] = {
        "pending_clarification": {
            "id": "clar-42",
            "type": "entity_selection",
            "options": [
                {"id": "course:COMP1110", "label": "COMP1110"},
                {"id": "course:COMP1600", "label": "COMP1600"},
            ],
            "allow_multiple": True,
        }
    }

    response = client.post("/api/v1/ask", json=payload)

    assert response.status_code == 200


def test_history_content_has_no_undocumented_per_message_limit() -> None:
    payload = valid_request()
    payload["history"] = [
        {"turn_id": "t1", "role": "user", "content": "x" * 10_000}
    ]

    response = client.post("/api/v1/ask", json=payload)

    assert response.status_code == 200


def test_source_keeps_record_and_registry_identifiers_separate() -> None:
    response = client.post(
        "/api/v1/ask", json=valid_request("Prerequisites for COMP1110")
    )

    source = response.json()["sources"][0]
    assert set(source) == {"record_id", "source_id", "title", "url", "domain"}
    assert source["record_id"] == "courses:course:COMP1110_2026"
    assert source["source_id"] == "courses_programs_and_courses"
    assert source["record_id"] != source["source_id"]


def test_malformed_json_returns_controlled_400() -> None:
    response = client.post(
        "/api/v1/ask",
        content='{ "question": ',
        headers={"content-type": "application/json"},
    )

    assert_error_envelope(response, 400)


def test_ordinary_validation_failure_returns_controlled_400() -> None:
    payload = valid_request()
    del payload["question"]

    response = client.post("/api/v1/ask", json=payload)

    assert_error_envelope(response, 400)


def test_question_over_limit_returns_controlled_413_without_truncation() -> None:
    response = client.post("/api/v1/ask", json=valid_request("x" * 2_001))

    assert_error_envelope(response, 413)


def test_history_over_limit_returns_controlled_413() -> None:
    payload = valid_request()
    payload["history"] = [
        {"turn_id": f"t{index}", "role": "user", "content": "message"}
        for index in range(11)
    ]

    response = client.post("/api/v1/ask", json=payload)

    assert_error_envelope(response, 413)


def test_mock_clarification_preserves_frozen_shape_and_option_order() -> None:
    response = client.post(
        "/api/v1/ask", json=valid_request(MOCK_CLARIFICATION_TRIGGER)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_clarification"
    assert body["clarification"] == {
        "id": "clar-42",
        "type": "entity_selection",
        "options": [
            {"id": "course:COMP1110", "label": "COMP1110"},
            {"id": "course:COMP1600", "label": "COMP1600"},
        ],
        "allow_multiple": True,
    }


@pytest.mark.parametrize(
    ("model", "status"),
    [
        (OkResponse, "ok"),
        (PartialResponse, "partial"),
        (NeedsClarificationResponse, "needs_clarification"),
        (InsufficientEvidenceResponse, "insufficient_evidence"),
        (OffTopicResponse, "off_topic"),
        (ErrorResponse, "error"),
    ],
)
def test_all_six_frozen_status_models_validate_and_serialize(
    model: type, status: str
) -> None:
    values: dict[str, object] = {"answer": "contract test", "request_id": "req_test"}
    if model is NeedsClarificationResponse:
        values["clarification"] = Clarification(
            id="clar-test",
            type="entity_selection",
            options=[ClarificationOption(id="course:COMP1110", label="COMP1110")],
            allow_multiple=False,
        )

    response = model(**values)
    serialized = response.model_dump(mode="json")
    validated = TypeAdapter(AskResponse).validate_python(serialized)

    assert serialized["status"] == status
    assert validated.status == status


def test_rate_limit_error_uses_the_frozen_envelope() -> None:
    response = controlled_error_response(429)
    body = json.loads(response.body)

    assert response.status_code == 429
    assert body["status"] == "error"


def test_unknown_route_returns_controlled_json_error() -> None:
    response = client.get("/not-a-real-route")

    assert response.headers["content-type"].startswith("application/json")
    assert_error_envelope(response, 404)


def test_internal_failure_is_controlled_and_does_not_leak_diagnostics() -> None:
    test_app = create_app()

    @test_app.get("/_test/internal-failure")
    async def fail_for_test() -> None:
        raise RuntimeError(
            "SECRET_TOKEN system prompt database.example.internal traceback "
            "C:\\private\\service.py"
        )

    test_client = TestClient(test_app, raise_server_exceptions=False)
    response = test_client.get("/_test/internal-failure")
    body = assert_error_envelope(response, 500)
    serialized = json.dumps(body).lower()

    for forbidden in (
        "secret_token",
        "system prompt",
        "database.example.internal",
        "traceback",
        "c:\\private\\service.py",
    ):
        assert forbidden not in serialized
