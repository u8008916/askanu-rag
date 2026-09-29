"""R6 explicit hard constraints must be applied or reported, never erased."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from askanu_rag.main import create_app
from askanu_rag.models import ConstraintSemanticType
from askanu_rag.retrieval import CourseProgramRepository
from test_v7_day4_accommodation_vertical import ALPHA, BRAVO
from test_v7_day6_journeys import NOW, TODAY, event, job


def _job_record(
    identifier: str,
    *,
    location: str,
    employment_types: list[str],
    classification: str,
):
    record = job(identifier, title=f"Constraint Role {identifier}")
    metadata = record.metadata_json.model_copy(
        update={
            "location": location,
            "employment_types": employment_types,
            "classification": classification,
        }
    )
    return record.model_copy(update={"metadata_json": metadata})


JOBS = (
    _job_record(
        "810001",
        location="Canberra / ACT",
        employment_types=["Fixed-term"],
        classification="ANU08",
    ),
    _job_record(
        "810002",
        location="Melbourne / VIC",
        employment_types=["Casual"],
        classification="ANU05",
    ),
)


def _ask(records, question: str) -> dict:
    with TestClient(
        create_app(
            CourseProgramRepository(records),
            jobs_today_provider=lambda: TODAY,
            events_now_provider=lambda: NOW,
        )
    ) as client:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": question,
                "history": [],
                "conversation_state": {},
            },
        )
    assert response.status_code == 200, response.text
    return response.json()


def _constraint(body: dict, semantic_type: ConstraintSemanticType) -> dict:
    return next(
        item
        for item in body["conversation_state"]["constraints"]["items"]
        if item["semantic_type"] == semantic_type.value
    )


@pytest.mark.parametrize(
    ("question", "semantic_type", "value", "expected_id", "classification"),
    (
        (
            "What jobs are available in Melbourne?",
            ConstraintSemanticType.LOCATION,
            "Melbourne",
            "810002",
            "APPLIED_MATCH",
        ),
        (
            "What jobs are available in Sydney?",
            ConstraintSemanticType.LOCATION,
            "Sydney",
            None,
            "APPLIED_NO_SUPPORTED_MATCH",
        ),
        (
            "What jobs are available in Antarctica?",
            ConstraintSemanticType.LOCATION,
            "Antarctica",
            None,
            "APPLIED_NO_SUPPORTED_MATCH",
        ),
        (
            "What casual jobs are available?",
            ConstraintSemanticType.EMPLOYMENT_TYPE,
            "casual",
            "810002",
            "APPLIED_MATCH",
        ),
        (
            "What full-time jobs are available?",
            ConstraintSemanticType.EMPLOYMENT_TYPE,
            "full-time",
            None,
            "APPLIED_NO_SUPPORTED_MATCH",
        ),
        (
            "What remote jobs are available?",
            ConstraintSemanticType.EMPLOYMENT_TYPE,
            "remote",
            None,
            "APPLIED_NO_SUPPORTED_MATCH",
        ),
        (
            "What ANU99 jobs are available?",
            ConstraintSemanticType.CATEGORY,
            "ANU99",
            None,
            "APPLIED_NO_SUPPORTED_MATCH",
        ),
    ),
)
def test_r6_job_hard_constraint_is_retained_and_never_returns_unconstrained(
    question: str,
    semantic_type: ConstraintSemanticType,
    value: str,
    expected_id: str | None,
    classification: str,
) -> None:
    body = _ask(JOBS, question)

    retained = _constraint(body, semantic_type)
    assert str(retained["value"]).casefold() == value.casefold()
    if classification == "APPLIED_MATCH":
        assert body["status"] == "ok"
        assert [item["canonical_id"] for item in body["items"]] == [expected_id]
    else:
        assert body["status"] == "insufficient_evidence"
        assert body["items"] == []
        assert "population is incomplete" in body["answer"]
        assert "does not establish that no such ANU jobs exist" in body["answer"]


def test_r6_accommodation_impossible_location_is_not_silently_discarded() -> None:
    body = _ask((ALPHA, BRAVO), "Show me accommodation in Antarctica")

    retained = _constraint(body, ConstraintSemanticType.LOCATION)
    assert retained["value"].casefold() == "antarctica"
    assert body["status"] == "insufficient_evidence"
    assert body["items"] == []
    assert "cannot truthfully report no matches" in body["answer"]


def test_r6_event_impossible_location_is_not_silently_discarded() -> None:
    records = (event("constraint-event", day=14, hour=12, venue="Kambri"),)

    body = _ask(records, "What events are in Antarctica?")

    retained = _constraint(body, ConstraintSemanticType.LOCATION)
    assert retained["value"].casefold() == "antarctica"
    assert body["status"] == "insufficient_evidence"
    assert body["items"] == []
    assert "constraints" in body["answer"].casefold()

