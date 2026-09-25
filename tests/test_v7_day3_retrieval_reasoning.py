"""Frozen V7 Day 3 retrieval, evidence and epistemic-safety benchmark."""

import copy
import hashlib
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from askanu_rag.evidence_selection import (
    build_reasoned_evidence_bundle,
    build_result_set,
    classify_answer_state,
    classify_result_set_status,
)
from askanu_rag.models import (
    AnswerState,
    ConstraintLifecycle,
    ConstraintScope,
    ConstraintSemanticType,
    ConstraintSet,
    Domain,
    EntityKind,
    EvidenceItem,
    MissingEvidence,
    QueryInterpretation,
    ResolvedIntent,
    ResultSetStatus,
    RetrievalStrategy,
    ScopedConstraint,
    SupportRecord,
)
from askanu_rag.main import create_app
from askanu_rag.retrieval import CourseProgramRepository
from askanu_rag.retrieval.benchmark import (
    BENCHMARK_K_VALUES,
    BenchmarkQuery,
    CurrentSparseBaseline,
    Day3BoundedImprovement,
    LocalBm25Experiment,
    SupportExpansionExperiment,
    evaluate_benchmark,
    load_benchmark,
)
from askanu_rag.retrieval_planning import build_retrieval_plan
from test_day12_contracts import support_payload
from test_jobs import TODAY, make_job

BENCHMARK = (
    Path(__file__).parents[1] / "benchmarks" / "v7_day3" / "benchmark.json"
)


@pytest.fixture(scope="module")
def suite():
    return load_benchmark(BENCHMARK)


@pytest.fixture(scope="module")
def baseline(suite):
    return evaluate_benchmark(suite, CurrentSparseBaseline(), latency_repetitions=1)


@pytest.fixture(scope="module")
def bm25(suite):
    return evaluate_benchmark(suite, LocalBm25Experiment(), latency_repetitions=1)


@pytest.fixture(scope="module")
def support_expansion(suite):
    return evaluate_benchmark(
        suite, SupportExpansionExperiment(), latency_repetitions=1
    )


@pytest.fixture(scope="module")
def day3_improvement(suite):
    return evaluate_benchmark(
        suite, Day3BoundedImprovement(), latency_repetitions=1
    )


def test_frozen_benchmark_has_balanced_six_domain_coverage(suite):
    assert suite.labelled_before_run is True
    assert len(suite.queries) == 36
    assert Counter(query.domain for query in suite.queries) == {
        domain: 6 for domain in Domain
    }
    assert {query.difficulty for query in suite.queries} == {
        "easy",
        "medium",
        "difficult",
    }
    assert {query.route for query in suite.queries} == {
        "exact",
        "structured",
        "discovery",
    }


def test_every_query_predeclares_evidence_authority_constraints_and_semantics(suite):
    assert all(query.allowed_source_ids for query in suite.queries)
    assert all(query.notes for query in suite.queries)
    assert all(query.query_type for query in suite.queries)
    assert {query.expected_answer_state for query in suite.queries} == {
        AnswerState.CONFIRMED,
        AnswerState.DERIVED,
        AnswerState.PARTIAL,
        AnswerState.UNKNOWN,
    }
    assert {query.expected_result_status for query in suite.queries} == {
        ResultSetStatus.RESULTS,
        ResultSetStatus.EMPTY,
        ResultSetStatus.INCOMPLETE,
    }


def test_empty_requires_a_completely_evaluated_population():
    with pytest.raises(ValidationError, match="EMPTY requires"):
        BenchmarkQuery.model_validate(
            {
                "query_id": "unsafe-empty",
                "domain": "jobs",
                "query": "No jobs?",
                "query_type": "negative",
                "difficulty": "difficult",
                "route": "structured",
                "eligible_record_ids": [],
                "expected_relevant_record_ids": [],
                "allowed_source_ids": ["jobs_anu_search"],
                "hard_constraints": [],
                "expected_answer_state": "UNKNOWN",
                "expected_result_status": "EMPTY",
                "population_complete": False,
                "notes": "An incomplete population cannot prove an empty result.",
            }
        )


def test_incomplete_population_cannot_claim_confirmed_answer():
    with pytest.raises(ValidationError, match="INCOMPLETE cannot"):
        BenchmarkQuery.model_validate(
            {
                "query_id": "unsafe-incomplete",
                "domain": "jobs",
                "query": "Any jobs?",
                "query_type": "negative",
                "difficulty": "difficult",
                "route": "structured",
                "eligible_record_ids": [],
                "expected_relevant_record_ids": [],
                "allowed_source_ids": ["jobs_anu_search"],
                "hard_constraints": [],
                "expected_answer_state": "CONFIRMED",
                "expected_result_status": "INCOMPLETE",
                "population_complete": False,
                "notes": "Unknown evidence cannot become a confirmed no-match.",
            }
        )


def test_current_baseline_reports_all_required_k_values_and_stage_metrics(baseline):
    assert tuple(baseline.recall_at_k) == BENCHMARK_K_VALUES
    assert baseline.measured_query_count == 35
    assert baseline.recall_at_k[1] == pytest.approx(0.7833333333)
    assert baseline.recall_at_k[3] == pytest.approx(0.8785714286)
    assert baseline.recall_at_k[5] == pytest.approx(0.8857142857)
    assert baseline.recall_at_k[10] == pytest.approx(0.8857142857)
    assert baseline.recall_at_k[20] == pytest.approx(0.8857142857)
    assert baseline.selected_evidence_complete_rate == pytest.approx(31 / 35)
    assert baseline.selected_evidence_precision == 1.0
    assert tuple(baseline.retrieval_latency_by_k_ms) == BENCHMARK_K_VALUES
    assert all(
        summary.samples == baseline.query_count
        for summary in baseline.retrieval_latency_by_k_ms.values()
    )
    assert set(baseline.route_latency_ms) == {"discovery", "exact", "structured"}
    assert set(baseline.interaction_latency_ms) == {
        "discovery",
        "follow_up",
        "lookup",
    }
    assert set(baseline.domain_latency_ms) == {
        "accommodation",
        "courses",
        "events",
        "jobs",
        "scholarships",
        "support",
    }
    assert all(
        summary.p95_ms >= summary.p50_ms >= 0
        for summary in (
            *baseline.retrieval_latency_by_k_ms.values(),
            *baseline.route_latency_ms.values(),
            *baseline.interaction_latency_ms.values(),
            *baseline.domain_latency_ms.values(),
        )
    )


def test_baseline_preserves_hard_filters_and_source_authority(baseline):
    assert baseline.hard_constraint_pass_rate == 1.0
    assert baseline.provenance_pass_rate == 1.0
    assert all(result.hard_constraints_preserved for result in baseline.results)
    assert all(result.provenance_preserved for result in baseline.results)


def test_missing_facts_are_data_failures_not_retrieval_misses(baseline):
    failures = {
        result.query_id: result.observed_failure_class for result in baseline.results
    }
    assert failures["scholarship-eligibility-unknown"] == "DATA"
    assert failures["accommodation-vacancy-unknown"] == "DATA"
    assert failures["jobs-incomplete-requirements"] == "DATA"
    assert failures["events-rubric-organiser-unknown"] == "DATA"
    assert failures["support-hours-unknown"] == "DATA"


def test_retrieval_misses_are_separate_from_evidence_selection(baseline):
    assert baseline.failure_counts["RETRIEVAL"] == 4
    assert baseline.failure_counts.get("EVIDENCE_SELECTION_RANKING", 0) == 0
    missed = {
        result.query_id
        for result in baseline.results
        if result.observed_failure_class == "RETRIEVAL"
    }
    assert missed == {
        "support-unfair-grade",
        "support-money-problem",
        "support-international",
        "jobs-technical",
    }


def test_bm25_experiment_improves_recall_but_increases_candidate_noise(
    baseline, bm25
):
    assert bm25.recall_at_k[5] > baseline.recall_at_k[5]
    assert bm25.selected_evidence_complete_rate > (
        baseline.selected_evidence_complete_rate
    )
    assert bm25.selected_evidence_precision < baseline.selected_evidence_precision
    assert bm25.provenance_pass_rate == 1.0
    assert bm25.hard_constraint_pass_rate == 1.0
    assert bm25.failure_counts["RETRIEVAL"] == 1


def test_bounded_support_expansion_closes_measured_gap_without_noise_regression(
    baseline, support_expansion
):
    assert support_expansion.recall_at_k[5] == pytest.approx(34 / 35)
    assert support_expansion.selected_evidence_complete_rate == pytest.approx(34 / 35)
    assert support_expansion.selected_evidence_precision >= (
        baseline.selected_evidence_precision
    )
    assert support_expansion.domain_recall_at_5["support"] == 1.0
    assert support_expansion.failure_counts["RETRIEVAL"] == 1
    assert support_expansion.provenance_pass_rate == 1.0
    assert support_expansion.hard_constraint_pass_rate == 1.0


def test_complete_day3_improvement_closes_jobs_and_support_retrieval_gaps(
    day3_improvement
):
    assert day3_improvement.recall_at_k[5] == 1.0
    assert day3_improvement.recall_at_k[20] == 1.0
    assert day3_improvement.selected_evidence_complete_rate == 1.0
    assert day3_improvement.selected_evidence_precision == 1.0
    assert day3_improvement.failure_counts == {"DATA": 5, "NONE": 31}
    assert day3_improvement.provenance_pass_rate == 1.0
    assert day3_improvement.hard_constraint_pass_rate == 1.0


def test_exact_and_retained_resultset_paths_do_not_depend_on_sparse_ranking(
    suite, baseline
):
    results = {result.query_id: result for result in baseline.results}
    for query_id in (
        "course-code",
        "course-followup-prereq",
        "scholarship-second-result",
    ):
        assert results[query_id].first_relevant_rank == 1
        assert results[query_id].selected_evidence_complete is True


def test_rubric_source_identity_is_never_relabelled_as_official(suite, baseline):
    record_sources = {record.record_id: record.source_id for record in suite.records}
    result = next(
        item
        for item in baseline.results
        if item.query_id == "events-rubric-organiser-unknown"
    )
    assert result.candidate_ids == ("events:event:rubric-9001",)
    assert record_sources[result.candidate_ids[0]] == "rubric_unified_search"


def _support_record(entity_id: str, title: str, purpose: str) -> SupportRecord:
    payload = copy.deepcopy(support_payload())
    payload.update(
        entity_id=entity_id,
        record_id=f"support:support_service:{entity_id}",
        title=title,
        canonical_url=f"https://anusa.com.au/student-assistance/{entity_id}/",
    )
    payload["metadata_json"]["category"] = title.removesuffix(" Support")
    payload["metadata_json"]["purpose"] = purpose
    if entity_id != "academic":
        payload["metadata_json"]["topics"] = []
    content = f"{title}. {purpose}"
    payload["content"] = content
    payload["content_hash"] = hashlib.sha256(content.encode()).hexdigest()
    return SupportRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("question", "expected_record_id", "expected_status"),
    (
        (
            "My mark feels unfair and I want to challenge the assessment",
            "support:support_service:academic",
            "ok",
        ),
        (
            "I am stressed because I cannot afford groceries",
            None,
            "insufficient_evidence",
        ),
        (
            "Where can an international student get help settling in?",
            "support:support_service:international",
            "ok",
        ),
    ),
)
def test_resolved_natural_support_problems_reach_source_grounded_retrieval(
    question, expected_record_id, expected_status
):
    records = (
        _support_record(
            "academic",
            "Academic Support",
            "Help with unfair grades, assessment concerns and grade appeals.",
        ),
        _support_record(
            "financial",
            "Financial Support",
            "Help with money stress and financial hardship.",
        ),
        _support_record(
            "international",
            "International Student Support",
            "Help for international students with study and community referrals.",
        ),
    )
    with TestClient(create_app(CourseProgramRepository(records))) as client:
        response = client.post(
            "/api/v1/ask",
            json={"question": question, "history": [], "conversation_state": {}},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == expected_status
    if expected_record_id is None:
        assert body["sources"] == []
    else:
        assert body["sources"][0]["record_id"] == expected_record_id
        assert body["sources"][0]["source_id"] == "support_anusa_student_assistance"


def test_jobs_semantic_discovery_has_local_sparse_fallback_without_vectors():
    records = (
        make_job(
            "100001",
            title="Python Web Software Developer",
            role_requirements=["Python web software development"],
        ),
        make_job("100002", title="Research Officer"),
    )
    with TestClient(
        create_app(
            CourseProgramRepository(records),
            jobs_today_provider=lambda: TODAY,
        )
    ) as client:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": (
                    "Which current ANU jobs involve Python web software development?"
                ),
                "history": [],
                "conversation_state": {},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert [source["record_id"] for source in body["sources"]] == [
        "jobs:job:100001"
    ]


def test_retrieval_plan_keeps_hard_filters_before_selected_discovery_strategy():
    constraint = ScopedConstraint(
        semantic_type=ConstraintSemanticType.STUDENT_TYPE,
        value="international",
        scope=ConstraintScope(domain=Domain.SCHOLARSHIPS),
        lifecycle=ConstraintLifecycle.UNTIL_REPLACED,
        introduced_turn=1,
    )
    plan = build_retrieval_plan(
        QueryInterpretation(
            domain=Domain.SCHOLARSHIPS,
            intent=ResolvedIntent(name="discover", operation="initial_discovery"),
            explicit_constraints=ConstraintSet(items=(constraint,)),
            constraints=ConstraintSet(items=(constraint,)),
        ),
        plan_id="plan-day3-hybrid",
        discovery_strategy=RetrievalStrategy.HYBRID,
    )

    assert plan is not None
    assert [step.strategy for step in plan.steps] == [
        RetrievalStrategy.STRUCTURED_FILTER,
        RetrievalStrategy.HYBRID,
    ]


def test_resultset_status_depends_on_population_completeness_not_answer_state():
    assert classify_result_set_status(("one",), population_complete=False) == (
        ResultSetStatus.RESULTS
    )
    assert classify_result_set_status((), population_complete=True) == (
        ResultSetStatus.EMPTY
    )
    assert classify_result_set_status((), population_complete=False) == (
        ResultSetStatus.INCOMPLETE
    )


def test_reasoning_state_is_derived_only_from_selected_and_missing_evidence():
    evidence = EvidenceItem(
        record_id="accommodation:residence:yukeembruk",
        source_id="accommodation_anu_study",
        domain=Domain.ACCOMMODATION,
        canonical_url=(
            "https://study.anu.edu.au/accommodation/our-residences/yukeembruk"
        ),
        evidence_text="The stored source does not publish current vacancy status.",
        selected_fields=("vacancy_status",),
    )
    missing = MissingEvidence(field="vacancy_status", reason="null")
    plan = build_retrieval_plan(
        QueryInterpretation(
            domain=Domain.ACCOMMODATION,
            intent=ResolvedIntent(name="fact_lookup", operation="lookup"),
        ),
        plan_id="plan-vacancy",
    )
    assert plan is not None

    assert classify_answer_state(
        selected_evidence=(evidence,), missing_evidence=(missing,)
    ) == AnswerState.PARTIAL
    assert classify_answer_state(
        selected_evidence=(), missing_evidence=(missing,)
    ) == AnswerState.UNKNOWN
    bundle = build_reasoned_evidence_bundle(
        plan,
        bundle_id="bundle-vacancy",
        selected_evidence=(evidence,),
        missing_evidence=(missing,),
    )
    result_set = build_result_set(
        plan,
        result_set_id="results-vacancy",
        entity_kind=EntityKind.RESIDENCE,
        ordered_canonical_ids=("yukeembruk",),
        originating_query="Are there rooms right now?",
        created_turn=2,
        population_complete=True,
    )
    assert bundle.answer_state == AnswerState.PARTIAL
    assert result_set.status == ResultSetStatus.RESULTS
