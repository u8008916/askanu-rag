from __future__ import annotations

from pathlib import Path

import pytest

from askanu_rag.retrieval.embeddings import DeterministicFakeEmbedder
from askanu_rag.retrieval.final_hybrid_benchmark import (
    FINAL_HYBRID_LABEL,
    FROZEN_HOLDOUT_SHA256,
    FinalHybridMeasurementError,
    run_final_hybrid_benchmark,
    sha256_file,
    write_report,
)
from askanu_rag.retrieval.reranking import RerankResult, RerankerUnavailableError
from askanu_rag.retrieval.benchmark import load_benchmark


ROOT = Path(__file__).resolve().parents[1]
HOLDOUT = ROOT / "benchmarks" / "v7_day3" / "holdout.json"


class IdentityReranker:
    def rerank(self, query, documents, *, top_n):
        assert query
        assert 1 <= len(documents) <= 20
        return tuple(RerankResult(index, 1.0 - index / 100) for index in range(top_n))


class OfflineReranker:
    def rerank(self, query, documents, *, top_n):
        raise RerankerUnavailableError("offline")


def test_final_hybrid_runner_is_isolated_bounded_and_auditable(tmp_path):
    report = run_final_hybrid_benchmark(
        load_benchmark(HOLDOUT),
        DeterministicFakeEmbedder(dimension=16),
        IdentityReranker(),
        holdout_sha256=FROZEN_HOLDOUT_SHA256,
        enforce_live_providers=False,
    )

    assert report.label == FINAL_HYBRID_LABEL
    assert report.query_count == report.measured_query_count == 24
    assert report.corpus.canonical_records == 29
    assert report.corpus.retrieval_units == report.corpus.vectors == 29
    assert report.corpus.production_database_used is False
    assert report.pipeline.max_retrieval_units_per_record == 20
    assert report.pipeline.max_returned_vector_units_per_record == 3
    assert report.pipeline.fusion == "RRF k=60 fused max20"
    assert "excluded" in report.pipeline.benchmark_provider_pacing
    assert len(report.results) == 24
    assert all(len(result.sparse_ids) <= 20 for result in report.results)
    assert all(len(result.dense_ids) <= 20 for result in report.results)
    assert all(len(result.fused_ids) <= 20 for result in report.results)
    assert all(len(result.selected_ids) <= 5 for result in report.results)
    assert all(
        result.reranker_used for result in report.results if result.fused_ids
    )
    assert report.provenance_pass_rate == 1.0
    assert report.hard_constraint_pass_rate == 1.0
    assert report.provider_errors == ()

    raw = tmp_path / "raw.json"
    summary = tmp_path / "summary.md"
    write_report(report, raw, summary)
    assert FINAL_HYBRID_LABEL in raw.read_text(encoding="utf-8")
    assert FINAL_HYBRID_LABEL in summary.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_report(report, raw, summary)


def test_final_hybrid_runner_rejects_transient_reranker_fallback():
    with pytest.raises(FinalHybridMeasurementError, match="fell back"):
        run_final_hybrid_benchmark(
            load_benchmark(HOLDOUT),
            DeterministicFakeEmbedder(dimension=16),
            OfflineReranker(),
            holdout_sha256=FROZEN_HOLDOUT_SHA256,
            enforce_live_providers=False,
        )


def test_frozen_holdout_sha_is_exact():
    assert sha256_file(HOLDOUT) == FROZEN_HOLDOUT_SHA256
