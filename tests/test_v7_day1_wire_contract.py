"""Additive, backwards-compatible V7 conversation_state HTTP contract."""

from __future__ import annotations

from fastapi.testclient import TestClient

from askanu_rag.main import MOCK_CLARIFICATION_TRIGGER, create_app
from askanu_rag.models import (
    ConversationState,
    Domain,
    EntityKind,
    EntityResolutionBasis,
    ResolvedEntity,
)
from askanu_rag.state_transitions import advance_turn, remember_entity


def payload(question: str, *, state: object = ...) -> dict[str, object]:
    body: dict[str, object] = {"question": question, "history": []}
    if state is not ...:
        body["conversation_state"] = state
    return body


def post(question: str, *, state: object = ...):
    with TestClient(create_app()) as client:
        return client.post("/api/v1/ask", json=payload(question, state=state))


def test_old_caller_may_omit_conversation_state_and_receives_v1_state() -> None:
    response = post("Prerequisites for COMP1110")

    assert response.status_code == 200
    returned = response.json()["conversation_state"]
    assert returned["schema_version"] == 1
    assert returned["turn_index"] == 1
    assert returned["recent_entities"] == []


def test_legacy_pending_only_shape_remains_accepted() -> None:
    response = post(
        "first",
        state={
            "pending_clarification": {
                "id": "clar-test",
                "type": "entity_selection",
                "options": [
                    {
                        "id": "courses:course:COMP1110_2026",
                        "label": "COMP1110 (2026)",
                    }
                ],
                "allow_multiple": False,
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["conversation_state"]["schema_version"] == 1


def test_valid_structured_state_round_trips_through_rag_owned_transition() -> None:
    state = advance_turn(ConversationState())
    warrumbul = ResolvedEntity(
        domain=Domain.ACCOMMODATION,
        kind=EntityKind.RESIDENCE,
        canonical_id="warrumbul-lodge",
        canonical_name="Warrumbul Lodge",
        source_record_id="accommodation:residence:warrumbul-lodge",
        resolution_basis=EntityResolutionBasis.CANONICAL_NAME,
        mentioned_turn=1,
    )
    state = remember_entity(state, warrumbul)

    response = post(
        "Prerequisites for COMP1110",
        state=state.model_dump(mode="json"),
    )

    assert response.status_code == 200
    returned = response.json()["conversation_state"]
    assert returned["turn_index"] == 2
    assert returned["recent_entities"][0]["canonical_id"] == "warrumbul-lodge"


def test_response_clarification_is_copied_into_authoritative_state() -> None:
    response = post(MOCK_CLARIFICATION_TRIGGER)

    assert response.status_code == 200
    body = response.json()
    pending = body["conversation_state"]["pending_clarification"]
    assert pending["id"] == body["clarification"]["id"]
    assert pending["original_intent"]["operation"] == "select_option"
    assert pending["missing_slots"] == ["selection"]


def test_unknown_state_field_is_controlled_400() -> None:
    response = post(
        "Prerequisites for COMP1110",
        state={"schema_version": 1, "institutional_facts": {"vacancy": True}},
    )

    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_incompatible_state_version_is_controlled_400() -> None:
    response = post(
        "Prerequisites for COMP1110", state={"schema_version": 2}
    )

    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_malformed_state_does_not_coerce_turn_counter() -> None:
    response = post(
        "Prerequisites for COMP1110",
        state={"schema_version": 1, "turn_index": "12"},
    )

    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_entity_collection_over_limit_is_controlled_400() -> None:
    entities = [
        {
            "domain": "jobs",
            "kind": "job",
            "canonical_id": f"job-{index}",
            "canonical_name": f"Job {index}",
            "source_record_id": f"jobs:job:{index}",
            "resolution_basis": "explicit_identifier",
            "mentioned_turn": 1,
        }
        for index in range(13)
    ]
    response = post(
        "What jobs are open?",
        state={
            "schema_version": 1,
            "turn_index": 1,
            "recent_entities": entities,
        },
    )

    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_invalid_focus_reference_is_controlled_400() -> None:
    response = post(
        "Prerequisites for COMP1110",
        state={
            "schema_version": 1,
            "focus": {
                "domain": "courses",
                "entity_kind": "course",
                "canonical_entity_id": "COMP9999",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_duplicate_semantic_entity_identity_is_controlled_400() -> None:
    duplicate = {
        "domain": "courses",
        "kind": "course",
        "canonical_id": "COMP1110",
        "canonical_name": "Structured Programming",
        "source_record_id": "courses:course:COMP1110_2026",
        "resolution_basis": "explicit_identifier",
        "mentioned_turn": 1,
    }

    response = post(
        "What are its prerequisites?",
        state={
            "schema_version": 1,
            "turn_index": 1,
            "recent_entities": [duplicate, duplicate],
        },
    )

    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_client_collection_order_is_canonicalized_before_round_trip() -> None:
    def retained(canonical_id: str, turn: int) -> dict[str, object]:
        return {
            "domain": "courses",
            "kind": "course",
            "canonical_id": canonical_id,
            "canonical_name": canonical_id,
            "source_record_id": f"courses:course:{canonical_id}_2026",
            "resolution_basis": "explicit_identifier",
            "mentioned_turn": turn,
        }

    response = post(
        "What are its prerequisites?",
        state={
            "schema_version": 1,
            "turn_index": 2,
            "recent_entities": [retained("COMP1100", 1), retained("COMP1110", 2)],
        },
    )

    assert response.status_code == 200
    returned = response.json()["conversation_state"]["recent_entities"]
    assert [item["canonical_id"] for item in returned] == ["COMP1110", "COMP1100"]


def test_client_state_is_not_used_as_factual_evidence() -> None:
    state = {
        "schema_version": 1,
        "turn_index": 1,
        "recent_entities": [
            {
                "domain": "accommodation",
                "kind": "residence",
                "canonical_id": "warrumbul-lodge",
                "canonical_name": "Warrumbul Lodge",
                "source_record_id": "accommodation:residence:warrumbul-lodge",
                "resolution_basis": "canonical_name",
                "mentioned_turn": 1,
            }
        ],
        "focus": {
            "domain": "accommodation",
            "entity_kind": "residence",
            "canonical_entity_id": "warrumbul-lodge",
        },
    }

    response = post("Is it catered?", state=state)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"insufficient_evidence", "off_topic"}
    assert body["sources"] == []
    assert "catered" not in body["answer"].casefold()
