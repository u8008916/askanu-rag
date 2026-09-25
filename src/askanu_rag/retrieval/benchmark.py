"""Deterministic V7 retrieval benchmark primitives.

The benchmark deliberately sits outside the request path.  It measures the
current local sparse boundary and candidate alternatives without changing
source authority, conversation state, public API behaviour, or production
indexing configuration.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Literal, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from askanu_rag.models import AnswerState, Domain, ResultSetStatus
from askanu_rag.retrieval.query_expansion import expand_support_problem_query
from askanu_rag.retrieval.semantic import LocalBm25Retriever, LocalTfidfRetriever

BENCHMARK_K_VALUES = (1, 3, 5, 10, 20)


class BenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BenchmarkRecord(BenchmarkModel):
    """Approved-record projection sufficient for ranking and provenance checks."""

    record_id: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=200)
    domain: Domain
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=10_000)


class BenchmarkQuery(BenchmarkModel):
    """A pre-labelled query; labels are frozen before a pipeline is evaluated."""

    query_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    domain: Domain
    query: str = Field(min_length=1, max_length=2_000)
    query_type: str = Field(min_length=1, max_length=100)
    difficulty: Literal["easy", "medium", "difficult"]
    route: Literal["exact", "structured", "discovery"]
    eligible_record_ids: tuple[str, ...] = Field(max_length=50)
    expected_relevant_record_ids: tuple[str, ...] = Field(max_length=20)
    allowed_source_ids: tuple[str, ...] = Field(min_length=1, max_length=10)
    hard_constraints: tuple[str, ...] = Field(default_factory=tuple, max_length=12)
    expected_answer_state: AnswerState
    expected_result_status: ResultSetStatus
    population_complete: bool
    expected_failure_class: Literal[
        "NONE",
        "DATA",
        "ENTITY_RESOLUTION",
        "INTENT_CONSTRAINT",
        "RETRIEVAL",
        "EVIDENCE_SELECTION_RANKING",
        "REASONING_ORCHESTRATION",
        "RESPONSE",
    ] = "NONE"
    notes: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def labels_are_semantically_safe(self) -> "BenchmarkQuery":
        if len(set(self.eligible_record_ids)) != len(self.eligible_record_ids):
            raise ValueError("eligible record IDs must be unique")
        if len(set(self.expected_relevant_record_ids)) != len(
            self.expected_relevant_record_ids
        ):
            raise ValueError("expected relevant record IDs must be unique")
        if not set(self.expected_relevant_record_ids).issubset(
            self.eligible_record_ids
        ):
            raise ValueError("relevant records must be in the supported population")
        if self.expected_result_status == ResultSetStatus.RESULTS:
            if not self.expected_relevant_record_ids:
                raise ValueError("RESULTS requires pre-labelled relevant evidence")
        elif self.expected_result_status == ResultSetStatus.EMPTY and (
            self.expected_relevant_record_ids
        ):
            raise ValueError("EMPTY cannot label relevant result records")
        if self.expected_result_status == ResultSetStatus.EMPTY:
            if not self.population_complete:
                raise ValueError("EMPTY requires a completely evaluated population")
        if self.expected_result_status == ResultSetStatus.INCOMPLETE:
            if self.population_complete:
                raise ValueError("INCOMPLETE requires an incomplete population")
            if self.expected_answer_state not in {
                AnswerState.PARTIAL,
                AnswerState.UNKNOWN,
            }:
                raise ValueError("INCOMPLETE cannot claim confirmed evidence")
        return self


class BenchmarkSuite(BenchmarkModel):
    schema_version: Literal[1] = 1
    benchmark_id: str
    labelled_before_run: Literal[True] = True
    records: tuple[BenchmarkRecord, ...] = Field(min_length=1)
    queries: tuple[BenchmarkQuery, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def references_are_valid(self) -> "BenchmarkSuite":
        records = {record.record_id: record for record in self.records}
        if len(records) != len(self.records):
            raise ValueError("benchmark record IDs must be unique")
        query_ids = {query.query_id for query in self.queries}
        if len(query_ids) != len(self.queries):
            raise ValueError("benchmark query IDs must be unique")
        for query in self.queries:
            missing = set(query.eligible_record_ids).difference(records)
            if missing:
                raise ValueError(
                    f"{query.query_id} references missing records: {sorted(missing)}"
                )
            for record_id in query.eligible_record_ids:
                record = records[record_id]
                if record.domain != query.domain:
                    raise ValueError(
                        f"{query.query_id} population crosses its domain"
                    )
                if record.source_id not in query.allowed_source_ids:
                    raise ValueError(
                        f"{query.query_id} population crosses source authority"
                    )
        return self


class CandidateRetriever(Protocol):
    name: str

    def retrieve(
        self,
        query: BenchmarkQuery,
        records: tuple[BenchmarkRecord, ...],
        *,
        top_k: int,
    ) -> tuple[BenchmarkRecord, ...]: ...


class CurrentSparseBaseline:
    """Current deterministic paths plus the existing local TF-IDF retriever."""

    name = "current-deterministic-plus-local-tfidf"

    def __init__(self, *, min_score: float = 0.2) -> None:
        if not 0 <= min_score <= 1:
            raise ValueError("min_score must be between 0 and 1")
        self._min_score = min_score
        self._sparse = LocalTfidfRetriever()

    def retrieve(
        self,
        query: BenchmarkQuery,
        records: tuple[BenchmarkRecord, ...],
        *,
        top_k: int,
    ) -> tuple[BenchmarkRecord, ...]:
        if query.route in {"exact", "structured"}:
            return records[:top_k]
        # The configured Jobs request path has no local sparse fallback before
        # Day 3; semantic Jobs discovery requires an injected vector retriever.
        if query.domain == Domain.JOBS:
            return ()
        return self._sparse_retrieve(query, records, top_k=top_k)

    def _sparse_retrieve(
        self,
        query: BenchmarkQuery,
        records: tuple[BenchmarkRecord, ...],
        *,
        top_k: int,
    ) -> tuple[BenchmarkRecord, ...]:
        hits = self._sparse.search(
            query.query,
            records,  # type: ignore[arg-type] -- frozen projection has same fields
            top_k=top_k,
            min_score=self._min_score,
        )
        by_id = {record.record_id: record for record in records}
        return tuple(by_id[hit.record_id] for hit in hits if hit.record_id in by_id)


class SupportExpansionExperiment(CurrentSparseBaseline):
    """Current sparse pipeline plus the bounded Support problem vocabulary."""

    name = "local-tfidf-with-bounded-support-expansion"

    def retrieve(
        self,
        query: BenchmarkQuery,
        records: tuple[BenchmarkRecord, ...],
        *,
        top_k: int,
    ) -> tuple[BenchmarkRecord, ...]:
        if query.domain == Domain.SUPPORT and query.route == "discovery":
            query = query.model_copy(
                update={"query": expand_support_problem_query(query.query)}
            )
        return super().retrieve(query, records, top_k=top_k)


class Day3BoundedImprovement(SupportExpansionExperiment):
    """Historical tuned Support expansion plus TF-IDF Jobs fallback."""

    name = "day3-bounded-support-expansion-and-jobs-sparse-fallback"

    def retrieve(
        self,
        query: BenchmarkQuery,
        records: tuple[BenchmarkRecord, ...],
        *,
        top_k: int,
    ) -> tuple[BenchmarkRecord, ...]:
        if query.domain == Domain.JOBS and query.route == "discovery":
            return self._sparse_retrieve(query, records, top_k=top_k)
        return super().retrieve(query, records, top_k=top_k)


class LocalBm25Experiment:
    """Frozen benchmark adapter around the selected runtime BM25 retriever."""

    name = "selected-local-bm25"

    def __init__(self, *, k1: float = 1.2, b: float = 0.75) -> None:
        self._retriever = LocalBm25Retriever(k1=k1, b=b)

    def retrieve(
        self,
        query: BenchmarkQuery,
        records: tuple[BenchmarkRecord, ...],
        *,
        top_k: int,
    ) -> tuple[BenchmarkRecord, ...]:
        if query.route in {"exact", "structured"}:
            return records[:top_k]
        hits = self._retriever.search(
            query.query,
            records,  # type: ignore[arg-type] -- projection has title/content/ID
            top_k=top_k,
            min_score=0.0,
        )
        by_id = {record.record_id: record for record in records}
        return tuple(
            by_id[hit.record_id]
            for hit in hits
            if hit.record_id in by_id
        )


class QueryResult(BenchmarkModel):
    query_id: str
    candidate_ids: tuple[str, ...]
    first_relevant_rank: int | None
    selected_evidence_ids: tuple[str, ...]
    selected_evidence_complete: bool
    provenance_preserved: bool
    hard_constraints_preserved: bool
    observed_failure_class: str


class LatencySummary(BenchmarkModel):
    p50_ms: float
    p95_ms: float
    samples: int


class BenchmarkReport(BenchmarkModel):
    benchmark_id: str
    pipeline: str
    query_count: int
    measured_query_count: int
    recall_at_k: dict[int, float]
    selected_evidence_complete_rate: float
    selected_evidence_precision: float
    retrieval_latency_p50_ms: float
    retrieval_latency_p95_ms: float
    domain_latency_p50_ms: dict[str, float]
    retrieval_latency_by_k_ms: dict[int, LatencySummary]
    route_latency_ms: dict[str, LatencySummary]
    interaction_latency_ms: dict[str, LatencySummary]
    domain_latency_ms: dict[str, LatencySummary]
    domain_recall_at_5: dict[str, float]
    provenance_pass_rate: float
    hard_constraint_pass_rate: float
    failure_counts: dict[str, int]
    results: tuple[QueryResult, ...]


def load_benchmark(path: Path) -> BenchmarkSuite:
    return BenchmarkSuite.model_validate_json(path.read_text(encoding="utf-8"))


def evaluate_benchmark(
    suite: BenchmarkSuite,
    retriever: CandidateRetriever,
    *,
    selection_k: int = 5,
    latency_repetitions: int = 25,
) -> BenchmarkReport:
    if selection_k < 1:
        raise ValueError("selection_k must be positive")
    if latency_repetitions < 1:
        raise ValueError("latency repetitions must be positive")

    by_id = {record.record_id: record for record in suite.records}
    recalls: dict[int, list[float]] = {value: [] for value in BENCHMARK_K_VALUES}
    domain_recalls: dict[str, list[float]] = {}
    latency_by_k: dict[int, list[float]] = {
        value: [] for value in BENCHMARK_K_VALUES
    }
    route_latencies: dict[str, list[float]] = {}
    interaction_latencies: dict[str, list[float]] = {}
    domain_latencies: dict[str, list[float]] = {}
    latencies: list[float] = []
    results: list[QueryResult] = []
    selected_complete = 0
    selected_relevant = 0
    selected_total = 0
    provenance_passes = 0
    hard_constraint_passes = 0
    failure_counts: Counter[str] = Counter()

    for case in suite.queries:
        population = tuple(by_id[record_id] for record_id in case.eligible_record_ids)
        ranked = retriever.retrieve(case, population, top_k=max(BENCHMARK_K_VALUES))
        ranked_ids = tuple(record.record_id for record in ranked)
        expected = set(case.expected_relevant_record_ids)
        first_rank = next(
            (index for index, record_id in enumerate(ranked_ids, start=1) if record_id in expected),
            None,
        )
        if expected:
            for value in BENCHMARK_K_VALUES:
                recalls[value].append(len(expected.intersection(ranked_ids[:value])) / len(expected))
            domain_recalls.setdefault(case.domain.value, []).append(
                len(expected.intersection(ranked_ids[:5])) / len(expected)
            )
        selected_ids = ranked_ids[:selection_k]
        complete = bool(expected) and expected.issubset(selected_ids)
        selected_complete += int(complete)
        selected_relevant += len(expected.intersection(selected_ids))
        selected_total += len(selected_ids)
        provenance_ok = all(
            record.source_id in case.allowed_source_ids for record in ranked
        )
        constraints_ok = set(ranked_ids).issubset(case.eligible_record_ids)
        provenance_passes += int(provenance_ok)
        hard_constraint_passes += int(constraints_ok)

        if not expected:
            observed_failure = case.expected_failure_class
        elif not expected.intersection(ranked_ids):
            observed_failure = "RETRIEVAL"
        elif not complete:
            observed_failure = "EVIDENCE_SELECTION_RANKING"
        else:
            observed_failure = case.expected_failure_class
        failure_counts[observed_failure] += 1
        results.append(
            QueryResult(
                query_id=case.query_id,
                candidate_ids=ranked_ids,
                first_relevant_rank=first_rank,
                selected_evidence_ids=selected_ids,
                selected_evidence_complete=complete,
                provenance_preserved=provenance_ok,
                hard_constraints_preserved=constraints_ok,
                observed_failure_class=observed_failure,
            )
        )

        for value in BENCHMARK_K_VALUES:
            for _ in range(latency_repetitions):
                started = perf_counter_ns()
                retriever.retrieve(case, population, top_k=value)
                elapsed_ms = (perf_counter_ns() - started) / 1_000_000
                latency_by_k[value].append(elapsed_ms)
                if value == max(BENCHMARK_K_VALUES):
                    latencies.append(elapsed_ms)
                    route_latencies.setdefault(case.route, []).append(elapsed_ms)
                    interaction_latencies.setdefault(
                        _interaction_class(case), []
                    ).append(elapsed_ms)
                    domain_latencies.setdefault(case.domain.value, []).append(
                        elapsed_ms
                    )

    measured = sum(bool(query.expected_relevant_record_ids) for query in suite.queries)
    return BenchmarkReport(
        benchmark_id=suite.benchmark_id,
        pipeline=retriever.name,
        query_count=len(suite.queries),
        measured_query_count=measured,
        recall_at_k={
            value: _mean(recalls[value]) for value in BENCHMARK_K_VALUES
        },
        selected_evidence_complete_rate=(selected_complete / measured if measured else 0.0),
        selected_evidence_precision=(selected_relevant / selected_total if selected_total else 0.0),
        retrieval_latency_p50_ms=_percentile(latencies, 0.50),
        retrieval_latency_p95_ms=_percentile(latencies, 0.95),
        domain_latency_p50_ms={
            domain: _percentile(values, 0.50)
            for domain, values in sorted(domain_latencies.items())
        },
        retrieval_latency_by_k_ms={
            value: _latency_summary(latency_by_k[value])
            for value in BENCHMARK_K_VALUES
        },
        route_latency_ms={
            route: _latency_summary(values)
            for route, values in sorted(route_latencies.items())
        },
        interaction_latency_ms={
            interaction: _latency_summary(values)
            for interaction, values in sorted(interaction_latencies.items())
        },
        domain_latency_ms={
            domain: _latency_summary(values)
            for domain, values in sorted(domain_latencies.items())
        },
        domain_recall_at_5={
            domain: _mean(values) for domain, values in sorted(domain_recalls.items())
        },
        provenance_pass_rate=provenance_passes / len(suite.queries),
        hard_constraint_pass_rate=hard_constraint_passes / len(suite.queries),
        failure_counts=dict(sorted(failure_counts.items())),
        results=tuple(results),
    )


def report_json(report: BenchmarkReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _latency_summary(values: Sequence[float]) -> LatencySummary:
    return LatencySummary(
        p50_ms=_percentile(values, 0.50),
        p95_ms=_percentile(values, 0.95),
        samples=len(values),
    )


def _interaction_class(query: BenchmarkQuery) -> str:
    if query.query_type in {
        "resolved_follow_up",
        "resolved_time_refinement",
        "retained_resultset_ordinal",
        "continue_resultset",
    }:
        return "follow_up"
    if query.route == "exact":
        return "lookup"
    return "discovery"


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if quantile == 0.50:
        return median(ordered)
    rank = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[rank]
