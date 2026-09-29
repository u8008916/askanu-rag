"""D7-A1 controlled semantic rejections preserve valid inbound state."""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from askanu_rag.main import create_app
from askanu_rag.retrieval import CourseProgramRepository
from test_v7_day4_accommodation_vertical import _twelve_residences


def _discover(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/ask",
        json={
            "question": "Show me accommodation options",
            "history": [],
            "conversation_state": {},
        },
    )
    assert response.status_code == 200
    return response.json()


def _error_payload(kind: str, discovered: dict) -> dict:
    state = deepcopy(discovered["conversation_state"])
    active = state["result_sets"][0]
    result_set_id = active["result_set_id"]
    base = {
        "question": "Show more",
        "history": [],
        "conversation_state": state,
    }
    if kind == "stale_cursor":
        state["result_page"] = None
        return base
    if kind == "older_resultset":
        older = deepcopy(active)
        older["result_set_id"] = "rs:accommodation:older"
        older["created_turn"] = 0
        older["last_refined_turn"] = 0
        state["result_sets"].append(older)
        return base | {
            "result_page": {
                "result_set_id": older["result_set_id"],
                "start_ordinal": 6,
                "limit": 5,
            }
        }
    if kind == "invalid_resultset_id":
        return base | {
            "result_page": {
                "result_set_id": "rs:accommodation:missing",
                "start_ordinal": 6,
                "limit": 5,
            }
        }
    if kind == "mismatched_ordinal":
        return base | {
            "question": "Tell me about it",
            "selected_result": {
                "result_set_id": result_set_id,
                "canonical_id": active["ordered_canonical_ids"][0],
                "ordinal": 2,
            },
        }
    if kind == "tampered_selected_id":
        return base | {
            "question": "Tell me about it",
            "selected_result": {
                "result_set_id": result_set_id,
                "canonical_id": "client-created-hall",
                "ordinal": 1,
            },
        }
    if kind == "tampered_selected_set":
        return base | {
            "question": "Tell me about it",
            "selected_result": {
                "result_set_id": "rs:accommodation:missing",
                "canonical_id": active["ordered_canonical_ids"][0],
                "ordinal": 1,
            },
        }
    if kind == "page_past_end":
        return base | {
            "result_page": {
                "result_set_id": result_set_id,
                "start_ordinal": 14,
                "limit": 5,
            }
        }
    if kind == "page_replayed_start":
        return base | {
            "result_page": {
                "result_set_id": result_set_id,
                "start_ordinal": 1,
                "limit": 5,
            }
        }
    raise AssertionError(kind)


@pytest.mark.parametrize(
    "kind",
    (
        "stale_cursor",
        "older_resultset",
        "invalid_resultset_id",
        "mismatched_ordinal",
        "tampered_selected_id",
        "tampered_selected_set",
        "page_past_end",
        "page_replayed_start",
    ),
)
def test_a1_controlled_semantic_rejection_echoes_valid_inbound_state(kind: str) -> None:
    with TestClient(
        create_app(CourseProgramRepository(_twelve_residences()))
    ) as client:
        discovered = _discover(client)
        payload = _error_payload(kind, discovered)
        inbound = deepcopy(payload["conversation_state"])

        rejected = client.post("/api/v1/ask", json=payload)

        assert rejected.status_code == 400
        assert rejected.json()["conversation_state"] == inbound
        followup = client.post(
            "/api/v1/ask",
            json={
                "question": "Tell me about the second one",
                "history": [],
                "conversation_state": rejected.json()["conversation_state"],
            },
        )
        assert followup.status_code == 200
        assert followup.json()["items"][0]["ordinal"] == 2


def test_a1_clear_chat_remains_the_only_deliberate_reset() -> None:
    with TestClient(
        create_app(CourseProgramRepository(_twelve_residences()))
    ) as client:
        discovered = _discover(client)
        cleared = client.post(
            "/api/v1/ask",
            json={
                "question": "Clear Chat",
                "history": [],
                "conversation_state": discovered["conversation_state"],
            },
        )

    assert cleared.status_code == 200
    assert cleared.json()["conversation_state"]["turn_index"] == 0
    assert cleared.json()["conversation_state"]["result_sets"] == []


def test_a1_invalid_inbound_state_keeps_validation_fallback_behavior() -> None:
    with TestClient(
        create_app(CourseProgramRepository(_twelve_residences()))
    ) as client:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": "Tell me about the second one",
                "history": [],
                "conversation_state": {"schema_version": 999},
            },
        )

    assert response.status_code == 400
    assert response.json()["conversation_state"]["turn_index"] == 0
    assert response.json()["conversation_state"]["result_sets"] == []
