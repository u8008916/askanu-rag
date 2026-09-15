"""Day 10 frozen Jobs contract and deterministic retrieval behavior."""

import hashlib
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

import askanu_rag.job_queries as job_queries
from askanu_rag.main import create_app
from askanu_rag.models import AskResponse, CommonRecord, JobMetadata, JobRecord
from askanu_rag.retrieval import (
    CourseProgramRepository,
    UnavailableCourseProgramRepository,
    load_common_records,
)
from askanu_rag.retrieval.vector import VectorHit

TODAY = date(2026, 9, 14)
SCHOLARSHIP_FIXTURE = (
    Path(__file__).parents[1] / "fixtures/day9_scholarship_records.json"
)


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
    role_requirements: list[str] | None = None,
    category: str | None = None,
    location: str | None = "Canberra / ACT",
    classification: str | None = "ANU Officer 6/7",
    salary: str | None = "$95,000 - $105,000",
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
            category=category,
            employment_types=list(employment_types),
            location=location,
            classification=classification,
            salary=salary,
            closing_text=(
                f"Closes {closing_date}" if closing_date is not None else None
            ),
            closing_date=closing_date,
            closing_at=closing_at,
            status=status,
            summary="Synthetic unit-test role.",
            role_requirements=role_requirements,
        ),
    )


def ask(repo, question: str, *, pending=None, history=(), vector=None):
    with TestClient(
        create_app(
            repo,
            jobs_today_provider=lambda: TODAY,
            vector_retriever=vector,
        )
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


def test_job_metadata_has_exact_approved_v2_keys_and_missing_values():
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
        "role_requirements",
    }
    assert metadata.category is None
    assert metadata.employment_types == []
    assert metadata.closing_date is None
    assert metadata.closing_at is None
    assert metadata.role_requirements is None


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


def test_pending_scholarship_scope_releases_explicit_jobs_with_filter_words():
    job = make_job("123456")
    repo = CourseProgramRepository(
        (*load_common_records(SCHOLARSHIP_FIXTURE), job)
    )
    broad = ask(repo, "What scholarships can I apply for?")

    body = ask(
        repo,
        "What jobs are available for international undergraduate students?",
        pending=broad["clarification"],
    )

    assert broad["clarification"]["id"] == "clar-scholarship-scope"
    assert body["status"] == "ok"
    assert [source["record_id"] for source in body["sources"]] == [job.record_id]
    assert body["items"][0]["job_id"] == job.entity_id
    assert "eligible" not in body["answer"].casefold()


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


def test_ben_exact_requirements_prompt_without_selected_job_clarifies():
    body = ask(
        CourseProgramRepository([]),
        "What are the requirements for this ANU job?",
    )

    assert body["status"] == "needs_clarification"
    assert body["answer"] == "Which job role do you mean?"
    assert body["clarification"]["id"] == "clar-job-missing-role"
    assert body["sources"] == []
    assert "requirement" not in body["answer"].casefold()


def test_selected_job_without_requirements_returns_grounded_insufficient_evidence():
    job = make_job("563693", title="Senior Consultant")

    body = ask(
        CourseProgramRepository([job]),
        "What are the requirements for this ANU job?",
        history=(
            {
                "turn_id": "t1",
                "role": "assistant",
                "content": "Senior Consultant. Job ID: 563693.",
            },
        ),
    )

    assert body["status"] == "insufficient_evidence"
    assert body["sources"] == [
        {
            "record_id": job.record_id,
            "source_id": job.source_id,
            "title": job.title,
            "url": str(job.canonical_url),
            "domain": job.domain,
        }
    ]
    answer = body["answer"].casefold()
    assert "does not contain direct-page" in answer
    assert "official job listing" in answer
    for unsupported in (
        job.metadata_json.classification,
        job.metadata_json.salary,
        *job.metadata_json.employment_types,
        "eligible",
        "qualified",
        "suitable",
    ):
        assert unsupported.casefold() not in answer


def test_direct_page_role_requirements_are_returned_verbatim_with_source():
    job = make_job(
        "563412",
        title="Capability Lead",
        role_requirements=[
            "Demonstrated experience leading agile practice.",
            "Strong stakeholder communication skills.",
        ],
    )

    body = ask(
        CourseProgramRepository([job]),
        "What are the requirements for job 563412?",
    )

    assert body["status"] == "ok"
    assert body["sources"][0]["record_id"] == job.record_id
    assert "Demonstrated experience leading agile practice." in body["answer"]
    assert "Strong stakeholder communication skills." in body["answer"]


def test_current_hybrid_jobs_hard_filter_excludes_closed_semantic_match():
    current = make_job("563556", title="Cybersecurity Network Engineer")
    closed = make_job(
        "563557",
        title="Closed Cybersecurity Architect",
        status="closed",
        closing_date="2026-09-30",
    )

    class FixedVector:
        def search(self, _question, *, domain, allowed_records, **_kwargs):
            from askanu_rag.retrieval.vector import VectorHit

            assert domain == "jobs"
            assert current in allowed_records
            assert closed not in allowed_records
            return (VectorHit(current, 0.9, ("whole",)),)

    body = ask(
        CourseProgramRepository([current, closed]),
        "Are there current jobs related to cybersecurity or networks?",
        vector=FixedVector(),
    )

    assert body["status"] == "ok"
    assert [item["job_id"] for item in body["items"]] == ["563556"]
    assert all(source["record_id"] != closed.record_id for source in body["sources"])


@pytest.mark.parametrize(
    "latest_history",
    [
        {"turn_id": "t2", "role": "user", "content": "Tell me about parking."},
        {
            "turn_id": "t2",
            "role": "assistant",
            "content": "Job ID: 563693 or Job ID: 563694.",
        },
    ],
)
def test_referential_job_does_not_reuse_unrelated_or_ambiguous_history(
    latest_history,
):
    body = ask(
        CourseProgramRepository(
            [make_job("563693"), make_job("563694", title="Second role")]
        ),
        "What are the requirements for this ANU job?",
        history=(
            {
                "turn_id": "t1",
                "role": "assistant",
                "content": "Research Officer. Job ID: 563693.",
            },
            latest_history,
        ),
    )

    assert body["status"] == "needs_clarification"
    assert body["answer"] == "Which job role do you mean?"
    assert body["sources"] == []


def test_canberra_today_and_current_jobs_follow_canberra_midnight(monkeypatch):
    utc_instant = datetime(2026, 9, 14, 14, 30, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is not None
            return utc_instant.astimezone(tz)

    monkeypatch.setattr(job_queries, "datetime", FixedDateTime)
    assert job_queries.canberra_today() == date(2026, 9, 15)

    closing_today = make_job("1", closing_date="2026-09-15")
    closed_yesterday = make_job("2", closing_date="2026-09-14")
    client = TestClient(
        create_app(CourseProgramRepository([closing_today, closed_yesterday]))
    )

    response = client.get("/api/v1/jobs/current?limit=20")

    assert response.status_code == 200
    assert [item["job_id"] for item in response.json()["items"]] == ["1"]


def test_semantic_current_jobs_rank_over_complete_hard_filtered_pool():
    current = [
        make_job(str(100000 + index), title=f"Current Role {index}")
        for index in range(1, 26)
    ]
    best = current[24]
    closed = make_job("100026", title="Closed Semantic Decoy", status="closed")

    class FixedVector:
        def search(self, _question, *, domain, allowed_records, **_kwargs):
            assert domain == "jobs"
            assert len(allowed_records) == 25
            assert best in allowed_records
            assert closed not in allowed_records
            return (
                VectorHit(closed, 0.99, ("whole",)),
                VectorHit(best, 0.98, ("whole",)),
            )

    body = ask(
        CourseProgramRepository([*current, closed]),
        "What current jobs are related to quantum computing?",
        vector=FixedVector(),
    )

    assert [item["record_id"] for item in body["items"]] == [best.record_id]
    assert closed.record_id not in {source["record_id"] for source in body["sources"]}

def test_status_null_without_deadline_is_never_promoted_to_current():
    unknown = make_job("55", status=None, closing_date=None)

    body = ask(CourseProgramRepository([unknown]), "Show me current ANU jobs")

    assert body["status"] == "insufficient_evidence"
    assert body["sources"] == []


@pytest.mark.parametrize(
    "question",
    [
        "Jobs related to cybersecurity",
        "What ANU jobs are about networks?",
        "Are there roles focused on machine learning?",
        "What ANU jobs involve data science?",
    ],
)
def test_general_topic_jobs_reach_semantic_current_retrieval(question):
    job = make_job("610001", title="Cybersecurity Data Engineer")

    class SemanticSpy:
        def __init__(self):
            self.calls = 0

        def search(self, query, *, domain, allowed_records, top_k, min_score):
            self.calls += 1
            assert query == question
            assert domain == "jobs"
            assert allowed_records == (job,)
            assert top_k == 10
            assert min_score == 0.2
            return (VectorHit(job, 0.9, ("whole",)),)

    vector = SemanticSpy()
    body = ask(CourseProgramRepository([job]), question, vector=vector)

    assert body["status"] == "ok"
    assert [item["job_id"] for item in body["items"]] == [job.entity_id]
    assert vector.calls == 1


@pytest.mark.parametrize("failure", ["unavailable", "error", "weak", "empty"])
def test_semantic_job_failure_never_falls_back_to_arbitrary_current_list(failure):
    first = make_job("610010", title="Unrelated First Current Job")
    second = make_job("610011", title="Unrelated Second Current Job")

    class FailingOrIrrelevantVector:
        def search(self, *_args, **_kwargs):
            if failure == "error":
                raise RuntimeError("semantic provider unavailable")
            if failure == "weak":
                return (VectorHit(first, 0.1, ("whole",)),)
            return ()

    vector = None if failure == "unavailable" else FailingOrIrrelevantVector()
    body = ask(
        CourseProgramRepository([first, second]),
        "What current ANU jobs are related to cybersecurity?",
        vector=vector,
    )

    assert body["status"] == "insufficient_evidence"
    assert body["items"] == []
    assert body["sources"] == []
    assert first.title not in body["answer"]


def test_structured_job_filters_use_only_explicit_stored_values():
    canberra_continuing = make_job(
        "610020",
        title="Canberra Continuing Role",
        employment_types=("Continuing",),
        location="Canberra / ACT",
        category="Information Technology",
        classification="ANU08",
        salary="$112,000 - $120,000 plus 17% superannuation",
    )
    sydney_casual = make_job(
        "610021",
        title="Sydney Casual Role",
        employment_types=("Casual",),
        location="Sydney / NSW",
        category="Administration",
        classification="ANU05",
        salary="$52.50 per hour",
    )
    repository = CourseProgramRepository([canberra_continuing, sydney_casual])

    cases = (
        ("Show me current jobs in Canberra", canberra_continuing),
        ("Show me current continuing jobs", canberra_continuing),
        ("Show me current casual jobs", sydney_casual),
        ("Show jobs with classification ANU08", canberra_continuing),
        ("Show current jobs in Information Technology", canberra_continuing),
        (
            "Show current jobs with salary $112,000 - $120,000 plus 17% superannuation",
            canberra_continuing,
        ),
    )
    for question, expected in cases:
        body = ask(repository, question)
        assert body["status"] == "ok", question
        assert [item["job_id"] for item in body["items"]] == [expected.entity_id]

    no_match = ask(repository, "Show me current jobs in Darwin")
    assert no_match["status"] == "insufficient_evidence"
    assert no_match["items"] == []
    assert no_match["sources"] == []


def test_closing_and_direct_role_requirement_filters_are_source_backed():
    matching = make_job(
        "610025",
        title="Source-backed Requirements Role",
        closing_date="2026-09-22",
        role_requirements=["Demonstrated Python security engineering experience."],
    )
    other = make_job(
        "610026",
        title="Other Role",
        closing_date="2026-09-29",
        role_requirements=["Demonstrated finance administration experience."],
    )
    repository = CourseProgramRepository([matching, other])

    by_closing = ask(repository, "Show current jobs closing 2026-09-22")
    by_requirement = ask(
        repository,
        "Show current jobs requiring Demonstrated Python security engineering experience.",
    )

    assert [item["job_id"] for item in by_closing["items"]] == [matching.entity_id]
    assert [item["job_id"] for item in by_requirement["items"]] == [matching.entity_id]


def test_structured_filters_remain_hard_inside_semantic_job_discovery():
    allowed = make_job(
        "610030",
        title="Canberra Security Engineer",
        location="Canberra / ACT",
        employment_types=("Continuing",),
    )
    disallowed_location = make_job(
        "610031",
        title="Sydney Security Engineer",
        location="Sydney / NSW",
        employment_types=("Continuing",),
    )
    closed = make_job(
        "610032",
        title="Closed Canberra Security Architect",
        status="closed",
        location="Canberra / ACT",
        employment_types=("Continuing",),
    )

    class FixedVector:
        def search(self, _question, *, domain, allowed_records, **_kwargs):
            assert domain == "jobs"
            assert allowed_records == (allowed,)
            return (
                VectorHit(closed, 1.0, ("whole",)),
                VectorHit(disallowed_location, 0.99, ("whole",)),
                VectorHit(allowed, 0.9, ("whole",)),
            )

    body = ask(
        CourseProgramRepository([allowed, disallowed_location, closed]),
        "What current continuing jobs in Canberra are related to cybersecurity?",
        vector=FixedVector(),
    )

    assert body["status"] == "ok"
    assert [item["job_id"] for item in body["items"]] == [allowed.entity_id]


def test_unknown_in_constraint_blocks_semantic_jobs_before_vector_search():
    canberra = make_job(
        "610033",
        title="Canberra Cybersecurity Engineer",
        location="Canberra / ACT",
    )
    sydney = make_job(
        "610034",
        title="Sydney Cybersecurity Engineer",
        location="Sydney / NSW",
    )

    class MustNotRun:
        def __init__(self):
            self.calls = 0

        def search(self, *_args, **_kwargs):
            self.calls += 1
            return (VectorHit(canberra, 0.99, ("whole",)),)

    vector = MustNotRun()
    body = ask(
        CourseProgramRepository([canberra, sydney]),
        "What jobs in Darwin are related to cybersecurity?",
        vector=vector,
    )

    assert body["status"] == "insufficient_evidence"
    assert body["items"] == []
    assert body["sources"] == []
    assert canberra.title not in body["answer"]
    assert sydney.title not in body["answer"]
    assert vector.calls == 0


def test_expired_by_date_high_score_job_is_excluded_before_semantic_ranking():
    valid = make_job(
        "610035",
        title="Current Network Security Engineer",
        closing_date="2026-09-20",
    )
    expired = make_job(
        "610036",
        title="Expired Cybersecurity Architect",
        status="current",
        closing_date="2026-09-13",
    )

    class FixedVector:
        def search(self, _question, *, domain, allowed_records, **_kwargs):
            assert domain == "jobs"
            assert allowed_records == (valid,)
            return (
                VectorHit(expired, 0.99, ("whole",)),
                VectorHit(valid, 0.8, ("whole",)),
            )

    body = ask(
        CourseProgramRepository([valid, expired]),
        "What jobs are related to cybersecurity and network security?",
        vector=FixedVector(),
    )

    assert body["status"] == "ok"
    assert [item["job_id"] for item in body["items"]] == [valid.entity_id]
    assert expired.record_id not in {
        source["record_id"] for source in body["sources"]
    }


def test_exact_job_id_and_title_bypass_semantic_discovery():
    job = make_job("610040", title="Cybersecurity Research Officer")

    class MustNotRun:
        def __init__(self):
            self.calls = 0

        def search(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("exact Jobs lookup must precede semantic discovery")

    vector = MustNotRun()
    repository = CourseProgramRepository([job])

    by_id = ask(repository, "Tell me about job 610040", vector=vector)
    by_title = ask(repository, "Tell me about Cybersecurity Research Officer", vector=vector)

    assert by_id["sources"][0]["record_id"] == job.record_id
    assert by_title["sources"][0]["record_id"] == job.record_id
    assert vector.calls == 0


def test_generic_current_jobs_remain_deterministic_without_vector_relevance():
    first = make_job("610050", title="First", closing_date="2026-09-15")
    second = make_job("610051", title="Second", closing_date="2026-09-16")

    class MustNotRun:
        def __init__(self):
            self.calls = 0

        def search(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("generic current listing must not require vectors")

    vector = MustNotRun()
    body = ask(
        CourseProgramRepository([second, first]),
        "Show me current jobs",
        vector=vector,
    )

    assert body["status"] == "ok"
    assert [item["job_id"] for item in body["items"]] == ["610050", "610051"]
    assert vector.calls == 0
