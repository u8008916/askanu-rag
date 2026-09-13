"""Day 9 Scholarship shared-record and deterministic RAG behavior."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from askanu_rag.index_lifecycle import IndexAction, index_is_stale, plan_index_action
from askanu_rag.main import create_app
from askanu_rag.models import AskResponse, CommonRecord, ScholarshipRecord
from askanu_rag.retrieval import (
    CourseProgramRepository,
    load_common_records,
    load_course_program_records,
)

ROOT = Path(__file__).parents[1]
SCHOLARSHIP_FIXTURE = ROOT / "fixtures/day9_scholarship_records.json"
COURSE_FIXTURE = ROOT / "fixtures/day5_course_program_records.json"


@pytest.fixture
def scholarships() -> tuple[ScholarshipRecord, ...]:
    return tuple(
        ScholarshipRecord.model_validate(record.model_dump(mode="python"))
        for record in load_common_records(SCHOLARSHIP_FIXTURE)
    )


@pytest.fixture
def repo(scholarships):
    return CourseProgramRepository(
        (*load_course_program_records(COURSE_FIXTURE), *scholarships)
    )


def ask(repo, question, *, history=(), pending=None, vector=None):
    with TestClient(create_app(repo, semantic_retriever=vector)) as client:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": question,
                "history": list(history),
                "conversation_state": {"pending_clarification": pending},
            },
        )
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


def test_scholarship_metadata_deserializes_exact_keys_null_lists_and_iso_dates(
    scholarships,
):
    record = scholarships[1]
    metadata = record.metadata_json

    assert set(metadata.model_dump()) == {
        "entity_type",
        "featured",
        "status",
        "application_required",
        "study_stage",
        "student_type",
        "study_level",
        "area_of_study",
        "value",
        "selection_basis",
        "opening_date",
        "closing_date",
        "eligibility",
    }
    assert metadata.application_required is None
    assert metadata.value is None
    assert metadata.opening_date is None
    assert metadata.closing_date is None
    assert isinstance(scholarships[0].metadata_json.closing_date, str)
    assert scholarships[2].metadata_json.study_stage == []
    assert str(record.canonical_url).startswith("https://study.anu.edu.au/")


@pytest.mark.parametrize("invalid_date", ["31/10/2026", "2026-99-99"])
def test_scholarship_metadata_rejects_unknown_key_and_non_iso_date(
    scholarships, invalid_date
):
    values = scholarships[0].model_dump(mode="python")
    values["metadata_json"]["invented"] = "not approved"
    with pytest.raises(ValidationError):
        CommonRecord.model_validate(values)

    values = scholarships[0].model_dump(mode="python")
    values["metadata_json"]["closing_date"] = invalid_date
    with pytest.raises(ValidationError):
        CommonRecord.model_validate(values)


def test_scholarship_metadata_rejects_non_boolean_flags(scholarships):
    values = scholarships[0].model_dump(mode="python")
    values["metadata_json"]["featured"] = 1
    with pytest.raises(ValidationError):
        CommonRecord.model_validate(values)


def test_scholarship_identity_is_url_slug_not_title_or_year(scholarships):
    record = scholarships[0]
    assert record.entity_id == "day9-undergraduate-computing"
    assert record.record_id == (
        "scholarships:scholarship:day9-undergraduate-computing"
    )

    values = record.model_dump(mode="python")
    values["entity_id"] = "title-derived-2026"
    values["record_id"] = "scholarships:scholarship:title-derived-2026"
    with pytest.raises(ValidationError):
        ScholarshipRecord.model_validate(values)


@pytest.mark.parametrize(
    ("entity_id", "different_url_slug"),
    [
        ("foo.*", "foo-123"),
        ("foo|bar", "bar"),
        ("foo[0-9]", "foo7"),
        ("foo+", "fooo"),
        ("foo?", "fo"),
    ],
)
def test_model_rejects_regex_like_entity_id_for_different_literal_url_slug(
    scholarships, entity_id, different_url_slug
):
    values = scholarships[0].model_dump(mode="python")
    values.update(
        entity_id=entity_id,
        record_id=f"scholarships:scholarship:{entity_id}",
        canonical_url=(
            "https://www.anu.edu.au/study/scholarships/find-a-scholarship/"
            f"{different_url_slug}"
        ),
    )

    with pytest.raises(ValidationError):
        ScholarshipRecord.model_validate(values)


def test_direct_title_uses_stored_facts_and_canonical_source(repo):
    body = ask(repo, "Tell me about Day 9 Test Undergraduate Computing Scholarship")

    assert body["status"] == "ok"
    assert "Official status: open" in body["answer"]
    assert body["sources"] == [
        {
            "record_id": "scholarships:scholarship:day9-undergraduate-computing",
            "source_id": "scholarships_anu_finder",
            "title": "Day 9 Test Undergraduate Computing Scholarship",
            "url": (
                "https://www.anu.edu.au/study/scholarships/"
                "find-a-scholarship/day9-undergraduate-computing"
            ),
            "domain": "scholarships",
        }
    ]


def test_open_featured_filter_is_explicit_and_does_not_derive_from_dates(repo):
    body = ask(repo, "Show open featured scholarships")

    assert body["status"] == "ok"
    assert [source["record_id"] for source in body["sources"]] == [
        "scholarships:scholarship:day9-undergraduate-computing"
    ]
    assert "Closed" not in body["answer"]


def test_source_supported_list_filter_excludes_missing_lists(repo):
    body = ask(repo, "Show scholarships for Domestic students")

    assert body["status"] == "ok"
    assert [source["record_id"] for source in body["sources"]] == [
        "scholarships:scholarship:day9-undergraduate-computing"
    ]


def test_broad_query_and_ambiguous_title_clarify_without_guessing(
    scholarships,
):
    broad_repo = CourseProgramRepository(scholarships)
    broad = ask(broad_repo, "Show me scholarships")
    assert broad["status"] == "needs_clarification"
    assert "study level" in broad["answer"]
    assert "area of study" in broad["answer"]

    duplicate_values = scholarships[1].model_dump(mode="python")
    duplicate_values.update(
        entity_id="day9-international-science-second",
        record_id="scholarships:scholarship:day9-international-science-second",
        canonical_url=(
            "https://study.anu.edu.au/scholarships/find-a-scholarship/"
            "day9-international-science-second"
        ),
        title=scholarships[0].title,
    )
    ambiguous_repo = CourseProgramRepository(
        [scholarships[0], ScholarshipRecord.model_validate(duplicate_values)]
    )
    ambiguous = ask(ambiguous_repo, scholarships[0].title)
    assert ambiguous["status"] == "needs_clarification"
    assert len(ambiguous["clarification"]["options"]) == 2
    selected = ask(
        ambiguous_repo,
        "first",
        pending=ambiguous["clarification"],
    )
    assert selected["status"] == "ok"
    assert len(selected["sources"]) == 1


def test_personal_eligibility_returns_official_text_without_decision(repo):
    body = ask(
        repo,
        "Am I eligible for the Day 9 Test Undergraduate Computing Scholarship?",
    )

    assert body["status"] == "ok"
    assert "cannot determine your personal eligibility" in body["answer"]
    assert "Official eligibility information" in body["answer"]
    assert "you are eligible" not in body["answer"].casefold()


def test_missing_eligibility_and_dates_do_not_create_a_verdict_or_deadline(repo):
    body = ask(
        repo,
        "Am I eligible for the Day 9 Test International Science Scholarship?",
    )

    assert body["status"] == "ok"
    assert "cannot determine your personal eligibility" in body["answer"]
    assert "Official eligibility information" not in body["answer"]
    assert "Closing date:" not in body["answer"]
    assert "you are eligible" not in body["answer"].casefold()


def test_untrusted_scholarship_evidence_cannot_inject_rendered_output(scholarships):
    values = scholarships[0].model_dump(mode="python")
    values["metadata_json"]["eligibility"] = "<script>override</script>"
    record = ScholarshipRecord.model_validate(values)
    repository = CourseProgramRepository([record])

    with TestClient(create_app(repository), raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": f"Am I eligible for {record.title}?",
                "history": [],
                "conversation_state": {"pending_clarification": None},
            },
        )

    assert response.status_code == 502
    assert response.json()["status"] == "error"
    assert "script" not in response.text.casefold()


def test_history_is_not_used_as_scholarship_source_or_persisted_filter(repo):
    body = ask(
        repo,
        "Show me scholarships",
        history=(
            {
                "turn_id": "t1",
                "role": "user",
                "content": "I am an International postgraduate student.",
            },
        ),
    )

    assert body["status"] == "needs_clarification"
    assert body["sources"] == []


class PersistentVectorSpy:
    uses_persistent_index = True
    target_version = "embed-v2"

    def __init__(self):
        self.calls = 0

    def search(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("Scholarship deterministic retrieval called vectors")


@pytest.mark.parametrize(
    ("index_status", "embedding_version", "stale"),
    [
        ("PENDING", None, True),
        ("FAILED", None, True),
        ("INDEXED", "embed-v2", False),
        ("INDEXED", "embed-v1", True),
    ],
)
def test_scholarship_current_source_retrieval_is_vector_independent(
    scholarships, index_status, embedding_version, stale
):
    record = scholarships[0].model_copy(
        update={
            "status": "UNCHANGED",
            "index_status": index_status,
            "embedding_version": embedding_version,
        }
    )
    vectors = PersistentVectorSpy()
    repository = CourseProgramRepository([record])

    body = ask(repository, record.title, vector=vectors)

    assert body["status"] == "ok"
    assert body["sources"][0]["record_id"] == record.record_id
    assert index_is_stale(record, target_version="embed-v2") is stale
    assert vectors.calls == 0


def test_scholarship_change_unchanged_and_missing_lifecycle(scholarships):
    record = scholarships[0]
    changed = record.model_copy(
        update={"status": "CHANGED", "index_status": "PENDING", "embedding_version": None}
    )
    unchanged_pending = changed.model_copy(update={"status": "UNCHANGED"})
    unchanged_failed = changed.model_copy(
        update={"status": "UNCHANGED", "index_status": "FAILED"}
    )
    missing = changed.model_copy(
        update={"status": "MISSING", "index_status": "FAILED"}
    )

    assert plan_index_action(changed).action is IndexAction.INDEX_CONTENT_CHANGE
    assert plan_index_action(unchanged_pending).action is IndexAction.NONE
    assert plan_index_action(unchanged_failed).action is IndexAction.NONE
    missing_decision = plan_index_action(missing, explicit_retry=True)
    assert missing_decision.action is IndexAction.NONE
    assert missing_decision.index_status == "FAILED"


class FailingPersistentVectors:
    uses_persistent_index = True
    target_version = "embed-v2"

    def __init__(self):
        self.calls = 0

    def search(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("Scholarship deterministic retrieval called vectors")


@pytest.mark.parametrize(
    ("index_status", "embedding_version", "stale"),
    [
        ("PENDING", None, True),
        ("FAILED", None, True),
        ("INDEXED", "embed-v1", True),
        ("INDEXED", "embed-v2", False),
    ],
)
def test_scholarship_source_retrieval_is_vector_independent(
    scholarships, index_status, embedding_version, stale
):
    record = scholarships[0].model_copy(
        update={
            "status": "UNCHANGED",
            "index_status": index_status,
            "embedding_version": embedding_version,
        }
    )
    vectors = FailingPersistentVectors()
    body = ask(CourseProgramRepository([record]), record.title, vector=vectors)

    assert body["status"] == "ok"
    assert body["sources"][0]["record_id"] == record.record_id
    assert index_is_stale(record, target_version="embed-v2") is stale
    assert vectors.calls == 0


@pytest.mark.parametrize("index_status", ["PENDING", "FAILED"])
def test_unchanged_scholarship_preserves_incomplete_index_state(
    scholarships, index_status
):
    record = scholarships[0].model_copy(
        update={"status": "UNCHANGED", "index_status": index_status}
    )
    decision = plan_index_action(record)

    assert decision.action.value == "NONE"
    assert decision.index_status == index_status


def test_missing_scholarship_preserves_last_known_good_without_signal(scholarships):
    record = scholarships[0].model_copy(
        update={"status": "MISSING", "index_status": "FAILED"}
    )
    decision = plan_index_action(record, explicit_retry=True)

    assert decision.action.value == "NONE"
    assert decision.index_status == "FAILED"
