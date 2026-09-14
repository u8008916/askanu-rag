"""Day 10 frozen Jobs contract and deterministic retrieval behavior."""

import hashlib
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from askanu_rag.main import create_app
from askanu_rag.models import AskResponse, CommonRecord, JobMetadata, JobRecord
from askanu_rag.retrieval import (
    CourseProgramRepository,
    UnavailableCourseProgramRepository,
)

TODAY = date(2026, 9, 14)


def make_job(
    entity_id: str = "123456",
    *,
    title: str = "Research Officer",
    status: str | None = "current",
    closing_date: str | None = "2026-09-27",
    closing_at: str | None = None,
    employment_types: tuple[str, ...] = ("Fixed Term",),
    index_status: str = "PENDING",
    url_slug: str | None = None,
) -> JobRecord:
    content = f"{title}\nJob ID: {entity_id}\nSource-supported test evidence"
    observed = datetime(2026, 9, 14, 2, 0, tzinfo=timezone.utc)
    return JobRecord(
        record_id=f"jobs:job:{entity_id}",
        source_id="jobs_anu_search",
        entity_id=entity_id,
        domain="jobs",
        title=title,
        content=content,
        canonical_url=(
            f"https://jobs.anu.edu.au/jobs/{url_slug or f'test-role-{entity_id}'}"
        ),
        status="NEW",
        effective_from=None,
        effective_to=None,
        collected_at=observed,
        last_seen_at=observed,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        embedding_version=None,
        index_status=index_status,
        metadata_json=JobMetadata(
            entity_type="job",
            job_id=entity_id,
            category=None,
            employment_types=list(employment_types),
            location="Canberra / ACT",
            classification="ANU Officer 6/7",
            salary="$95,000 - $105,000",
            closing_text=(
                f"Closes {closing_date}" if closing_date is not None else None
            ),
            closing_date=closing_date,
            closing_at=closing_at,
            status=status,
            summary="Synthetic unit-test role.",
        ),
    )


def ask(repo, question: str, *, pending=None, history=()):
    with TestClient(
        create_app(repo, jobs_today_provider=lambda: TODAY)
    ) as client:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": question,
                "history": list(history),
                "conversation_state": {"pending_clarification": pending},
            },
        )
    assert response.status_code == 200
    TypeAdapter(AskResponse).validate_python(response.json())
    assert set(response.json()) == {
        "status",
        "answer",
        "items",
        "sources",
        "clarification",
        "request_id",
    }
    return response.json()


def test_job_metadata_has_exact_frozen_twelve_keys_and_missing_values():
    metadata = make_job(closing_date=None, employment_types=()).metadata_json

    assert set(metadata.model_dump()) == {
        "entity_type",
        "job_id",
        "category",
        "employment_types",
        "location",
        "classification",
        "salary",
        "closing_text",
        "closing_date",
        "closing_at",
        "status",
        "summary",
    }
    assert metadata.category is None
    assert metadata.employment_types == []
    assert metadata.closing_date is None
    assert metadata.closing_at is None


def test_job_metadata_preserves_source_supported_timezone_aware_closing_at():
    value = "2026-09-27T23:55:00+10:00"

    assert make_job(closing_at=value).metadata_json.closing_at == value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("job_id", "abc"),
        ("status", "open"),
        ("status", "expired"),
        ("closing_date", "2026-02-30"),
        ("closing_date", "27/09/2026"),
        ("closing_at", "2026-09-27T23:55:00"),
        ("closing_at", "not-a-datetime"),
    ],
)
def test_job_metadata_rejects_values_outside_frozen_contract(field, value):
    values = make_job().model_dump(mode="python")
    values["metadata_json"][field] = value

    with pytest.raises(ValidationError):
        CommonRecord.model_validate(values)


def test_job_metadata_rejects_unknown_key_and_identity_mismatches():
    values = make_job().model_dump(mode="python")
    values["metadata_json"]["invented"] = "not approved"
    with pytest.raises(ValidationError):
        CommonRecord.model_validate(values)

    values = make_job().model_dump(mode="python")
    values["metadata_json"]["job_id"] = "654321"
    with pytest.raises(ValidationError):
        CommonRecord.model_validate(values)

    values = make_job().model_dump(mode="python")
    values["record_id"] = "jobs:job:654321"
    with pytest.raises(ValidationError):
        CommonRecord.model_validate(values)


@pytest.mark.parametrize(
    "canonical_url",
    [
        "http://jobs.anu.edu.au/jobs/research-officer",
        "HTTPS://jobs.anu.edu.au/jobs/research-officer",
        "https://JOBS.ANU.EDU.AU/jobs/research-officer",
        "https://jobs.anu.edu.au:443/jobs/research-officer",
        "https://jobs.anu.edu.au/jobs",
        "https://jobs.anu.edu.au/jobs/research-officer/",
        "https://jobs.anu.edu.au/jobs/research/officer",
        "https://jobs.anu.edu.au/jobs/research-officer?ref=search",
        "https://jobs.anu.edu.au/jobs/research-officer#details",
        "https://jobs.anu.edu.au/me",
        "https://example.com/jobs/research-officer",
    ],
)
def test_job_model_rejects_noncanonical_public_url(canonical_url):
    values = make_job().model_dump(mode="python")
    values["canonical_url"] = canonical_url

    with pytest.raises(ValidationError):
        JobRecord.model_validate(values)


@pytest.mark.parametrize("field", ["effective_from", "effective_to"])
def test_job_effective_dates_must_remain_null(field):
    values = make_job().model_dump(mode="python")
    values[field] = values["collected_at"]

    with pytest.raises(ValidationError):
        JobRecord.model_validate(values)


def test_repository_filters_orders_then_limits_with_numeric_id_tie_break():
    records = [
        make_job("10", title="Ten", closing_date="2026-09-20"),
        make_job("9", title="Nine", closing_date="2026-09-20"),
        make_job("2", title="Undated", closing_date=None),
        make_job("7", title="Closing today", closing_date="2026-09-14"),
        make_job("3", title="Expired", closing_date="2026-09-13"),
        make_job("4", title="Closed", status="closed", closing_date="2026-09-30"),
        make_job("5", title="Unknown", status=None, closing_date=None),
    ]
    repo = CourseProgramRepository(records)

    assert [record.entity_id for record in repo.current_jobs(20, TODAY)] == [
        "7",
        "9",
        "10",
        "2",
    ]
    assert [record.entity_id for record in repo.current_jobs(2, TODAY)] == ["7", "9"]
    assert [
        record.entity_id
        for record in repo.current_jobs(20, TODAY, employment_type="Fixed Term")
    ] == ["7", "9", "10", "2"]


def test_current_jobs_endpoint_contract_limits_and_stored_provenance():
    jobs = [
        make_job(str(number), closing_date=f"2026-09-{20 + number:02d}")
        for number in range(1, 7)
    ]
    client = TestClient(
        create_app(CourseProgramRepository(jobs), jobs_today_provider=lambda: TODAY)
    )

    default = client.get("/api/v1/jobs/current")
    limited = client.get("/api/v1/jobs/current?limit=1")

    assert default.status_code == 200
    assert len(default.json()["items"]) == 5
    assert set(default.json()) == {"status", "items", "request_id"}
    item = default.json()["items"][0]
    assert set(item) == {
        "record_id",
        "source_id",
        "job_id",
        "title",
        "employment_types",
        "location",
        "classification",
        "salary",
        "closing_text",
        "closing_date",
        "closing_at",
        "status",
        "url",
        "domain",
    }
    assert item["url"] == "https://jobs.anu.edu.au/jobs/test-role-1"
    assert limited.status_code == 200
    assert [item["job_id"] for item in limited.json()["items"]] == ["1"]


@pytest.mark.parametrize("limit", ["0", "-1", "not-an-integer", "21"])
def test_current_jobs_endpoint_rejects_invalid_or_unbounded_limit(limit):
    client = TestClient(create_app(CourseProgramRepository([])))

    response = client.get(f"/api/v1/jobs/current?limit={limit}")

    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_current_jobs_endpoint_fails_closed_when_repository_is_unavailable():
    client = TestClient(
        create_app(UnavailableCourseProgramRepository()),
        raise_server_exceptions=False,
    )

    response = client.get("/api/v1/jobs/current")

    assert response.status_code == 500
    assert response.json()["status"] == "error"
    assert set(response.json()) == {
        "status",
        "answer",
        "items",
        "sources",
        "clarification",
        "request_id",
    }


def test_chat_current_fixed_term_and_index_states_are_deterministic():
    pending = make_job("9", title="Pending role", index_status="PENDING")
    failed = make_job("10", title="Failed index role", index_status="FAILED")
    continuing = make_job(
        "11",
        title="Continuing role",
        employment_types=("Continuing",),
    )
    repo = CourseProgramRepository([pending, failed, continuing])

    body = ask(repo, "Are there any fixed-term jobs currently open?")

    assert body["status"] == "ok"
    assert [item["job_id"] for item in body["items"]] == ["9", "10"]
    assert [source["url"] for source in body["sources"]] == [
        str(pending.canonical_url),
        str(failed.canonical_url),
    ]


def test_chat_numeric_id_exact_title_and_current_status_use_fresh_records():
    current = make_job("123456")
    closed = make_job("98765", title="Closed Research Role", status="closed")
    repo = CourseProgramRepository([current, closed])

    by_id = ask(repo, "Tell me about job 123456")
    by_title = ask(repo, "Tell me about   research officer")
    closed_body = ask(repo, "Is Closed Research Role still current?")

    assert by_id["sources"][0]["record_id"] == current.record_id
    assert by_title["sources"][0]["record_id"] == current.record_id
    assert by_title["sources"][0]["url"] == str(current.canonical_url)
    assert closed_body["sources"][0]["record_id"] == closed.record_id
    assert "not current" in closed_body["answer"]


def test_duplicate_exact_title_clarifies_and_pending_selection_retrieves_fresh():
    first = make_job("9", title="Research Officer")
    second = make_job("10", title="  Research   Officer  ")
    repo = CourseProgramRepository([first, second])

    ambiguous = ask(repo, "Tell me about Research Officer")
    selected = ask(
        repo,
        "second",
        pending=ambiguous["clarification"],
    )

    assert ambiguous["status"] == "needs_clarification"
    assert [option["id"] for option in ambiguous["clarification"]["options"]] == [
        first.record_id,
        second.record_id,
    ]
    assert selected["status"] == "ok"
    assert selected["sources"][0]["record_id"] == second.record_id


def test_role_followup_uses_history_only_for_identity_then_retrieves_record():
    job = make_job("123456")
    body = ask(
        CourseProgramRepository([job]),
        "Is this role still current?",
        history=(
            {
                "turn_id": "t1",
                "role": "assistant",
                "content": "Research Officer. Job ID: 123456.",
            },
        ),
    )

    assert body["status"] == "ok"
    assert body["sources"][0]["record_id"] == job.record_id


def test_status_null_without_deadline_is_never_promoted_to_current():
    unknown = make_job("55", status=None, closing_date=None)

    body = ask(CourseProgramRepository([unknown]), "Show me current ANU jobs")

    assert body["status"] == "insufficient_evidence"
    assert body["sources"] == []
