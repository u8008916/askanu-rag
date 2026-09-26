from pathlib import Path

from fastapi.testclient import TestClient

from askanu_rag.conversation_orchestrator import orchestrate_turn
from askanu_rag.main import create_app
from askanu_rag.models import ConversationState
from askanu_rag.retrieval import (
    CourseProgramRepository,
    load_course_program_records,
)
from askanu_rag.retrieval.identifiers import (
    normalize_course_code,
    normalize_course_code_reference,
)


ROOT = Path(__file__).resolve().parents[1]


def repository():
    return CourseProgramRepository(
        load_course_program_records(
            ROOT / "fixtures" / "day5_course_program_records.json"
        )
    )


def test_reference_normalization_does_not_weaken_canonical_validation():
    assert normalize_course_code("COMP1110") == "COMP1110"
    assert normalize_course_code("COMP 1110") == "COMP1110"

    # Frozen strict canonical boundary remains unchanged.
    assert normalize_course_code("COMP-1110") is None
    assert normalize_course_code("COMP/1110") is None
    assert normalize_course_code("COMP--1110") is None

    # Natural query references get a separate bounded normalization layer.
    assert normalize_course_code_reference("COMP1110") == "COMP1110"
    assert normalize_course_code_reference("comp 1110") == "COMP1110"
    assert normalize_course_code_reference("comp-1110") == "COMP1110"
    assert normalize_course_code_reference("COMP - 1110") == "COMP1110"
    assert normalize_course_code_reference("COMP/1110") is None
    assert normalize_course_code_reference("COMP--1110") is None


def test_prereqs_abbreviation_is_a_course_fact_lookup():
    turn = orchestrate_turn(
        "What prereqs do I need for COMP1110?",
        (),
        ConversationState(),
    )

    assert turn.interpretation.entity is not None
    assert turn.interpretation.entity.canonical_id == "COMP1110"
    assert turn.interpretation.domain.value == "courses"
    assert turn.interpretation.intent is not None
    assert turn.interpretation.intent.name == "fact_lookup"


def ask(client, question, history=None, state=None):
    return client.post(
        "/api/v1/ask",
        json={
            "question": question,
            "history": history or [],
            "conversation_state": state or {},
        },
    )


def assert_comp1110_prerequisites(response):
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ok"
    assert (
        body["answer"]
        == "The prerequisites for COMP1110 (2026) are: "
        "COMP1100 OR COMP1130 OR COMP1730"
    )
    assert body["sources"][0]["record_id"] == "courses:course:COMP1110_2026"


def test_api_accepts_hyphenated_course_reference():
    with TestClient(create_app(repository=repository())) as client:
        response = ask(
            client,
            "What are the prerequisites for comp-1110?",
        )

    assert_comp1110_prerequisites(response)


def test_api_accepts_prereqs_abbreviation():
    with TestClient(create_app(repository=repository())) as client:
        response = ask(
            client,
            "What prereqs do I need for COMP1110?",
        )

    assert_comp1110_prerequisites(response)


def test_api_accepts_prereqs_plus_hyphenated_course_reference():
    with TestClient(create_app(repository=repository())) as client:
        response = ask(
            client,
            "What prereqs do I need for comp-1110?",
        )

    assert_comp1110_prerequisites(response)


def test_canonical_name_state_drives_course_followup_retrieval():
    with TestClient(create_app(repository=repository())) as client:
        first = ask(
            client,
            "Tell me about Structured Programming.",
        )

        assert first.status_code == 200
        first_body = first.json()
        assert first_body["status"] == "ok"

        retained = first_body["conversation_state"]["recent_entities"][0]
        assert retained["canonical_id"] == "COMP1110"
        assert retained["resolution_basis"] == "canonical_name"

        second = ask(
            client,
            "What are its prerequisites?",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about Structured Programming.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": first_body["answer"],
                },
            ],
            state=first_body["conversation_state"],
        )

    assert_comp1110_prerequisites(second)


def test_selected_course_year_survives_followup_after_clarification():
    with TestClient(create_app(repository=repository())) as client:
        first = ask(
            client,
            "Actually, tell me about COMP1100.",
        )
        first_body = first.json()

        assert first_body["status"] == "needs_clarification"
        assert [item["id"] for item in first_body["clarification"]["options"]] == [
            "courses:course:COMP1100_2026",
            "courses:course:COMP1100_2027",
        ]

        selected = ask(
            client,
            "COMP1100 (2026) — Programming as Problem Solving",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Actually, tell me about COMP1100.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": first_body["answer"],
                },
            ],
            state=first_body["conversation_state"],
        )
        selected_body = selected.json()

        assert selected_body["status"] == "ok"
        retained = selected_body["conversation_state"]["recent_entities"][0]
        assert retained["canonical_id"] == "COMP1100"
        assert (
            retained["source_record_id"]
            == "courses:course:COMP1100_2026"
        )

        followup = ask(
            client,
            "What are its prerequisites?",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Actually, tell me about COMP1100.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": first_body["answer"],
                },
                {
                    "turn_id": "u2",
                    "role": "user",
                    "content": "COMP1100 (2026) — Programming as Problem Solving",
                },
                {
                    "turn_id": "a2",
                    "role": "assistant",
                    "content": selected_body["answer"],
                },
            ],
            state=selected_body["conversation_state"],
        )

    body = followup.json()

    assert followup.status_code == 200
    assert body["status"] == "insufficient_evidence"
    assert (
        body["answer"]
        == "The stored evidence for COMP1100 (2026) does not establish "
        "its prerequisites."
    )
    assert body["clarification"] is None
    assert body["sources"][0]["record_id"] == "courses:course:COMP1100_2026"


def test_ordinal_clarification_selection_also_retains_exact_course_year():
    with TestClient(create_app(repository=repository())) as client:
        first = ask(client, "Tell me about COMP1100.")
        first_body = first.json()

        assert first_body["status"] == "needs_clarification"

        selected = ask(
            client,
            "first",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about COMP1100.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": first_body["answer"],
                },
            ],
            state=first_body["conversation_state"],
        )
        selected_body = selected.json()

        assert selected_body["status"] == "ok"
        retained = selected_body["conversation_state"]["recent_entities"][0]
        assert retained["canonical_id"] == "COMP1100"
        assert retained["source_record_id"] == "courses:course:COMP1100_2026"


def test_explicit_new_course_request_supersedes_stale_year_clarification():
    with TestClient(create_app(repository=repository())) as client:
        ambiguous = ask(
            client,
            "Tell me about COMP1100.",
        )
        ambiguous_body = ambiguous.json()

        assert ambiguous_body["status"] == "needs_clarification"

        switched = ask(
            client,
            "Actually, tell me about COMP1110.",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about COMP1100.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": ambiguous_body["answer"],
                },
            ],
            state=ambiguous_body["conversation_state"],
        )
        switched_body = switched.json()

        assert switched_body["status"] == "ok"
        assert switched_body["clarification"] is None
        assert "COMP1110 (2026)" in switched_body["answer"]

        retained = switched_body["conversation_state"]["recent_entities"][0]
        assert retained["canonical_id"] == "COMP1110"

        followup = ask(
            client,
            "What are its prerequisites?",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about COMP1100.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": ambiguous_body["answer"],
                },
                {
                    "turn_id": "u2",
                    "role": "user",
                    "content": "Actually, tell me about COMP1110.",
                },
                {
                    "turn_id": "a2",
                    "role": "assistant",
                    "content": switched_body["answer"],
                },
            ],
            state=switched_body["conversation_state"],
        )

    assert_comp1110_prerequisites(followup)


def test_safe_alias_structurd_programming_retrieves_on_same_turn():
    with TestClient(create_app(repository=repository())) as client:
        response = ask(
            client,
            "Tell me about Structurd Programming.",
        )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert "COMP1110 (2026)" in body["answer"]

    retained = body["conversation_state"]["recent_entities"][0]
    assert retained["canonical_id"] == "COMP1110"
    assert retained["resolution_basis"] == "safe_alias"


def test_safe_alias_structured_programing_retrieves_on_same_turn():
    with TestClient(create_app(repository=repository())) as client:
        response = ask(
            client,
            "Tell me about Structured Programing.",
        )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert "COMP1110 (2026)" in body["answer"]

    retained = body["conversation_state"]["recent_entities"][0]
    assert retained["canonical_id"] == "COMP1110"
    assert retained["resolution_basis"] == "safe_alias"


def test_safe_alias_preserves_prerequisite_fact_intent():
    with TestClient(create_app(repository=repository())) as client:
        response = ask(
            client,
            "What are the prerequisites for Structurd Programming?",
        )

    assert_comp1110_prerequisites(response)


def test_more_corrupted_course_name_is_not_silently_guessed():
    with TestClient(create_app(repository=repository())) as client:
        response = ask(
            client,
            "Tell me about Structred Prgraming.",
        )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] != "ok"

    state = body["conversation_state"]
    assert not any(
        entity["canonical_id"] == "COMP1110"
        for entity in state["recent_entities"]
    )


import pytest


def test_non_comp_course_replaces_previous_comp_focus():
    with TestClient(create_app(repository=repository())) as client:
        comp = ask(
            client,
            "Tell me about COMP2200.",
        )
        comp_body = comp.json()

        assert comp_body["status"] == "ok"
        assert "COMP2200 (2026)" in comp_body["answer"]

        biol = ask(
            client,
            "Tell me about BIOL9001P.",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about COMP2200.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": comp_body["answer"],
                },
            ],
            state=comp_body["conversation_state"],
        )
        biol_body = biol.json()

        assert biol_body["status"] == "ok"
        assert "BIOL9001P (2026)" in biol_body["answer"]

        retained = biol_body["conversation_state"]["recent_entities"][0]
        assert retained["canonical_id"] == "BIOL9001P"

        followup = ask(
            client,
            "What are its prerequisites?",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about COMP2200.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": comp_body["answer"],
                },
                {
                    "turn_id": "u2",
                    "role": "user",
                    "content": "Tell me about BIOL9001P.",
                },
                {
                    "turn_id": "a2",
                    "role": "assistant",
                    "content": biol_body["answer"],
                },
            ],
            state=biol_body["conversation_state"],
        )

    body = followup.json()

    assert followup.status_code == 200
    assert body["status"] == "insufficient_evidence"
    assert "BIOL9001P (2026)" in body["answer"]
    assert "COMP2200" not in body["answer"]
    assert (
        body["sources"][0]["record_id"]
        == "courses:course:BIOL9001P_2026"
    )


_QASIM_ALL_COURSE_RECORDS = tuple(
    (
        record.metadata_json.course_code,
        record.metadata_json.academic_year,
        record.record_id,
    )
    for record in repository().all_records()
    if record.metadata_json.entity_type == "course"
)


@pytest.mark.parametrize(
    "course_code,academic_year,record_id",
    _QASIM_ALL_COURSE_RECORDS,
)
def test_every_frozen_course_record_roundtrips_through_conversation_state(
    course_code,
    academic_year,
    record_id,
):
    question = f"Tell me about {course_code} in {academic_year}."

    with TestClient(create_app(repository=repository())) as client:
        first = ask(
            client,
            question,
        )
        first_body = first.json()

        assert first.status_code == 200
        assert first_body["status"] == "ok"
        assert f"{course_code} ({academic_year})" in first_body["answer"]

        assert len(first_body["sources"]) == 1
        assert first_body["sources"][0]["record_id"] == record_id

        retained = first_body["conversation_state"]["recent_entities"][0]
        assert retained["canonical_id"] == course_code
        assert retained["source_record_id"] == record_id

        followup = ask(
            client,
            "What are its prerequisites?",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": question,
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": first_body["answer"],
                },
            ],
            state=first_body["conversation_state"],
        )

    followup_body = followup.json()

    assert followup.status_code == 200
    assert followup_body["status"] in {
        "ok",
        "insufficient_evidence",
    }
    assert followup_body["clarification"] is None
    assert len(followup_body["sources"]) == 1
    assert followup_body["sources"][0]["record_id"] == record_id

    retained_after = (
        followup_body["conversation_state"]["recent_entities"][0]
    )
    assert retained_after["canonical_id"] == course_code
    assert retained_after["source_record_id"] == record_id


@pytest.mark.parametrize(
    "refinement",
    (
        "What about 2027?",
        "How about 2027?",
        "And 2027?",
    ),
)
def test_absolute_year_only_refinement_replaces_course_year(refinement):
    with TestClient(create_app(repository=repository())) as client:
        first = ask(
            client,
            "Tell me about COMP1100 in 2026.",
        )
        first_body = first.json()

        assert first_body["status"] == "ok"
        assert "COMP1100 (2026)" in first_body["answer"]

        second = ask(
            client,
            refinement,
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about COMP1100 in 2026.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": first_body["answer"],
                },
            ],
            state=first_body["conversation_state"],
        )
        second_body = second.json()

        assert second.status_code == 200
        assert second_body["status"] == "ok"
        assert "COMP1100 (2027)" in second_body["answer"]
        assert second_body["clarification"] is None
        assert (
            second_body["sources"][0]["record_id"]
            == "courses:course:COMP1100_2027"
        )

        retained = second_body["conversation_state"]["recent_entities"][0]
        assert retained["canonical_id"] == "COMP1100"
        assert (
            retained["source_record_id"]
            == "courses:course:COMP1100_2027"
        )

        followup = ask(
            client,
            "What are its prerequisites?",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about COMP1100 in 2026.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": first_body["answer"],
                },
                {
                    "turn_id": "u2",
                    "role": "user",
                    "content": refinement,
                },
                {
                    "turn_id": "a2",
                    "role": "assistant",
                    "content": second_body["answer"],
                },
            ],
            state=second_body["conversation_state"],
        )

    followup_body = followup.json()

    assert followup.status_code == 200
    assert followup_body["status"] == "insufficient_evidence"
    assert "COMP1100 (2027)" in followup_body["answer"]
    assert (
        followup_body["sources"][0]["record_id"]
        == "courses:course:COMP1100_2027"
    )


def test_absolute_year_only_correction_can_move_back_to_2026():
    with TestClient(create_app(repository=repository())) as client:
        first = ask(
            client,
            "Tell me about COMP1100 in 2027.",
        )
        first_body = first.json()

        second = ask(
            client,
            "Actually, 2026.",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about COMP1100 in 2027.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": first_body["answer"],
                },
            ],
            state=first_body["conversation_state"],
        )

    body = second.json()

    assert second.status_code == 200
    assert body["status"] == "ok"
    assert "COMP1100 (2026)" in body["answer"]
    assert (
        body["sources"][0]["record_id"]
        == "courses:course:COMP1100_2026"
    )

    retained = body["conversation_state"]["recent_entities"][0]
    assert retained["canonical_id"] == "COMP1100"
    assert (
        retained["source_record_id"]
        == "courses:course:COMP1100_2026"
    )


def test_relative_year_is_not_silently_interpreted_as_absolute_year():
    with TestClient(create_app(repository=repository())) as client:
        first = ask(
            client,
            "Tell me about COMP1100 in 2026.",
        )
        first_body = first.json()

        relative = ask(
            client,
            "What about next year?",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about COMP1100 in 2026.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": first_body["answer"],
                },
            ],
            state=first_body["conversation_state"],
        )
        relative_body = relative.json()

        assert relative.status_code == 200
        assert relative_body["status"] != "ok"
        assert not relative_body["sources"]

        retained = relative_body["conversation_state"]["recent_entities"][0]
        assert retained["canonical_id"] == "COMP1100"
        assert (
            retained["source_record_id"]
            == "courses:course:COMP1100_2026"
        )

        followup = ask(
            client,
            "What are its prerequisites?",
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about COMP1100 in 2026.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": first_body["answer"],
                },
                {
                    "turn_id": "u2",
                    "role": "user",
                    "content": "What about next year?",
                },
                {
                    "turn_id": "a2",
                    "role": "assistant",
                    "content": relative_body["answer"],
                },
            ],
            state=relative_body["conversation_state"],
        )

    body = followup.json()

    assert body["status"] == "insufficient_evidence"
    assert "COMP1100 (2026)" in body["answer"]
    assert (
        body["sources"][0]["record_id"]
        == "courses:course:COMP1100_2026"
    )


def test_explicit_course_lecturer_request_is_not_downgraded_to_overview():
    with TestClient(create_app(repository=repository())) as client:
        response = ask(
            client,
            "Tell me about COMP1110. Who is the lecturer?",
        )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "insufficient_evidence"
    assert (
        body["answer"]
        == "The stored evidence does not establish the requested information."
    )
    assert len(body["sources"]) == 1
    assert (
        body["sources"][0]["record_id"]
        == "courses:course:COMP1110_2026"
    )
    assert "Stored excerpt:" not in body["answer"]


@pytest.mark.parametrize(
    "question",
    (
        "Who is the lecturer?",
        "Who is the convenor?",
        "Who is the instructor?",
        "Who teaches it?",
    ),
)
def test_teaching_staff_followup_keeps_course_but_abstains(question):
    with TestClient(create_app(repository=repository())) as client:
        first = ask(
            client,
            "Tell me about COMP1110.",
        )
        first_body = first.json()

        response = ask(
            client,
            question,
            history=[
                {
                    "turn_id": "u1",
                    "role": "user",
                    "content": "Tell me about COMP1110.",
                },
                {
                    "turn_id": "a1",
                    "role": "assistant",
                    "content": first_body["answer"],
                },
            ],
            state=first_body["conversation_state"],
        )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "insufficient_evidence"
    assert (
        body["answer"]
        == "The stored evidence does not establish the requested information."
    )
    assert len(body["sources"]) == 1
    assert (
        body["sources"][0]["record_id"]
        == "courses:course:COMP1110_2026"
    )


def test_descriptive_course_teaches_query_is_not_mistaken_for_staff_lookup():
    with TestClient(create_app(repository=repository())) as client:
        response = ask(
            client,
            "Which course teaches structured programming "
            "and programming fundamentals in 2026?",
        )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert "COMP1110 (2026)" in body["answer"]
    assert any(
        source["record_id"] == "courses:course:COMP1110_2026"
        for source in body["sources"]
    )
