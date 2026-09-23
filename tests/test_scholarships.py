"""Day 9 Scholarship shared-record and deterministic RAG behavior."""

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from askanu_rag.index_lifecycle import IndexAction, index_is_stale, plan_index_action
from askanu_rag.main import create_app
from askanu_rag.models import (
    AskResponse,
    Clarification,
    CommonRecord,
    ScholarshipRecord,
)
from askanu_rag.retrieval import (
    CourseProgramRepository,
    load_common_records,
    load_course_program_records,
)
from askanu_rag.scholarship_queries import ScholarshipQueryService

ROOT = Path(__file__).parents[1]
SCHOLARSHIP_FIXTURE = ROOT / "fixtures/day9_scholarship_records.json"
COURSE_FIXTURE = ROOT / "fixtures/day5_course_program_records.json"
SCHOLARSHIP_URL_PREFIX = (
    "https://study.anu.edu.au/scholarships/find-scholarship/"
)


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


def scholarship_variant(base, *, entity_id, title, **metadata_updates):
    values = base.model_dump(mode="python")
    values.update(
        entity_id=entity_id,
        record_id=f"scholarships:scholarship:{entity_id}",
        canonical_url=f"{SCHOLARSHIP_URL_PREFIX}{entity_id}",
        title=title,
    )
    values["metadata_json"].update(metadata_updates)
    return ScholarshipRecord.model_validate(values)


@pytest.fixture
def refinement_records(scholarships):
    international_engineering = scholarship_variant(
        scholarships[0],
        entity_id="day9-international-bachelor-engineering",
        title="Day 9 Test International Bachelor Engineering Scholarship",
        student_type=["International"],
        study_level=["Bachelor"],
        area_of_study=["Engineering"],
        featured=True,
        status="open",
        eligibility=None,
    )
    international_science = scholarship_variant(
        scholarships[1],
        entity_id="day9-international-bachelor-science",
        title="Day 9 Test International Bachelor Science Scholarship",
        student_type=["International"],
        study_level=["Bachelor"],
        area_of_study=["Science"],
        featured=False,
        status="open",
    )
    domestic_postgraduate = scholarship_variant(
        scholarships[2],
        entity_id="day9-domestic-postgraduate-engineering",
        title="Day 9 Test Domestic Postgraduate Engineering Scholarship",
        student_type=["Domestic"],
        study_level=["Postgraduate"],
        area_of_study=["Engineering"],
        featured=False,
        status="open",
    )
    return (
        international_engineering,
        international_science,
        domestic_postgraduate,
    )


@pytest.fixture
def refinement_repo(refinement_records):
    return CourseProgramRepository(refinement_records)


def ask(repo, question, *, history=(), pending=None, vector=None, dense=None):
    with TestClient(
        create_app(
            repo,
            semantic_retriever=vector,
            vector_retriever=dense,
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
    TypeAdapter(AskResponse).validate_python(response.json())
    assert set(response.json()) == {
        "status",
        "answer",
        "items",
        "sources",
        "clarification",
        "request_id",
        "conversation_state",
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
    assert str(record.canonical_url) == (
        f"{SCHOLARSHIP_URL_PREFIX}day9-international-science"
    )
    assert all(
        item.effective_from is None and item.effective_to is None
        for item in scholarships
    )


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
        canonical_url=f"{SCHOLARSHIP_URL_PREFIX}{different_url_slug}",
    )

    with pytest.raises(ValidationError):
        ScholarshipRecord.model_validate(values)


@pytest.mark.parametrize(
    "canonical_url",
    [
        "http://study.anu.edu.au/scholarships/find-scholarship/foo",
        "HTTPS://study.anu.edu.au/scholarships/find-scholarship/foo",
        "https://STUDY.ANU.EDU.AU/scholarships/find-scholarship/foo",
        "https://study.anu.edu.au:443/scholarships/find-scholarship/foo",
        "https://www.anu.edu.au/scholarships/find-scholarship/foo",
        "https://example.anu.edu.au/scholarships/find-scholarship/foo",
        "https://study.anu.edu.au/study/scholarships/find-scholarship/foo",
        "https://study.anu.edu.au/scholarships/find-a-scholarship/foo",
        "https://study.anu.edu.au/find-scholarship/foo",
        "https://study.anu.edu.au/scholarships/find-scholarship/foo/",
        "https://study.anu.edu.au/scholarships/find-scholarship/foo?year=2026",
        "https://study.anu.edu.au/scholarships/find-scholarship/foo#details",
    ],
)
def test_model_rejects_noncanonical_scholarship_url_boundary(
    scholarships, canonical_url
):
    values = scholarships[0].model_dump(mode="python")
    values.update(
        entity_id="foo",
        record_id="scholarships:scholarship:foo",
        canonical_url=canonical_url,
    )

    with pytest.raises(ValidationError):
        ScholarshipRecord.model_validate(values)


@pytest.mark.parametrize(
    "invalid_slug",
    [
        "Foo",
        "FOO",
        "foo_bar",
        "foo--bar",
        "-foo",
        "foo-",
        "foo.bar",
        "foo/bar",
        "foo%20bar",
        "foo*bar",
        "foo.*",
        "foo+bar",
        "foo?",
        "foo|bar",
        "foo[0-9]",
        "foo[bar]",
    ],
)
def test_model_rejects_scholarship_slug_outside_frozen_grammar(
    scholarships, invalid_slug
):
    values = scholarships[0].model_dump(mode="python")
    values.update(
        entity_id=invalid_slug,
        record_id=f"scholarships:scholarship:{invalid_slug}",
        canonical_url=f"{SCHOLARSHIP_URL_PREFIX}{invalid_slug}",
    )

    with pytest.raises(ValidationError):
        ScholarshipRecord.model_validate(values)


@pytest.mark.parametrize("field", ["effective_from", "effective_to"])
def test_model_rejects_non_null_scholarship_effective_dates(
    scholarships, field
):
    values = scholarships[0].model_dump(mode="python")
    values[field] = values["collected_at"]

    with pytest.raises(ValidationError):
        ScholarshipRecord.model_validate(values)


def test_rag_trusts_scraper_canonical_content_hash_without_rehashing(scholarships):
    values = scholarships[0].model_dump(mode="python")
    values["content"] = "A changed canonical payload owned by the scraper."
    values["content_hash"] = "0" * 64

    record = ScholarshipRecord.model_validate(values)

    assert record.content_hash == "0" * 64


def test_exact_scholarship_slug_lookup_preserves_identity_and_url(repo):
    entity_id = "day9-undergraduate-computing"

    record = repo.find_scholarship_by_entity_id(entity_id)

    assert record is not None
    assert record.entity_id == entity_id
    assert record.record_id == f"scholarships:scholarship:{entity_id}"
    assert str(record.canonical_url) == f"{SCHOLARSHIP_URL_PREFIX}{entity_id}"


def test_frozen_new_changed_and_unchanged_timestamp_examples(scholarships):
    new = scholarships[0]
    assert new.status == "NEW"
    assert new.collected_at == new.last_seen_at

    later = new.last_seen_at + timedelta(hours=1)
    changed = new.model_copy(
        update={
            "status": "CHANGED",
            "content": f"{new.content}\nChanged",
            "content_hash": "1" * 64,
            "last_seen_at": later,
        }
    )
    unchanged = changed.model_copy(
        update={"status": "UNCHANGED", "last_seen_at": later + timedelta(hours=1)}
    )

    assert changed.collected_at == new.collected_at
    assert changed.last_seen_at == later
    assert unchanged.collected_at == new.collected_at
    assert unchanged.last_seen_at > changed.last_seen_at


def test_direct_title_uses_stored_facts_and_canonical_source(repo):
    body = ask(repo, "Tell me about Day 9 Test Undergraduate Computing Scholarship")

    assert body["status"] == "ok"
    assert "Official status: open" in body["answer"]
    assert body["sources"] == [
        {
            "record_id": "scholarships:scholarship:day9-undergraduate-computing",
            "source_id": "scholarships_anu_finder",
            "title": "Day 9 Test Undergraduate Computing Scholarship",
            "url": f"{SCHOLARSHIP_URL_PREFIX}day9-undergraduate-computing",
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
            "https://study.anu.edu.au/scholarships/find-scholarship/"
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


def test_pending_scope_accepts_current_international_undergraduate_refinement(
    refinement_repo,
):
    broad = ask(refinement_repo, "What scholarships can I apply for?")

    body = ask(
        refinement_repo,
        "International undergraduate",
        pending=broad["clarification"],
    )

    assert broad["status"] == "needs_clarification"
    assert broad["clarification"]["id"] == "clar-scholarship-scope"
    assert body["status"] == "ok"
    assert {source["record_id"] for source in body["sources"]} == {
        "scholarships:scholarship:day9-international-bachelor-engineering",
        "scholarships:scholarship:day9-international-bachelor-science",
    }
    assert all(
        source["url"].startswith(SCHOLARSHIP_URL_PREFIX)
        for source in body["sources"]
    )
    assert "you are eligible" not in body["answer"].casefold()


def test_pending_scope_combines_independent_filter_dimensions_with_and(
    refinement_repo,
):
    broad = ask(refinement_repo, "What scholarships can I apply for?")
    body = ask(
        refinement_repo,
        "International undergraduate engineering",
        pending=broad["clarification"],
    )

    assert body["status"] == "ok"
    assert [source["record_id"] for source in body["sources"]] == [
        "scholarships:scholarship:day9-international-bachelor-engineering"
    ]


@pytest.mark.parametrize(
    "unsupported_refinement",
    ["Something completely unrelated", "application required"],
)
def test_pending_scope_unsupported_refinement_stays_safe(
    refinement_repo, unsupported_refinement
):
    broad = ask(refinement_repo, "What scholarships can I apply for?")
    body = ask(
        refinement_repo,
        unsupported_refinement,
        pending=broad["clarification"],
    )

    assert body["status"] == "needs_clarification"
    assert body["clarification"]["id"] == "clar-scholarship-scope"
    assert body["sources"] == []


def test_pending_scope_preserves_first_second_label_and_id_selection(
    refinement_repo,
):
    broad = ask(refinement_repo, "What scholarships can I apply for?")
    options = broad["clarification"]["options"]
    selections = (
        ("first", options[0]["id"]),
        ("second", options[1]["id"]),
        (options[0]["label"], options[0]["id"]),
        (options[1]["id"], options[1]["id"]),
    )

    for selection, expected_id in selections:
        body = ask(
            refinement_repo,
            selection,
            pending=broad["clarification"],
        )
        assert body["status"] == "ok"
        assert [source["record_id"] for source in body["sources"]] == [
            expected_id
        ]


def test_pending_scope_uses_current_refinement_not_profile_like_history(
    refinement_repo,
):
    broad = ask(refinement_repo, "What scholarships can I apply for?")
    body = ask(
        refinement_repo,
        "Domestic postgraduate",
        history=(
            {
                "turn_id": "old-user",
                "role": "user",
                "content": "I am an international undergraduate engineering student.",
            },
        ),
        pending=broad["clarification"],
    )

    assert body["status"] == "ok"
    assert [source["record_id"] for source in body["sources"]] == [
        "scholarships:scholarship:day9-domestic-postgraduate-engineering"
    ]


def test_pending_scope_valid_filters_with_no_match_do_not_relax(refinement_repo):
    broad = ask(refinement_repo, "What scholarships can I apply for?")
    body = ask(
        refinement_repo,
        "closed international engineering",
        pending=broad["clarification"],
    )

    assert body["status"] == "insufficient_evidence"
    assert body["sources"] == []


def test_pending_scope_supports_existing_featured_filter(refinement_repo):
    broad = ask(refinement_repo, "What scholarships can I apply for?")
    body = ask(
        refinement_repo,
        "featured international undergraduate",
        pending=broad["clarification"],
    )

    assert body["status"] == "ok"
    assert [source["record_id"] for source in body["sources"]] == [
        "scholarships:scholarship:day9-international-bachelor-engineering"
    ]


def test_refinement_does_not_become_personal_eligibility_evidence(
    refinement_repo,
):
    broad = ask(refinement_repo, "What scholarships can I apply for?")
    narrowed = ask(
        refinement_repo,
        "International undergraduate engineering",
        pending=broad["clarification"],
    )
    follow_up = ask(
        refinement_repo,
        "Am I eligible for the Day 9 Test International Bachelor Engineering "
        "Scholarship?",
        history=(
            {
                "turn_id": "scope",
                "role": "user",
                "content": "International undergraduate engineering",
            },
            {
                "turn_id": "result",
                "role": "assistant",
                "content": narrowed["answer"],
            },
        ),
    )

    assert narrowed["status"] == "ok"
    assert follow_up["status"] == "ok"
    assert "cannot determine your personal eligibility" in follow_up["answer"]
    assert "Official eligibility information" not in follow_up["answer"]
    assert "you are eligible" not in follow_up["answer"].casefold()


def test_pending_scholarship_scope_does_not_intercept_course_switch(repo):
    broad = ask(repo, "What scholarships can I apply for?")
    body = ask(
        repo,
        "What are the prerequisites for COMP1110?",
        pending=broad["clarification"],
    )

    assert body["status"] == "ok"
    assert body["sources"][0]["record_id"].endswith("COMP1110_2026")


@pytest.mark.parametrize(
    "question",
    [
        "What jobs are available for international undergraduate students?",
        "What courses can international undergraduates take?",
    ],
)
def test_pending_scope_explicit_other_domain_beats_scholarship_filter_words(
    refinement_repo, question
):
    broad = ask(refinement_repo, "What scholarships can I apply for?")
    pending = Clarification.model_validate(broad["clarification"])

    response = asyncio.run(
        ScholarshipQueryService(refinement_repo).answer(
            question,
            "routing-precedence-test",
            pending,
        )
    )

    assert response is None


def test_pending_scope_explicit_scholarship_domain_keeps_refinement(
    refinement_repo,
):
    broad = ask(refinement_repo, "What scholarships can I apply for?")
    body = ask(
        refinement_repo,
        "What scholarships are available for international undergraduates?",
        pending=broad["clarification"],
    )

    assert body["status"] == "ok"
    assert {source["record_id"] for source in body["sources"]} == {
        "scholarships:scholarship:day9-international-bachelor-engineering",
        "scholarships:scholarship:day9-international-bachelor-science",
    }


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


@pytest.mark.parametrize(
    "question",
    [
        "I need support",
        "Honours",
    ],
)
def test_pending_scope_ambiguous_terms_do_not_force_domain_switch(
    refinement_repo, question
):
    broad = ask(refinement_repo, "What scholarships can I apply for?")
    pending = Clarification.model_validate(broad["clarification"])

    response = asyncio.run(
        ScholarshipQueryService(refinement_repo).answer(
            question,
            "ambiguous-routing-test",
            pending,
        )
    )

    assert response is not None
    assert response.status == "needs_clarification"
    assert response.clarification.id == "clar-scholarship-scope"


def test_hybrid_scholarships_apply_open_student_filters_before_semantic_rank(
    scholarships,
):
    open_match = scholarship_variant(
        scholarships[0],
        entity_id="open-international-undergraduate-ai",
        title="Open International Undergraduate AI Scholarship",
        status="open",
        student_type=["International"],
        study_level=["Undergraduate"],
        area_of_study=["Computing"],
    )
    closed_match = scholarship_variant(
        scholarships[2],
        entity_id="closed-international-undergraduate-ai",
        title="Closed International Undergraduate AI Scholarship",
        status="closed",
        student_type=["International"],
        study_level=["Undergraduate"],
        area_of_study=["Computing"],
    )

    class FixedVector:
        def search(self, _question, *, domain, allowed_records, **_kwargs):
            from askanu_rag.retrieval.vector import VectorHit

            assert domain == "scholarships"
            assert open_match in allowed_records
            assert closed_match not in allowed_records
            return (VectorHit(open_match, 0.91, ("whole",)),)

    body = ask(
        CourseProgramRepository([open_match, closed_match]),
        "Open scholarships for an international undergraduate interested in AI",
        dense=FixedVector(),
    )

    assert body["status"] == "ok"
    assert [source["record_id"] for source in body["sources"]] == [
        open_match.record_id
    ]


@pytest.mark.parametrize(
    ("question", "expected", "entity_id"),
    [
        (
            "When does Day 9 Test Undergraduate Computing Scholarship open?",
            "Opening date: 2026-08-01.",
            "day9-undergraduate-computing",
        ),
        (
            "Does Day 9 Test Undergraduate Computing Scholarship require an application?",
            "Application required: yes.",
            "day9-undergraduate-computing",
        ),
        (
            "What is the selection basis for Day 9 Test Undergraduate Computing Scholarship?",
            "Selection basis: Academic merit in this synthetic fixture.",
            "day9-undergraduate-computing",
        ),
        (
            "Is Day 9 Test Undergraduate Computing Scholarship for Domestic students?",
            "Student type: Domestic.",
            "day9-undergraduate-computing",
        ),
        (
            "What study stage is Day 9 Test Undergraduate Computing Scholarship intended for?",
            "Study stage: Current students.",
            "day9-undergraduate-computing",
        ),
        (
            "Is Day 9 Test Undergraduate Computing Scholarship featured?",
            "Featured: yes.",
            "day9-undergraduate-computing",
        ),
        (
            "Is Day 9 Test International Science Scholarship featured?",
            "Featured: no.",
            "day9-international-science",
        ),
        (
            "Does Day 9 Test Closed Computing Scholarship require an application?",
            "Application required: no.",
            "day9-closed-computing",
        ),
    ],
)
def test_direct_scholarship_fact_projection_uses_exact_stored_evidence(
    repo, question, expected, entity_id
):
    body = ask(repo, question)

    assert body["status"] == "ok"
    assert expected in body["answer"]
    assert body["sources"][0]["record_id"] == f"scholarships:scholarship:{entity_id}"


@pytest.mark.parametrize(
    ("question", "missing_label"),
    [
        (
            "When does Day 9 Test International Science Scholarship open?",
            "opening date",
        ),
        (
            "Does Day 9 Test International Science Scholarship require an application?",
            "application required",
        ),
        (
            "What is the selection basis for Day 9 Test International Science Scholarship?",
            "selection basis",
        ),
    ],
)
def test_missing_requested_scholarship_fact_abstains_with_official_source(
    repo, question, missing_label
):
    body = ask(repo, question)

    assert body["status"] == "insufficient_evidence"
    assert missing_label in body["answer"].casefold()
    assert body["sources"][0]["record_id"] == (
        "scholarships:scholarship:day9-international-science"
    )
    for unrelated in ("Official status:", "Study level:", "Area of study:", "Value:"):
        assert unrelated not in body["answer"]
def test_day11_closing_date_projection_and_null_abstention(repo):
    present = ask(
        repo,
        "When does Day 9 Test Undergraduate Computing Scholarship close?",
    )

    assert present["status"] == "ok"
    assert present["answer"] == (
        "Day 9 Test Undergraduate Computing Scholarship. "
        "Closing date: 2026-10-31."
    )
    assert [
        source["record_id"]
        for source in present["sources"]
    ] == [
        "scholarships:scholarship:day9-undergraduate-computing"
    ]

    missing = ask(
        repo,
        "When does Day 9 Test International Science Scholarship close?",
    )

    assert missing["status"] == "insufficient_evidence"
    assert "closing date" in missing["answer"].casefold()
    assert [
        source["record_id"]
        for source in missing["sources"]
    ] == [
        "scholarships:scholarship:day9-international-science"
    ]

    for unrelated in (
        "Official status:",
        "Study level:",
        "Area of study:",
        "Value:",
    ):
        assert unrelated not in missing["answer"]
