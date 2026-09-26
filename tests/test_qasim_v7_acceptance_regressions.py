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
