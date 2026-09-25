from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from askanu_rag.retrieval.benchmark import (
    BENCHMARK_K_VALUES,
    CurrentSparseBaseline,
    Day3BoundedImprovement,
    LocalBm25Experiment,
    evaluate_benchmark,
    load_benchmark,
)
from askanu_rag.retrieval.query_expansion import expand_support_problem_query


ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_PATH = ROOT / "benchmarks" / "v7_day3" / "benchmark.json"
HOLDOUT_PATH = ROOT / "benchmarks" / "v7_day3" / "holdout.json"


@pytest.fixture(scope="module")
def development():
    return load_benchmark(DEVELOPMENT_PATH)


@pytest.fixture(scope="module")
def holdout():
    return load_benchmark(HOLDOUT_PATH)


@pytest.fixture(scope="module")
def baseline(holdout):
    return evaluate_benchmark(
        holdout, CurrentSparseBaseline(), latency_repetitions=1
    )


@pytest.fixture(scope="module")
def final_pipeline(holdout):
    return evaluate_benchmark(
        holdout, Day3BoundedImprovement(), latency_repetitions=1
    )


@pytest.fixture(scope="module")
def bm25(holdout):
    return evaluate_benchmark(
        holdout, LocalBm25Experiment(), latency_repetitions=1
    )


def test_holdout_is_balanced_prelabelled_and_disjoint(development, holdout):
    assert holdout.labelled_before_run is True
    assert len(holdout.queries) == 24
    assert Counter(query.domain.value for query in holdout.queries) == Counter(
        {
            "courses": 4,
            "scholarships": 4,
            "accommodation": 4,
            "jobs": 4,
            "events": 4,
            "support": 4,
        }
    )
    assert Counter(query.difficulty for query in holdout.queries) == Counter(
        {"easy": 6, "medium": 12, "difficult": 6}
    )
    development_queries = {
        query.query.strip().casefold() for query in development.queries
    }
    holdout_queries = {query.query.strip().casefold() for query in holdout.queries}
    assert len(holdout_queries) == len(holdout.queries)
    assert development_queries.isdisjoint(holdout_queries)


def test_holdout_uses_unchanged_development_corpus_records(development, holdout):
    development_records = {
        record.record_id: record.model_dump(mode="json")
        for record in development.records
    }
    assert all(
        development_records[record.record_id] == record.model_dump(mode="json")
        for record in holdout.records
    )


def test_support_holdout_phrases_are_not_encoded_by_current_expansion(holdout):
    queries = {
        query.query_id: query.query
        for query in holdout.queries
        if query.query_id.startswith("holdout-support-")
        and query.route == "discovery"
    }
    assert len(queries) == 3
    assert all(expand_support_problem_query(query) == query for query in queries.values())


@pytest.mark.parametrize("report_fixture", ("baseline", "final_pipeline", "bm25"))
def test_holdout_reports_same_metrics_and_safety_invariants(
    request, report_fixture
):
    report = request.getfixturevalue(report_fixture)
    assert report.query_count == 24
    assert report.measured_query_count == 24
    assert tuple(report.recall_at_k) == BENCHMARK_K_VALUES
    assert report.provenance_pass_rate == 1.0
    assert report.hard_constraint_pass_rate == 1.0
    assert report.retrieval_latency_p50_ms >= 0
    assert report.retrieval_latency_p95_ms >= report.retrieval_latency_p50_ms


def test_holdout_records_current_generalization_gap(baseline, final_pipeline):
    for report in (baseline, final_pipeline):
        assert report.recall_at_k[1] == pytest.approx(0.6736111111111112)
        assert report.recall_at_k[3] == 0.75
        assert report.recall_at_k[5] == 0.75
        assert report.recall_at_k[10] == 0.75
        assert report.recall_at_k[20] == 0.75
        assert report.selected_evidence_complete_rate == 0.75
        assert report.selected_evidence_precision == 1.0
        assert report.failure_counts == {"DATA": 4, "NONE": 14, "RETRIEVAL": 6}
    assert final_pipeline.domain_recall_at_5["support"] == 0.25
    assert final_pipeline.domain_recall_at_5["jobs"] == 0.75


def test_holdout_records_bm25_recall_noise_tradeoff(bm25):
    assert bm25.recall_at_k[1] == pytest.approx(0.7986111111111112)
    assert bm25.recall_at_k[3] == pytest.approx(23 / 24)
    assert bm25.recall_at_k[5] == pytest.approx(23 / 24)
    assert bm25.recall_at_k[10] == pytest.approx(23 / 24)
    assert bm25.recall_at_k[20] == pytest.approx(23 / 24)
    assert bm25.selected_evidence_complete_rate == pytest.approx(23 / 24)
    assert bm25.selected_evidence_precision == pytest.approx(28 / 43)
    assert bm25.failure_counts == {"DATA": 4, "NONE": 19, "RETRIEVAL": 1}
    retrieval_failures = {
        result.query_id
        for result in bm25.results
        if result.observed_failure_class == "RETRIEVAL"
    }
    assert retrieval_failures == {"holdout-support-financial"}
