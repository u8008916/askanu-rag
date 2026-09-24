"""Frozen V7 Day 2 App-to-RAG transport-size contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pydantic_core import PydanticCustomError

from askanu_rag.main import _mark_response, create_app
from askanu_rag.models import AskRequest, ConversationState, OffTopicResponse
from askanu_rag.transport_limits import (
    ASK_REQUEST_MAX_BYTES,
    HISTORY_MAX_BYTES,
    HISTORY_TURN_CONTENT_MAX_CHARS,
    HISTORY_TURN_ID_MAX_CHARS,
    QUESTION_MAX_UTF8_BYTES,
    STATE_MAX_BYTES,
    compact_json_utf8,
    serialized_utf8_size,
    validate_utf8_text_limit,
)


def _error_status(response, status_code: int) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert body["status"] == "error"
    assert body["answer"] == "The request could not be completed."
    assert body["conversation_state"]["schema_version"] == 1


def _history_at_size(target: int) -> list[dict[str, str]]:
    history = [
        {"turn_id": f"turn-{index}", "role": "user", "content": ""}
        for index in range(10)
    ]
    remaining = target - serialized_utf8_size(history)
    assert remaining >= 0
    for turn in history:
        addition = min(remaining, HISTORY_TURN_CONTENT_MAX_CHARS)
        turn["content"] = "x" * addition
        remaining -= addition
    assert remaining == 0
    assert serialized_utf8_size(history) == target
    return history


def _state_at_size(target: int) -> ConversationState:
    constraint_types = [
        "max_price",
        "temporal_window",
        "date_window",
        "time_of_day_window",
        "student_type",
        "program",
        "study_level",
        "location",
        "category",
        "employment_type",
        "accessibility",
    ]

    def constraint(index: int, prefix: str) -> dict[str, object]:
        return {
            "semantic_type": constraint_types[index % len(constraint_types)],
            "value": "v",
            "scope": {
                "domain": "jobs",
                "entity_kind": "job",
                "canonical_entity_id": f"{prefix}-job-{index}",
                "intent": "discover",
            },
            "lifecycle": "until_replaced",
            "introduced_turn": 1,
        }

    raw: dict[str, object] = {
        "schema_version": 1,
        "turn_index": 20,
        "recent_entities": [
            {
                "domain": "jobs",
                "kind": "job",
                "canonical_id": f"recent-job-{index}",
                "canonical_name": f"Job {index}",
                "source_record_id": f"jobs:job:recent-{index}",
                "resolution_basis": "explicit_identifier",
                "mentioned_turn": 1,
            }
            for index in range(12)
        ],
        "student_facts": [
            {
                "semantic_type": fact_type,
                "value": "v",
                "domain_scope": domain,
                "stated_turn": 1,
            }
            for domain in ("courses", "scholarships", "jobs")
            for fact_type in ("international", "program", "study_level", "student_type")
        ],
        "constraints": {
            "items": [constraint(index, "state") for index in range(16)]
        },
        "result_sets": [
            {
                "result_set_id": f"rs:transport:{result_index}",
                "domain": "jobs",
                "entity_kind": "job",
                "ordered_canonical_ids": [
                    f"result-{result_index}-{identity_index}"
                    for identity_index in range(20)
                ],
                "originating_query": "q",
                "intent": {"name": "discover", "operation": "list"},
                "constraints": {
                    "items": [
                        constraint(index, f"rs-{result_index}")
                        for index in range(16)
                    ]
                },
                "created_turn": 1,
                "last_refined_turn": 1,
                "status": "RESULTS",
            }
            for result_index in range(6)
        ],
        "pending_clarification": {
            "id": "clar-transport",
            "type": "entity_selection",
            "options": [
                {"id": f"jobs:job:option-{index}", "label": f"Option {index}"}
                for index in range(20)
            ],
            "allow_multiple": False,
            "created_turn": 1,
        },
    }
    data = ConversationState.model_validate(raw).model_dump(mode="json")

    adjustable: list[tuple[dict[str, object], str, int]] = []
    for entity in data["recent_entities"]:
        adjustable.append((entity, "canonical_name", 200))
        adjustable.append((entity, "canonical_id", 200))
        adjustable.append((entity, "source_record_id", 200))
    for fact in data["student_facts"]:
        adjustable.append((fact, "value", 500))
    for item in data["constraints"]["items"]:
        adjustable.append((item, "value", 500))
        adjustable.append((item["scope"], "canonical_entity_id", 200))
        adjustable.append((item["scope"], "intent", 64))
    for result_set in data["result_sets"]:
        adjustable.append((result_set, "result_set_id", 200))
        adjustable.append((result_set, "originating_query", 500))
        for index in range(len(result_set["ordered_canonical_ids"])):
            identity = result_set["ordered_canonical_ids"][index]
            remaining = target - serialized_utf8_size(data)
            addition = min(remaining, 200 - len(identity))
            result_set["ordered_canonical_ids"][index] += "x" * addition
        for item in result_set["constraints"]["items"]:
            adjustable.append((item, "value", 500))
            adjustable.append((item["scope"], "canonical_entity_id", 200))
            adjustable.append((item["scope"], "intent", 64))
    pending = data["pending_clarification"]
    for option in pending["options"]:
        adjustable.append((option, "id", 200))
        adjustable.append((option, "label", 200))

    for mapping, key, max_chars in adjustable:
        remaining = target - serialized_utf8_size(data)
        if remaining <= 0:
            break
        current = mapping[key]
        addition = min(remaining, max_chars - len(current))
        mapping[key] = current + ("x" * addition)

    state = ConversationState.model_validate(data)
    assert serialized_utf8_size(state) == target
    return state


def test_conversation_state_exact_byte_boundary_is_accepted() -> None:
    state = _state_at_size(STATE_MAX_BYTES)

    request = AskRequest(question="hello", history=[], conversation_state=state)
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "clear chat",
                "history": [],
                "conversation_state": state.model_dump(mode="json"),
            },
        )

    assert serialized_utf8_size(request.conversation_state) == STATE_MAX_BYTES
    assert response.status_code == 200


def test_conversation_state_over_byte_boundary_is_rejected() -> None:
    state = _state_at_size(STATE_MAX_BYTES + 1)

    with pytest.raises(ValidationError, match="conversation_state"):
        AskRequest(question="hello", history=[], conversation_state=state)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "hello",
                "history": [],
                "conversation_state": state.model_dump(mode="json"),
            },
        )

    _error_status(response, 413)


def test_history_exact_byte_boundary_is_accepted() -> None:
    history = _history_at_size(HISTORY_MAX_BYTES)

    request = AskRequest.model_validate({"question": "hello", "history": history})
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/ask", json={"question": "clear chat", "history": history}
        )

    assert serialized_utf8_size(request.history) == HISTORY_MAX_BYTES
    assert response.status_code == 200


def test_history_over_byte_boundary_returns_controlled_413() -> None:
    history = _history_at_size(HISTORY_MAX_BYTES + 1)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/ask", json={"question": "hello", "history": history}
        )

    _error_status(response, 413)


def test_history_turn_individual_string_boundaries() -> None:
    accepted = AskRequest.model_validate(
        {
            "question": "hello",
            "history": [
                {
                    "turn_id": "t" * HISTORY_TURN_ID_MAX_CHARS,
                    "role": "user",
                    "content": "x" * HISTORY_TURN_CONTENT_MAX_CHARS,
                }
            ],
        }
    )
    assert len(accepted.history[0].turn_id) == HISTORY_TURN_ID_MAX_CHARS
    assert len(accepted.history[0].content) == HISTORY_TURN_CONTENT_MAX_CHARS

    for field, value in (
        ("turn_id", "t" * (HISTORY_TURN_ID_MAX_CHARS + 1)),
        ("content", "x" * (HISTORY_TURN_CONTENT_MAX_CHARS + 1)),
    ):
        turn = {"turn_id": "t", "role": "user", "content": "x"}
        turn[field] = value
        with pytest.raises(ValidationError):
            AskRequest.model_validate({"question": "hello", "history": [turn]})
        with TestClient(create_app()) as client:
            response = client.post(
                "/api/v1/ask", json={"question": "hello", "history": [turn]}
            )
        _error_status(response, 413)


def test_multibyte_question_with_2000_characters_is_accepted() -> None:
    question = "é" * 2_000
    assert len(question.encode("utf-8")) == 4_000

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/ask", json={"question": question, "history": []}
        )

    assert response.status_code == 200


def test_question_above_2000_characters_returns_controlled_413() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/ask", json={"question": "é" * 2_001, "history": []}
        )

    _error_status(response, 413)


def test_question_byte_validator_rejects_multibyte_text_above_8_kib() -> None:
    question = "😀" * 2_049
    assert len(question.encode("utf-8")) == QUESTION_MAX_UTF8_BYTES + 4

    with pytest.raises(PydanticCustomError):
        validate_utf8_text_limit(
            question, QUESTION_MAX_UTF8_BYTES, "question"
        )


def test_complete_request_exact_byte_boundary_is_accepted() -> None:
    content = compact_json_utf8({"question": "hello", "history": []})
    content += b" " * (ASK_REQUEST_MAX_BYTES - len(content))
    assert len(content) == ASK_REQUEST_MAX_BYTES

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/ask",
            content=content,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 200


def test_complete_request_over_byte_boundary_returns_controlled_413() -> None:
    content = compact_json_utf8({"question": "hello", "history": []})
    content += b" " * (ASK_REQUEST_MAX_BYTES + 1 - len(content))
    assert len(content) == ASK_REQUEST_MAX_BYTES + 1

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/ask",
            content=content,
            headers={"content-type": "application/json"},
        )

    _error_status(response, 413)


def test_authoritative_response_state_round_trips_within_limit() -> None:
    with TestClient(create_app()) as client:
        first = client.post(
            "/api/v1/ask",
            json={"question": "Prerequisites for COMP1110", "history": []},
        )
        returned_state = first.json()["conversation_state"]
        second = client.post(
            "/api/v1/ask",
            json={
                "question": "What about its learning outcomes?",
                "history": [],
                "conversation_state": returned_state,
            },
        )

    assert first.status_code == 200
    assert serialized_utf8_size(returned_state) <= STATE_MAX_BYTES
    assert second.status_code == 200


def test_oversized_internal_state_is_never_emitted_or_truncated() -> None:
    state = _state_at_size(STATE_MAX_BYTES + 1)
    request = SimpleNamespace(state=SimpleNamespace(conversation_state=state))
    response = OffTopicResponse(answer="No.", request_id="req_transport")

    with pytest.raises(RuntimeError, match="exceeds transport limit"):
        _mark_response(request, response)
