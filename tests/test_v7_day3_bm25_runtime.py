from __future__ import annotations

from collections import Counter
from pathlib import Path

from askanu_rag.config import Settings
from askanu_rag.hybrid_queries import HybridQueryService
from askanu_rag.job_queries import JobQueryService
from askanu_rag.resource_queries import DomainResourceQueryService
from askanu_rag.retrieval.benchmark import (
    LocalBm25Experiment,
    load_benchmark,
)
from askanu_rag.retrieval.semantic import LocalBm25Retriever
from askanu_rag.scholarship_queries import ScholarshipQueryService


ROOT = Path(__file__).resolve().parents[1]


def test_selected_runtime_bm25_configuration_is_frozen():
    retriever = LocalBm25Retriever()

    assert retriever.k1 == 1.2
    assert retriever.b == 0.75
    assert retriever.uses_persistent_index is False
    assert retriever.uses_min_score is False
    assert retriever.score_kind == "bm25"
    assert retriever._tokens("The COMP-1110 course") == Counter(
        {"the": 1, "comp": 1, "1110": 1, "course": 1}
    )


def test_selected_runtime_bm25_matches_frozen_benchmark_adapter():
    runtime = LocalBm25Retriever()
    adapter = LocalBm25Experiment()

    for artifact in ("benchmark.json", "holdout.json"):
        suite = load_benchmark(ROOT / "benchmarks" / "v7_day3" / artifact)
        by_id = {record.record_id: record for record in suite.records}
        for query in suite.queries:
            if query.route != "discovery":
                continue
            population = tuple(
                by_id[record_id] for record_id in query.eligible_record_ids
            )
            runtime_ids = tuple(
                hit.record_id
                for hit in runtime.search(
                    query.query,
                    population,  # type: ignore[arg-type] -- same frozen projection
                    top_k=5,
                    min_score=0.99,
                )
            )
            adapter_ids = tuple(
                record.record_id
                for record in adapter.retrieve(query, population, top_k=5)
            )
            assert runtime_ids == adapter_ids


def test_selected_runtime_bm25_ties_are_stable_by_record_id():
    suite = load_benchmark(ROOT / "benchmarks" / "v7_day3" / "benchmark.json")
    template = suite.records[0]
    records = (
        template.model_copy(
            update={"record_id": "courses:course:B", "title": "Same alpha"}
        ),
        template.model_copy(
            update={"record_id": "courses:course:A", "title": "Same alpha"}
        ),
    )

    hits = LocalBm25Retriever().search(
        "alpha", records, top_k=5, min_score=1.0
    )

    assert [hit.record_id for hit in hits] == [
        "courses:course:A",
        "courses:course:B",
    ]


def test_all_runtime_discovery_services_default_to_selected_bm25_at_k_five():
    repository = object()

    courses = HybridQueryService(repository)
    jobs = JobQueryService(repository)  # type: ignore[arg-type]
    accommodation = DomainResourceQueryService(
        repository, "accommodation"  # type: ignore[arg-type]
    )
    support = DomainResourceQueryService(
        repository, "support"  # type: ignore[arg-type]
    )
    scholarships = ScholarshipQueryService(repository)  # type: ignore[arg-type]

    assert Settings().semantic_top_k == 5
    assert isinstance(courses.semantic, LocalBm25Retriever)
    assert courses.top_k == 5
    assert isinstance(jobs._sparse, LocalBm25Retriever)
    assert jobs._top_k == 5
    assert isinstance(accommodation.sparse, LocalBm25Retriever)
    assert accommodation.top_k == 5
    assert isinstance(support.sparse, LocalBm25Retriever)
    assert support.top_k == 5
    assert isinstance(scholarships._sparse, LocalBm25Retriever)
    assert scholarships._top_k == 5
