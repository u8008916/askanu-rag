"""Day 3 HTTP integration tests for deterministic course prerequisites."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from askanu_rag.course_queries import classify_course_prerequisites_query
from askanu_rag.main import create_app
from askanu_rag.models import CourseMetadata, CourseProgramRecord
from askanu_rag.retrieval import (
    CourseProgramRepository,
    load_course_program_records,
)

FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "day2_course_program_records.json"
)


def ask_payload(question: str) -> dict[str, object]:
    return {
        "question": question,
        "history": [],
        "conversation_state": {"pending_clarification": None},
    }


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def build_source_supported_test_record() -> CourseProgramRecord:
    """Build explicit synthetic evidence for the success-path contract test."""

    content = (
        "Day 3 deterministic test course\n"
        "Course Code: TEST1234\n"
        "Academic Year: 2026\n"
        "Prerequisites: Source-supported prerequisite text"
    )
    observed_at = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
    return CourseProgramRecord(
        record_id="courses:course:TEST1234_2026",
        source_id="courses_programs_and_courses",
        entity_id="TEST1234_2026",
        domain="courses",
        title="Day 3 deterministic test course",
        content=content,
        canonical_url=(
            "https://programsandcourses.anu.edu.au/2026/course/TEST1234"
        ),
        status="NEW",
        effective_from=None,
        effective_to=None,
        collected_at=observed_at,
        last_seen_at=observed_at,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        embedding_version=None,
        index_status="PENDING",
        metadata_json=CourseMetadata(
            entity_type="course",
            course_code="TEST1234",
            academic_year="2026",
            prerequisites="Source-supported prerequisite text",
        ),
    )


@pytest.mark.parametrize(
    ("question", "expected_code", "expected_year"),
    [
        ("What are the prerequisites for COMP1110?", "COMP1110", None),
        ("Prerequisites for comp 1110", "COMP1110", None),
        ("Does BIOL9001P have prerequisites?", "BIOL9001P", None),
        ("Prerequisites for COMP1110 in 2026", "COMP1110", "2026"),
        ("Prerequisites for COMP2026", "COMP2026", None),
    ],
)
def test_classifier_extracts_normalized_course_and_explicit_year(
    question: str,
    expected_code: str,
    expected_year: str | None,
) -> None:
    query = classify_course_prerequisites_query(question)

    assert query is not None
    assert query.course_code == expected_code
    assert query.academic_year == expected_year


def test_classifier_rejects_questions_outside_the_day3_slice() -> None:
    assert classify_course_prerequisites_query("Tell me about COMP1110") is None
    assert (
        classify_course_prerequisites_query(
            "Compare prerequisites for COMP1100 and COMP1110"
        )
        is None
    )


def test_required_comp1110_request_uses_real_http_and_repository_path(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/ask",
        json=ask_payload("What are the prerequisites for COMP1110?"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_evidence"
    assert body["items"] == []
    assert body["clarification"] is None
    assert body["request_id"].startswith("req_")
    assert "does not establish its prerequisites" in body["answer"]
    assert body["sources"][0]["record_id"] == "courses:course:COMP1110_2026"


@pytest.mark.parametrize(
    "question",
    [
        "What are the prerequisites for COMP1110?",
        "What are the prerequisites for comp 1110?",
        "Prerequisites for COMP1110",
        "Does COMP1110 have prerequisites?",
    ],
)
def test_case_spacing_and_intent_variants_resolve_the_same_record(
    client: TestClient, question: str
) -> None:
    response = client.post("/api/v1/ask", json=ask_payload(question))

    assert response.status_code == 200
    assert response.json()["sources"][0]["record_id"] == (
        "courses:course:COMP1110_2026"
    )


def test_unknown_exact_course_returns_no_evidence_without_guessing(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/ask",
        json=ask_payload("What are the prerequisites for ABCD9999?"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_evidence"
    assert body["sources"] == []
    assert body["items"] == []
    assert "ABCD9999" in body["answer"]


def test_null_prerequisites_are_not_presented_as_no_prerequisites(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/ask",
        json=ask_payload("What are the prerequisites for COMP1110?"),
    )

    body = response.json()
    assert body["status"] == "insufficient_evidence"
    assert "no prerequisites" not in body["answer"].lower()
    assert "does not establish" in body["answer"].lower()


def test_grounded_success_and_source_fields_come_from_stored_record() -> None:
    record = build_source_supported_test_record()
    repository = CourseProgramRepository([record])
    client = TestClient(create_app(repository))

    response = client.post(
        "/api/v1/ask",
        json=ask_payload("What are the prerequisites for test 1234?"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["answer"].endswith("Source-supported prerequisite text")
    assert body["items"] == []
    assert body["sources"] == [
        {
            "record_id": record.record_id,
            "source_id": record.source_id,
            "title": record.title,
            "url": str(record.canonical_url),
            "domain": record.domain,
        }
    ]


def test_unresolved_multiple_academic_years_requires_clarification() -> None:
    records = load_course_program_records(FIXTURE_PATH)
    client = TestClient(create_app(CourseProgramRepository(records)))

    response = client.post(
        "/api/v1/ask",
        json=ask_payload("What are the prerequisites for COMP1100?"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_clarification"
    assert body["sources"] == []
    assert body["clarification"] == {
        "id": "clar-course-comp1100-academic-year",
        "type": "entity_selection",
        "options": [
            {
                "id": "courses:course:COMP1100_2026",
                "label": "COMP1100 (2026)",
            },
            {
                "id": "courses:course:COMP1100_2027",
                "label": "COMP1100 (2027)",
            },
        ],
        "allow_multiple": False,
    }


def test_explicit_academic_year_resolves_without_inference(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ask",
        json=ask_payload("What are the prerequisites for COMP1100 in 2026?"),
    )

    body = response.json()
    assert body["status"] == "insufficient_evidence"
    assert body["sources"][0]["record_id"] == "courses:course:COMP1100_2026"
    assert body["sources"][0]["url"] == (
        "https://programsandcourses.anu.edu.au/2026/course/COMP1100"
    )


def test_repository_failure_uses_controlled_error_envelope() -> None:
    class FailingRepository:
        def find_course_by_code(
            self, identifier: str, academic_year: str | None = None
        ) -> object:
            raise RuntimeError("private database diagnostics")

    client = TestClient(create_app(FailingRepository()), raise_server_exceptions=False)
    response = client.post(
        "/api/v1/ask",
        json=ask_payload("What are the prerequisites for COMP1110?"),
    )

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert body["answer"] == "The request could not be completed."
    assert body["items"] == []
    assert body["sources"] == []
    assert body["clarification"] is None
    assert "database" not in str(body).lower()
