"""Additive, backwards-compatible V7 conversation_state HTTP contract."""

from __future__ import annotations

from fastapi.testclient import TestClient

import askanu_rag.conversation_orchestrator as orchestrator_module
from askanu_rag.main import MOCK_CLARIFICATION_TRIGGER, create_app
from askanu_rag.models import (
    ConstraintLifecycle,
    ConstraintScope,
    ConstraintSemanticType,
    ConversationState,
    Domain,
    EntityKind,
    EntityResolutionBasis,
    ResolvedEntity,
    ResolvedIntent,
    ResultSet,
    ResultSetStatus,
    ScopedConstraint,
    StudentFactType,
    StudentStatedFact,
)
from askanu_rag.models.conversation_state import (
    MAX_CLARIFICATION_OPTIONS,
    MAX_RESULT_IDENTITIES,
    MAX_RETAINED_CONSTRAINTS,
    MAX_RETAINED_ENTITIES,
    MAX_RETAINED_RESULT_SETS,
    MAX_RETAINED_STUDENT_FACTS,
)
from askanu_rag.state_transitions import (
    advance_turn,
    put_constraint,
    remember_entity,
    remember_result_set,
    remember_student_fact,
)


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
    assert returned["recent_entities"][0]["canonical_id"] == "COMP1110"


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
    assert {item["canonical_id"] for item in returned["recent_entities"]} == {
        "COMP1110",
        "warrumbul-lodge",
    }


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


def test_api_conversation_state_round_trips_for_20_turns_with_bounded_lifecycle(
    monkeypatch,
) -> None:
    """Exercise the client-carried lifecycle through twenty fresh app instances.

    The patched transition is a deterministic Day 1 state writer, not a natural-
    language interpreter. It lets the wire test exercise every collection bound
    while the client still returns each authoritative response state unchanged.
    """

    real_advance_turn = advance_turn
    constraint_keys = [
        (semantic_type, domain)
        for domain in Domain
        for semantic_type in ConstraintSemanticType
        if semantic_type != ConstraintSemanticType.MAX_PRICE_EXCLUSIVE
    ][:MAX_RETAINED_CONSTRAINTS]
    fact_keys = [
        (semantic_type, domain)
        for domain in Domain
        for semantic_type in StudentFactType
    ]

    def day1_lifecycle_transition(incoming: ConversationState) -> ConversationState:
        state = real_advance_turn(incoming)
        turn = state.turn_index
        state = remember_entity(
            state,
            ResolvedEntity(
                domain=Domain.JOBS,
                kind=EntityKind.JOB,
                canonical_id=f"wire-job-{turn}",
                canonical_name=f"Wire job {turn}",
                source_record_id=f"jobs:job:wire-{turn}",
                resolution_basis=EntityResolutionBasis.EXPLICIT_IDENTIFIER,
                mentioned_turn=turn,
            ),
        )
        state = remember_result_set(
            state,
            ResultSet(
                result_set_id=f"rs:wire:{turn}",
                domain=Domain.JOBS,
                entity_kind=EntityKind.JOB,
                ordered_canonical_ids=tuple(
                    f"wire-job-{turn}-{index}"
                    for index in range(1, MAX_RESULT_IDENTITIES + 1)
                ),
                originating_query=f"wire lifecycle turn {turn}",
                intent=ResolvedIntent(name="discover", operation="list"),
                created_turn=turn,
                last_refined_turn=turn,
                status=ResultSetStatus.RESULTS,
            ),
        )
        constraint_type, constraint_domain = constraint_keys[
            (turn - 1) % len(constraint_keys)
        ]
        state = put_constraint(
            state,
            ScopedConstraint(
                semantic_type=constraint_type,
                value=turn,
                scope=ConstraintScope(domain=constraint_domain),
                lifecycle=ConstraintLifecycle.UNTIL_REPLACED,
                introduced_turn=turn,
            ),
        )
        fact_type, fact_domain = fact_keys[turn - 1]
        return remember_student_fact(
            state,
            StudentStatedFact(
                semantic_type=fact_type,
                value=f"wire-value-{turn}",
                domain_scope=fact_domain,
                stated_turn=turn,
            ),
        )

    monkeypatch.setattr(
        orchestrator_module, "advance_turn", day1_lifecycle_transition
    )

    returned_state: dict[str, object] | None = None
    for request_number in range(1, 21):
        question = (
            MOCK_CLARIFICATION_TRIGGER
            if request_number == 20
            else "hello"
        )
        request_body = payload(
            question,
            state=returned_state if returned_state is not None else ...,
        )
        assert request_body["history"] == []
        if returned_state is None:
            assert "conversation_state" not in request_body
        else:
            assert request_body["conversation_state"] is returned_state

        # A new app instance per turn demonstrates that continuity requires no
        # server-side session ID or process-local session store.
        with TestClient(create_app()) as client:
            response = client.post("/api/v1/ask", json=request_body)

        assert response.status_code == 200
        body = response.json()
        assert "session_id" not in body
        returned_state = body["conversation_state"]
        validated = ConversationState.model_validate(returned_state)
        assert validated.schema_version == 1
        assert validated.turn_index == request_number
        assert len(validated.recent_entities) <= MAX_RETAINED_ENTITIES
        assert len(validated.result_sets) <= MAX_RETAINED_RESULT_SETS
        assert all(
            len(result_set.ordered_canonical_ids) <= MAX_RESULT_IDENTITIES
            for result_set in validated.result_sets
        )
        assert len(validated.constraints.items) <= MAX_RETAINED_CONSTRAINTS
        assert len(validated.student_facts) <= MAX_RETAINED_STUDENT_FACTS
        options = (
            validated.pending_clarification.options
            if validated.pending_clarification is not None
            else ()
        )
        assert len(options) <= MAX_CLARIFICATION_OPTIONS

    assert returned_state is not None
    final_state = ConversationState.model_validate(returned_state)
    assert len(final_state.recent_entities) == MAX_RETAINED_ENTITIES
    assert [entity.canonical_id for entity in final_state.recent_entities] == [
        f"wire-job-{turn}" for turn in range(20, 8, -1)
    ]
    assert len(final_state.result_sets) == MAX_RETAINED_RESULT_SETS
    assert [result.result_set_id for result in final_state.result_sets] == [
        f"rs:wire:{turn}" for turn in range(20, 14, -1)
    ]
    assert len(final_state.constraints.items) == MAX_RETAINED_CONSTRAINTS
    assert len(final_state.student_facts) == MAX_RETAINED_STUDENT_FACTS
    assert final_state.pending_clarification is not None
    assert len(final_state.pending_clarification.options) == 2


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
