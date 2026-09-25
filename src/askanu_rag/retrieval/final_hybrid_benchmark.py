"""One-shot benchmark runner for the frozen V7 Day 3 hybrid retrieval path.

This module is deliberately outside the request path.  It converts the frozen
benchmark projections into an isolated in-memory corpus, calls the real provider
adapters, and reuses the production BM25, vector, RRF, hard-filter, and reranking
components.  It never opens a database connection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from time import perf_counter_ns, sleep
from typing import Sequence

from pydantic import Field

from askanu_rag.config import DEFAULT_EMBEDDING_VERSION, Settings
from askanu_rag.retrieval.benchmark import (
    BenchmarkModel,
    BenchmarkRecord,
    BenchmarkSuite,
    load_benchmark,
)
from askanu_rag.retrieval.embeddings import (
    EmbeddingProvider,
    GeminiEmbeddingProvider,
    validate_vector,
)
from askanu_rag.retrieval.formatting import format_embedding_document
from askanu_rag.retrieval.hybrid import RankedCandidate, SharedHybridRetriever
from askanu_rag.retrieval.reranking import (
    CohereReranker,
    Reranker,
    RerankerDiagnostic,
    RerankerError,
)
from askanu_rag.retrieval.semantic import LocalBm25Retriever
from askanu_rag.retrieval.units import RetrievalUnitBuilder
from askanu_rag.retrieval.vector import (
    InMemoryVectorRepository,
    PersistedEmbedding,
    PersistedSemanticRetriever,
)


FINAL_HYBRID_LABEL = "V7 Day 3 final retrieval baseline"
FROZEN_HOLDOUT_SHA256 = (
    "13b061af57a6c2730dc7434f325996f0e2ce536ceddf00281545a89f58bf65b6"
)
SPARSE_TOP_K = 20
DENSE_TOP_K = 20
VECTOR_MIN_SCORE = 0.35
MAX_VECTOR_UNITS_PER_RECORD = 3
RRF_K = 60
FUSED_MAX = 20
RERANK_TOP_N = 5
EMBEDDING_DIMENSION = 768
EMBEDDING_MODEL = "gemini-embedding-2"
RERANK_MODEL = "rerank-v4.0-fast"
# Cohere documents a 10 request/minute evaluation-key Rerank limit.  Pacing is
# benchmark orchestration only: it is outside per-query latency and changes no
# query, candidate, model, or ranking configuration.
COHERE_MIN_INTERVAL_SECONDS = 6.1


class FinalHybridMeasurementError(RuntimeError):
    """The official measurement did not complete without fallback."""


class _BenchmarkMetadata(BenchmarkModel):
    entity_type: str


@dataclass(frozen=True)
class _BenchmarkCanonicalRecord:
    """Minimal CommonRecord-shaped adapter for frozen benchmark projections."""

    record_id: str
    source_id: str
    entity_id: str
    domain: str
    title: str
    content: str
    canonical_url: str
    content_hash: str
    metadata_json: _BenchmarkMetadata
    status: str = "NEW"
    index_status: str = "PENDING"
    embedding_version: str | None = None

    def model_copy(self, *, update: dict[str, object]):
        return replace(self, **update)


class LatencyAggregate(BenchmarkModel):
    p50_ms: float
    p95_ms: float
    mean_ms: float
    samples: int


class FinalHybridPipelineConfig(BenchmarkModel):
    sparse: str = "BM25 k1=1.2 b=0.75 Top20"
    dense: str = "Gemini gemini-embedding-2 768-dimensional cosine Top20"
    vector_min_score: float = VECTOR_MIN_SCORE
    retrieval_unit_policy: str = "retrieval-unit-v2-structured"
    max_retrieval_unit_chars: int = 2_000
    max_retrieval_units_per_record: int = 20
    max_returned_vector_units_per_record: int = MAX_VECTOR_UNITS_PER_RECORD
    fusion: str = "RRF k=60 fused max20"
    hard_filter: str = (
        "frozen eligible population plus post-fusion conclusive-invalid guard"
    )
    reranker: str = "Cohere rerank-v4.0-fast Top5"
    benchmark_provider_pacing: str = (
        "Cohere calls spaced by at least 6.1 seconds; wait excluded from "
        "per-query retrieval latency"
    )
    embedding_version: str = DEFAULT_EMBEDDING_VERSION


class FinalHybridCorpusSummary(BenchmarkModel):
    source: str
    canonical_records: int
    retrieval_units: int
    vectors: int
    domain_distribution: dict[str, int]
    storage: str = "isolated in-memory benchmark repository"
    production_database_used: bool = False


class FinalHybridQueryResult(BenchmarkModel):
    query_id: str
    domain: str
    expected_relevant_ids: tuple[str, ...]
    sparse_ids: tuple[str, ...]
    dense_ids: tuple[str, ...]
    fused_ids: tuple[str, ...]
    selected_ids: tuple[str, ...]
    first_relevant_rank: int | None
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    pre_rerank_recall_at_10: float
    selected_evidence_complete: bool
    provenance_preserved: bool
    hard_constraints_preserved: bool
    rejected_by_hard_filter: int
    reranker_used: bool
    observed_failure_class: str
    latency_ms: dict[str, float]


class FinalHybridBenchmarkReport(BenchmarkModel):
    label: str = FINAL_HYBRID_LABEL
    benchmark_id: str
    measured_at_utc: datetime
    holdout_sha256: str
    query_count: int
    measured_query_count: int
    query_domain_distribution: dict[str, int]
    pipeline: FinalHybridPipelineConfig
    corpus: FinalHybridCorpusSummary
    recall_at_k: dict[int, float]
    pre_rerank_recall_at_10: float
    selected_evidence_complete_rate: float
    selected_evidence_precision_proxy: float
    provenance_pass_rate: float
    hard_constraint_pass_rate: float
    failure_counts: dict[str, int]
    stage_latency_ms: dict[str, LatencyAggregate]
    provider_errors: tuple[str, ...] = ()
    results: tuple[FinalHybridQueryResult, ...]


class _TimedEmbeddingProvider:
    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider
        self.model = provider.model
        self.version = provider.version
        self.dimension = getattr(provider, "dimension", None)
        self.document_call_ms: list[float] = []
        self.query_call_ms: list[float] = []

    def embed_documents(
        self, texts: Sequence[str]
    ) -> tuple[tuple[float, ...], ...]:
        started = perf_counter_ns()
        try:
            return self._provider.embed_documents(texts)
        finally:
            self.document_call_ms.append(_elapsed_ms(started))

    def embed_query(self, text: str) -> tuple[float, ...]:
        started = perf_counter_ns()
        try:
            return self._provider.embed_query(text)
        finally:
            self.query_call_ms.append(_elapsed_ms(started))


class _TimedReranker:
    def __init__(self, reranker: Reranker) -> None:
        self._reranker = reranker
        self.call_ms: list[float] = []
        self.last_diagnostic: RerankerDiagnostic | None = None

    def rerank(self, query: str, documents: Sequence[str], *, top_n: int):
        started = perf_counter_ns()
        try:
            return self._reranker.rerank(query, documents, top_n=top_n)
        except RerankerError as exc:
            self.last_diagnostic = exc.diagnostic
            raise
        finally:
            self.call_ms.append(_elapsed_ms(started))


class _TimedHybridRetriever(SharedHybridRetriever):
    def __init__(self) -> None:
        super().__init__(max_candidates=FUSED_MAX, rrf_k=RRF_K)
        self.last_fusion_ms = 0.0
        self.last_fused: tuple[RankedCandidate, ...] = ()

    def merge(self, **kwargs):
        started = perf_counter_ns()
        try:
            self.last_fused = super().merge(**kwargs)
            return self.last_fused
        finally:
            self.last_fusion_ms = _elapsed_ms(started)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_final_hybrid_benchmark(
    suite: BenchmarkSuite,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    *,
    holdout_sha256: str,
    enforce_live_providers: bool = True,
) -> FinalHybridBenchmarkReport:
    """Execute one complete frozen hybrid pass over ``suite``."""

    if enforce_live_providers:
        if not isinstance(embedding_provider, GeminiEmbeddingProvider):
            raise FinalHybridMeasurementError(
                "official baseline requires the real Gemini embedding adapter"
            )
        if not isinstance(reranker, CohereReranker):
            raise FinalHybridMeasurementError(
                "official baseline requires the real Cohere reranker adapter"
            )
        if (
            embedding_provider.model != EMBEDDING_MODEL
            or embedding_provider.dimension != EMBEDDING_DIMENSION
            or embedding_provider.version
            != "gemini-embedding-2:768:retrieval-format-v1"
            or reranker.model != RERANK_MODEL
        ):
            raise FinalHybridMeasurementError("provider configuration is not frozen")

    dimension = int(getattr(embedding_provider, "dimension", EMBEDDING_DIMENSION))
    target_version = (
        DEFAULT_EMBEDDING_VERSION
        if enforce_live_providers
        else f"{embedding_provider.version}:retrieval-unit-v2-structured"
    )
    records = tuple(_canonical_record(record) for record in suite.records)
    by_id = {record.record_id: record for record in records}
    builder = RetrievalUnitBuilder(max_chars=2_000, max_units=20)
    units_by_record = {
        record.record_id: builder.build(record)  # type: ignore[arg-type]
        for record in records
    }
    all_units = tuple(
        unit for record in records for unit in units_by_record[record.record_id]
    )

    timed_embedding = _TimedEmbeddingProvider(embedding_provider)
    repository = InMemoryVectorRepository(records)  # type: ignore[arg-type]
    indexing_started = perf_counter_ns()
    vectors = timed_embedding.embed_documents(
        tuple(
            format_embedding_document(by_id[unit.source_record_id], unit)  # type: ignore[arg-type]
            for unit in all_units
        )
    )
    if len(vectors) != len(all_units):
        raise FinalHybridMeasurementError(
            "Gemini returned the wrong benchmark document vector count"
        )
    rows_by_record: dict[str, list[PersistedEmbedding]] = {
        record.record_id: [] for record in records
    }
    for unit, vector in zip(all_units, vectors):
        rows_by_record[unit.source_record_id].append(
            PersistedEmbedding(
                source_record_id=unit.source_record_id,
                retrieval_unit_id=unit.retrieval_unit_id,
                source_content_hash=unit.source_content_hash,
                retrieval_content_hash=unit.retrieval_content_hash,
                embedding_model=timed_embedding.model,
                embedding_version=target_version,
                embedding=validate_vector(vector, dimension=dimension),
            )
        )
    for record in records:
        repository.persist_success(
            record, rows_by_record[record.record_id], target_version  # type: ignore[arg-type]
        )
    indexing_total_ms = _elapsed_ms(indexing_started)
    indexed_by_id = repository.records

    sparse_retriever = LocalBm25Retriever(k1=1.2, b=0.75)
    dense_retriever = PersistedSemanticRetriever(
        repository,
        timed_embedding,
        top_k=DENSE_TOP_K,
        min_score=VECTOR_MIN_SCORE,
        max_units_per_record=MAX_VECTOR_UNITS_PER_RECORD,
        dimension=dimension,
        target_version=target_version,
    )
    timed_reranker = _TimedReranker(reranker)
    hybrid = _TimedHybridRetriever()

    stage_samples: dict[str, list[float]] = {
        "corpus_indexing_total": [indexing_total_ms],
        "gemini_document_embedding_provider_call": list(
            timed_embedding.document_call_ms
        ),
        "sparse_local": [],
        "dense_total": [],
        "gemini_query_embedding_provider_call": [],
        "dense_local_compute": [],
        "fusion_local": [],
        "cohere_rerank_provider_call": [],
        "cohere_rate_limit_wait": [],
        "selection_local_overhead": [],
        "total_retrieval": [],
    }
    query_results: list[FinalHybridQueryResult] = []
    recall_values: dict[int, list[float]] = {1: [], 3: [], 5: []}
    pre_rerank_recall_10: list[float] = []
    selected_complete = selected_relevant = selected_total = 0
    provenance_passes = hard_constraint_passes = 0
    failures: Counter[str] = Counter()
    last_rerank_started_ns: int | None = None

    for case in suite.queries:
        population = tuple(indexed_by_id[item] for item in case.eligible_record_ids)
        population_by_id = {record.record_id: record for record in population}

        sparse_started = perf_counter_ns()
        sparse_hits = sparse_retriever.search(
            case.query, population, top_k=SPARSE_TOP_K, min_score=0.0
        )
        sparse_ms = _elapsed_ms(sparse_started)
        sparse = tuple(
            (population_by_id[hit.record_id], hit.score)
            for hit in sparse_hits
            if hit.record_id in population_by_id
        )

        before_query_calls = len(timed_embedding.query_call_ms)
        dense_started = perf_counter_ns()
        dense_hits = dense_retriever.search(
            case.query,
            domain=case.domain.value,
            allowed_records=population,  # type: ignore[arg-type]
            top_k=DENSE_TOP_K,
            min_score=VECTOR_MIN_SCORE,
        )
        dense_ms = _elapsed_ms(dense_started)
        if len(timed_embedding.query_call_ms) != before_query_calls + 1:
            raise FinalHybridMeasurementError(
                "each benchmark query must make exactly one Gemini query call"
            )
        query_provider_ms = timed_embedding.query_call_ms[-1]
        semantic = tuple(
            (hit.record, hit.score, hit.retrieval_unit_ids) for hit in dense_hits
        )

        eligible = set(case.eligible_record_ids)
        rate_limit_wait_ms = 0.0
        if enforce_live_providers and (sparse or semantic):
            if last_rerank_started_ns is not None:
                elapsed_seconds = (
                    perf_counter_ns() - last_rerank_started_ns
                ) / 1_000_000_000
                remaining = COHERE_MIN_INTERVAL_SECONDS - elapsed_seconds
                if remaining > 0:
                    wait_started = perf_counter_ns()
                    sleep(remaining)
                    rate_limit_wait_ms = _elapsed_ms(wait_started)
            last_rerank_started_ns = perf_counter_ns()
        before_rerank_calls = len(timed_reranker.call_ms)
        selection_started = perf_counter_ns()
        selection = hybrid.select(
            query=case.query,
            sparse=sparse,  # type: ignore[arg-type]
            semantic=semantic,  # type: ignore[arg-type]
            reranker=timed_reranker,
            top_n=RERANK_TOP_N,
            conclusively_invalid=lambda record: record.record_id not in eligible,
        )
        selection_ms = _elapsed_ms(selection_started)
        if selection.reranker_fallback:
            diagnostic = timed_reranker.last_diagnostic
            safe_context = (
                "category=transient status=None request_id=None rate_limit=()"
                if diagnostic is None
                else (
                    f"category={diagnostic.category} "
                    f"status={diagnostic.status_code} "
                    f"request_id={diagnostic.request_id} "
                    f"rate_limit={diagnostic.rate_limit_headers}"
                )
            )
            raise FinalHybridMeasurementError(
                f"Cohere reranker fell back for {case.query_id}; "
                f"official measurement is incomplete; {safe_context}"
            )
        valid_fused = tuple(
            candidate
            for candidate in hybrid.last_fused
            if candidate.record.record_id in eligible
        )
        if valid_fused and not selection.reranker_used:
            raise FinalHybridMeasurementError(
                "Cohere reranker was skipped for non-empty candidates"
            )
        rerank_ms = (
            timed_reranker.call_ms[-1]
            if len(timed_reranker.call_ms) == before_rerank_calls + 1
            else 0.0
        )

        sparse_ids = tuple(record.record_id for record, _score in sparse)
        dense_ids = tuple(hit.record.record_id for hit in dense_hits)
        fused_ids = tuple(candidate.record.record_id for candidate in valid_fused)
        selected_ids = tuple(
            candidate.record.record_id for candidate in selection.candidates
        )
        expected = set(case.expected_relevant_record_ids)
        query_recalls = {
            value: _recall(selected_ids[:value], expected) for value in (1, 3, 5)
        }
        query_pre_recall = _recall(fused_ids[:10], expected)
        if expected:
            for value in (1, 3, 5):
                recall_values[value].append(query_recalls[value])
            pre_rerank_recall_10.append(query_pre_recall)
        complete = bool(expected) and expected.issubset(selected_ids)
        selected_complete += int(complete)
        selected_relevant += len(expected.intersection(selected_ids))
        selected_total += len(selected_ids)
        provenance_ok = all(
            indexed_by_id[record_id].source_id in case.allowed_source_ids
            for record_id in (*fused_ids, *selected_ids)
        )
        constraints_ok = set((*fused_ids, *selected_ids)).issubset(eligible)
        provenance_passes += int(provenance_ok)
        hard_constraint_passes += int(constraints_ok)
        if not expected:
            failure = case.expected_failure_class
        elif not expected.intersection(fused_ids):
            failure = "RETRIEVAL"
        elif not complete:
            failure = "EVIDENCE_SELECTION_RANKING"
        else:
            failure = case.expected_failure_class
        failures[failure] += 1
        first_rank = next(
            (
                rank
                for rank, record_id in enumerate(selected_ids, start=1)
                if record_id in expected
            ),
            None,
        )
        fusion_ms = hybrid.last_fusion_ms
        local_overhead_ms = max(0.0, selection_ms - fusion_ms - rerank_ms)
        total_ms = sparse_ms + dense_ms + selection_ms
        per_query_latency = {
            "sparse_local": sparse_ms,
            "dense_total": dense_ms,
            "gemini_query_embedding_provider_call": query_provider_ms,
            "dense_local_compute": max(0.0, dense_ms - query_provider_ms),
            "fusion_local": fusion_ms,
            "cohere_rerank_provider_call": rerank_ms,
            "cohere_rate_limit_wait": rate_limit_wait_ms,
            "selection_local_overhead": local_overhead_ms,
            "total_retrieval": total_ms,
        }
        for stage, value in per_query_latency.items():
            stage_samples[stage].append(value)
        query_results.append(
            FinalHybridQueryResult(
                query_id=case.query_id,
                domain=case.domain.value,
                expected_relevant_ids=case.expected_relevant_record_ids,
                sparse_ids=sparse_ids,
                dense_ids=dense_ids,
                fused_ids=fused_ids,
                selected_ids=selected_ids,
                first_relevant_rank=first_rank,
                recall_at_1=query_recalls[1],
                recall_at_3=query_recalls[3],
                recall_at_5=query_recalls[5],
                pre_rerank_recall_at_10=query_pre_recall,
                selected_evidence_complete=complete,
                provenance_preserved=provenance_ok,
                hard_constraints_preserved=constraints_ok,
                rejected_by_hard_filter=selection.rejected_count,
                reranker_used=selection.reranker_used,
                observed_failure_class=failure,
                latency_ms=per_query_latency,
            )
        )

    measured = sum(bool(case.expected_relevant_record_ids) for case in suite.queries)
    return FinalHybridBenchmarkReport(
        benchmark_id=suite.benchmark_id,
        measured_at_utc=datetime.now(timezone.utc),
        holdout_sha256=holdout_sha256,
        query_count=len(suite.queries),
        measured_query_count=measured,
        query_domain_distribution=dict(
            sorted(Counter(case.domain.value for case in suite.queries).items())
        ),
        pipeline=FinalHybridPipelineConfig(),
        corpus=FinalHybridCorpusSummary(
            source="frozen holdout benchmark record projections",
            canonical_records=len(records),
            retrieval_units=len(all_units),
            vectors=len(vectors),
            domain_distribution=dict(
                sorted(Counter(record.domain for record in records).items())
            ),
        ),
        recall_at_k={
            value: _mean_or_zero(recall_values[value]) for value in (1, 3, 5)
        },
        pre_rerank_recall_at_10=_mean_or_zero(pre_rerank_recall_10),
        selected_evidence_complete_rate=(
            selected_complete / measured if measured else 0.0
        ),
        selected_evidence_precision_proxy=(
            selected_relevant / selected_total if selected_total else 0.0
        ),
        provenance_pass_rate=provenance_passes / len(suite.queries),
        hard_constraint_pass_rate=hard_constraint_passes / len(suite.queries),
        failure_counts=dict(sorted(failures.items())),
        stage_latency_ms={
            name: _aggregate(values)
            for name, values in stage_samples.items()
            if values
        },
        results=tuple(query_results),
    )


def write_report(
    report: FinalHybridBenchmarkReport, raw_path: Path, summary_path: Path
) -> None:
    """Write the first completed baseline without overwriting frozen evidence."""

    if raw_path.exists() or summary_path.exists():
        raise FileExistsError(
            "final hybrid baseline already exists; refusing to overwrite it"
        )
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(_summary_markdown(report), encoding="utf-8")


def _canonical_record(record: BenchmarkRecord) -> _BenchmarkCanonicalRecord:
    _, entity_type, entity_id = record.record_id.split(":", 2)
    return _BenchmarkCanonicalRecord(
        record_id=record.record_id,
        source_id=record.source_id,
        entity_id=entity_id,
        domain=record.domain.value,
        title=record.title,
        content=record.content,
        canonical_url=(
            "https://benchmark.invalid/"
            + hashlib.sha256(record.record_id.encode("utf-8")).hexdigest()
        ),
        content_hash=hashlib.sha256(record.content.encode("utf-8")).hexdigest(),
        metadata_json=_BenchmarkMetadata(entity_type=entity_type),
    )


def _aggregate(values: Sequence[float]) -> LatencyAggregate:
    ordered = sorted(values)
    return LatencyAggregate(
        p50_ms=median(ordered),
        p95_ms=ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
        mean_ms=mean(ordered),
        samples=len(ordered),
    )


def _recall(ids: Sequence[str], expected: set[str]) -> float:
    return len(expected.intersection(ids)) / len(expected) if expected else 0.0


def _mean_or_zero(values: Sequence[float]) -> float:
    return mean(values) if values else 0.0


def _elapsed_ms(started_ns: int) -> float:
    return (perf_counter_ns() - started_ns) / 1_000_000


def _summary_markdown(report: FinalHybridBenchmarkReport) -> str:
    lines = [
        f"# {report.label}",
        "",
        f"- Benchmark: `{report.benchmark_id}`",
        f"- Measured at: `{report.measured_at_utc.isoformat()}`",
        f"- Holdout SHA-256: `{report.holdout_sha256}`",
        f"- Queries: {report.query_count}",
        (
            "- Corpus: "
            f"{report.corpus.canonical_records} canonical records, "
            f"{report.corpus.retrieval_units} retrieval units, "
            f"{report.corpus.vectors} real Gemini vectors"
        ),
        "- Storage: isolated in-memory benchmark repository; no production DB",
        "",
        "## Frozen pipeline",
        "",
        "BM25 Top20 + Gemini dense Top20 -> RRF k=60 fused max20 -> "
        "conclusive hard-filter guard -> Cohere rerank-v4.0-fast Top5",
        "",
        "## Quality metrics",
        "",
        f"- Recall@1: {report.recall_at_k[1]:.4%}",
        f"- Recall@3: {report.recall_at_k[3]:.4%}",
        f"- Recall@5: {report.recall_at_k[5]:.4%}",
        f"- Pre-rerank Recall@10: {report.pre_rerank_recall_at_10:.4%}",
        (
            "- Selected-evidence completeness@5: "
            f"{report.selected_evidence_complete_rate:.4%}"
        ),
        (
            "- Selected-evidence precision proxy: "
            f"{report.selected_evidence_precision_proxy:.4%}"
        ),
        f"- Provenance preservation: {report.provenance_pass_rate:.4%}",
        f"- Hard-constraint preservation: {report.hard_constraint_pass_rate:.4%}",
        "",
        "## Latency",
        "",
        "Local benchmark wall time; provider-call timings include network and provider processing.",
        "",
        "| Stage | Samples | p50 ms | p95 ms | mean ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, latency in report.stage_latency_ms.items():
        lines.append(
            f"| {name} | {latency.samples} | {latency.p50_ms:.3f} | "
            f"{latency.p95_ms:.3f} | {latency.mean_ms:.3f} |"
        )
    lines.extend(
        (
            "",
            "## Failure taxonomy",
            "",
        )
    )
    for name, count in report.failure_counts.items():
        lines.append(f"- {name}: {count}")
    lines.extend(("", "Provider errors: none.", ""))
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the one-shot frozen V7 Day 3 final hybrid holdout"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    before_hash = sha256_file(args.input)
    if before_hash != FROZEN_HOLDOUT_SHA256:
        print(
            f"BLOCKED: frozen holdout SHA mismatch: {before_hash}",
            file=sys.stderr,
        )
        return 2
    if args.output.exists() or args.summary_output.exists():
        print(
            "BLOCKED: final hybrid baseline output already exists",
            file=sys.stderr,
        )
        return 2
    settings = Settings.from_environment()
    gemini_key = settings.api_key.get_secret_value()
    if not gemini_key:
        print("BLOCKED: Gemini credential unavailable", file=sys.stderr)
        return 2
    cohere_key = settings.cohere_api_key.get_secret_value()
    if not cohere_key:
        print("BLOCKED: Cohere credential unavailable", file=sys.stderr)
        return 2

    try:
        report = run_final_hybrid_benchmark(
            load_benchmark(args.input),
            GeminiEmbeddingProvider(
                gemini_key,
                model=EMBEDDING_MODEL,
                dimension=EMBEDDING_DIMENSION,
                format_version="retrieval-format-v1",
                timeout_seconds=20,
            ),
            CohereReranker(
                cohere_key,
                model=RERANK_MODEL,
                timeout_seconds=5,
            ),
            holdout_sha256=before_hash,
        )
    except Exception as exc:
        print(
            f"MEASUREMENT FAILED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    after_hash = sha256_file(args.input)
    if after_hash != before_hash:
        print("BLOCKED: frozen holdout changed during measurement", file=sys.stderr)
        return 2
    write_report(report, args.output, args.summary_output)
    print(
        json.dumps(
            {
                "label": report.label,
                "query_count": report.query_count,
                "raw_output": str(args.output),
                "summary_output": str(args.summary_output),
                "holdout_sha256": after_hash,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
