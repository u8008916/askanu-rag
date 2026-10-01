"""R6 explicit hard constraints must be applied or reported, never erased."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from askanu_rag.interpretation import interpret_turn
from askanu_rag.main import create_app
from askanu_rag.models import ConstraintSemanticType, ConversationState, Domain
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


def _explicit_values(
    question: str,
    semantic_type: ConstraintSemanticType,
) -> list[str]:
    interpretation = interpret_turn(question, (), ConversationState())
    return [
        str(item.value)
        for item in interpretation.explicit_constraints.items
        if item.semantic_type == semantic_type
    ]


@pytest.mark.parametrize(
    ("question", "expected_location", "expected_ids"),
    (
        ("Are there jobs around Canberra?", "canberra", ["810001"]),
        ("Do you have jobs in Canberra?", "canberra", ["810001"]),
        ("Do you know about jobs in Canberra?", "canberra", ["810001"]),
        ("What about jobs in Canberra?", "canberra", ["810001"]),
        ("Show me jobs", None, ["810001", "810002"]),
        ("Show me jobs at ANU", None, ["810001", "810002"]),
        ("Show me any jobs at ANU", None, ["810001", "810002"]),
    ),
)
def test_r6_conversational_job_requests_route_to_discovery(
    question: str,
    expected_location: str | None,
    expected_ids: list[str],
) -> None:
    interpretation = interpret_turn(question, (), ConversationState())

    assert interpretation.domain == Domain.JOBS
    assert interpretation.intent is not None
    assert interpretation.intent.name == "discover"
    assert interpretation.intent.operation == "initial_discovery"
    assert _explicit_values(question, ConstraintSemanticType.LOCATION) == (
        [expected_location] if expected_location is not None else []
    )
    assert _explicit_values(question, ConstraintSemanticType.EMPLOYMENT_TYPE) == []

    body = _ask(JOBS, question)

    assert body["status"] == "ok"
    assert body["answer_state"] == "PARTIAL"
    assert [item["canonical_id"] for item in body["items"]] == expected_ids
    result_set = body["conversation_state"]["result_sets"][-1]
    assert result_set["domain"] == Domain.JOBS.value
    assert result_set["status"] == "RESULTS"
    assert result_set["ordered_canonical_ids"] == expected_ids


@pytest.mark.parametrize(
    ("question", "employment_type", "location", "expected_ids"),
    (
        ("Any casual jobs in Canberra?", "casual", "canberra", []),
        ("Show me full-time jobs in Canberra", "full-time", "canberra", []),
        (
            "What jobs are available at ANU in Canberra?",
            None,
            "canberra",
            ["810001"],
        ),
    ),
)
def test_r6_conversational_routing_preserves_real_job_constraints(
    question: str,
    employment_type: str | None,
    location: str,
    expected_ids: list[str],
) -> None:
    assert _explicit_values(question, ConstraintSemanticType.EMPLOYMENT_TYPE) == (
        [employment_type] if employment_type is not None else []
    )
    assert _explicit_values(question, ConstraintSemanticType.LOCATION) == [location]

    body = _ask(JOBS, question)

    assert [item["canonical_id"] for item in body["items"]] == expected_ids
    if expected_ids:
        assert body["status"] == "ok"
    else:
        assert body["status"] == "insufficient_evidence"
        assert "population is incomplete" in body["answer"]
    result_set = body["conversation_state"]["result_sets"][-1]
    assert result_set["domain"] == Domain.JOBS.value
    assert result_set["status"] == ("RESULTS" if expected_ids else "INCOMPLETE")


@pytest.mark.parametrize(
    ("question", "expected_domain", "expected_location"),
    (
        ("Tell me about accommodation", Domain.ACCOMMODATION, None),
        ("What about events in Canberra?", Domain.EVENTS, "canberra"),
        ("Show me scholarships", Domain.SCHOLARSHIPS, None),
        ("Do you know about COMP1110?", Domain.COURSES, None),
    ),
)
def test_r6_conversational_job_routing_does_not_hijack_other_domains(
    question: str,
    expected_domain: Domain,
    expected_location: str | None,
) -> None:
    interpretation = interpret_turn(question, (), ConversationState())

    assert interpretation.domain == expected_domain
    assert _explicit_values(question, ConstraintSemanticType.LOCATION) == (
        [expected_location] if expected_location is not None else []
    )
    assert _explicit_values(question, ConstraintSemanticType.EMPLOYMENT_TYPE) == []


@pytest.mark.parametrize(
    ("question", "expected_location", "expected_id"),
    (
        ("jobs at ANU in Canberra", "canberra", "810001"),
        ("jobs available at ANU in Canberra", "canberra", "810001"),
        ("any jobs at ANU in Canberra", "canberra", "810001"),
        ("jobs at ANU in Sydney", "sydney", None),
        ("jobs at ANU in Antarctica", "antarctica", None),
    ),
)
def test_r6_job_location_stops_at_institutional_anu_scope(
    question: str,
    expected_location: str,
    expected_id: str | None,
) -> None:
    body = _ask(JOBS, question)

    retained = _constraint(body, ConstraintSemanticType.LOCATION)
    assert retained["value"].casefold() == expected_location
    assert _explicit_values(question, ConstraintSemanticType.LOCATION) == [
        expected_location
    ]
    assert _explicit_values(question, ConstraintSemanticType.EMPLOYMENT_TYPE) == []
    if expected_id is not None:
        assert body["status"] == "ok"
        assert [item["canonical_id"] for item in body["items"]] == [expected_id]
    else:
        assert body["status"] == "insufficient_evidence"
        assert body["items"] == []


@pytest.mark.parametrize(
    ("question", "expected_location", "expected_id"),
    (
        ("Any jobs in Canberra?", "canberra", "810001"),
        ("Tell me about jobs in Canberra", "canberra", "810001"),
        ("What about jobs in Sydney?", "sydney", None),
    ),
)
def test_r6_job_query_words_are_not_employment_types(
    question: str,
    expected_location: str,
    expected_id: str | None,
) -> None:
    body = _ask(JOBS, question)

    assert _explicit_values(question, ConstraintSemanticType.EMPLOYMENT_TYPE) == []
    assert _constraint(body, ConstraintSemanticType.LOCATION)["value"].casefold() == (
        expected_location
    )
    if expected_id is not None:
        assert body["status"] == "ok"
        assert [item["canonical_id"] for item in body["items"]] == [expected_id]
    else:
        assert body["status"] == "insufficient_evidence"
        assert body["items"] == []


@pytest.mark.parametrize(
    ("question", "employment_type", "location", "expected_id"),
    (
        ("Are there any casual jobs in Canberra?", "casual", "canberra", None),
        ("Tell me about full-time jobs in Canberra", "full-time", "canberra", None),
        ("casual jobs in Melbourne", "casual", "melbourne", "810002"),
        ("full-time jobs in Sydney", "full-time", "sydney", None),
    ),
)
def test_r6_real_job_modifiers_survive_query_word_rejection(
    question: str,
    employment_type: str,
    location: str,
    expected_id: str | None,
) -> None:
    body = _ask(JOBS, question)

    assert _explicit_values(question, ConstraintSemanticType.EMPLOYMENT_TYPE) == [
        employment_type
    ]
    assert _explicit_values(question, ConstraintSemanticType.LOCATION) == [location]
    assert _constraint(body, ConstraintSemanticType.EMPLOYMENT_TYPE)[
        "value"
    ].casefold() == employment_type
    assert _constraint(body, ConstraintSemanticType.LOCATION)["value"].casefold() == (
        location
    )
    if expected_id is not None:
        assert body["status"] == "ok"
        assert [item["canonical_id"] for item in body["items"]] == [expected_id]
    else:
        assert body["status"] == "insufficient_evidence"
        assert body["items"] == []


@pytest.mark.parametrize(
    ("question", "expected_location"),
    (
        ("Tell me about accommodation in Canberra", "canberra"),
        ("Tell me about events in Canberra", "canberra"),
        ("Tell me about accommodation", None),
        ("Tell me about events", None),
    ),
)
def test_r6_shared_location_parser_rejects_cross_domain_query_words(
    question: str,
    expected_location: str | None,
) -> None:
    assert _explicit_values(question, ConstraintSemanticType.LOCATION) == (
        [expected_location] if expected_location is not None else []
    )
    assert _explicit_values(question, ConstraintSemanticType.EMPLOYMENT_TYPE) == []


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


def test_remote_jobs_are_unverifiable_not_an_employment_type_or_zero_match() -> None:
    body = _ask(JOBS, "What remote jobs are available?")

    assert body["status"] == "insufficient_evidence"
    assert body["items"] == []
    assert all(
        not (
            item["semantic_type"] == "employment_type"
            and str(item["value"]).casefold() == "remote"
        )
        for item in body["conversation_state"]["constraints"]["items"]
    )
    assert "cannot reliably apply or verify" in body["answer"]
    assert "population is incomplete" in body["answer"]
    assert "does not establish that no remote ANU jobs exist" in body["answer"]


def test_missing_job_locations_make_location_constraint_unreliable() -> None:
    records = tuple(
        record.model_copy(
            update={
                "metadata_json": record.metadata_json.model_copy(
                    update={"location": None}
                )
            }
        )
        for record in JOBS
    )

    body = _ask(records, "What jobs are available in Canberra?")

    assert body["status"] == "insufficient_evidence"
    assert body["items"] == []
    assert "cannot reliably evaluate that location" in body["answer"]
    assert "population is incomplete" in body["answer"]
    assert "does not establish that no such ANU jobs exist" in body["answer"]
    assert body["conversation_state"]["result_sets"][-1]["status"] == "INCOMPLETE"


def test_source_backed_job_location_still_matches_with_missing_peer_values() -> None:
    located = JOBS[0].model_copy(
        update={
            "metadata_json": JOBS[0].metadata_json.model_copy(
                update={"location": "Canberra / ACT, ACT, Australia, 2601"}
            )
        }
    )
    missing = JOBS[1].model_copy(
        update={
            "metadata_json": JOBS[1].metadata_json.model_copy(
                update={"location": None}
            )
        }
    )

    body = _ask((located, missing), "What jobs are available in Canberra?")

    assert body["status"] == "ok"
    assert [item["canonical_id"] for item in body["items"]] == [located.entity_id]
    assert body["items"][0]["location"] == (
        "Canberra / ACT, ACT, Australia, 2601"
    )
    assert "population is incomplete" in body["answer"]


def test_job_classification_shorthand_maps_only_to_matching_officer_level() -> None:
    anu08 = JOBS[0].model_copy(
        update={
            "metadata_json": JOBS[0].metadata_json.model_copy(
                update={"classification": "ANU Officer 8 (Administration)"}
            )
        }
    )
    anu09 = JOBS[1].model_copy(
        update={
            "metadata_json": JOBS[1].metadata_json.model_copy(
                update={"classification": "ANU Officer 9 (Administration)"}
            )
        }
    )

    shorthand = _ask((anu08, anu09), "What ANU08 jobs are available?")
    adjacent = _ask((anu08, anu09), "What ANU09 jobs are available?")
    direct = _ask(
        (anu08, anu09),
        "What jobs have classification ANU Officer 8 (Administration)?",
    )
    invalid = _ask((anu08, anu09), "What ANU8X jobs are available?")

    assert [item["canonical_id"] for item in shorthand["items"]] == [anu08.entity_id]
    assert shorthand["items"][0]["classification"] == (
        "ANU Officer 8 (Administration)"
    )
    assert [item["canonical_id"] for item in adjacent["items"]] == [anu09.entity_id]
    assert [item["canonical_id"] for item in direct["items"]] == [anu08.entity_id]
    assert invalid["status"] == "insufficient_evidence"
    assert invalid["items"] == []


def test_r6_event_impossible_location_is_not_silently_discarded() -> None:
    records = (event("constraint-event", day=14, hour=12, venue="Kambri"),)

    body = _ask(records, "What events are in Antarctica?")

    retained = _constraint(body, ConstraintSemanticType.LOCATION)
    assert retained["value"].casefold() == "antarctica"
    assert body["status"] == "insufficient_evidence"
    assert body["items"] == []
    assert "constraints" in body["answer"].casefold()

