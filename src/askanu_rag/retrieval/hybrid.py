"""Shared deterministic-first candidate merge for every AskANU domain."""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from enum import IntEnum
from time import perf_counter
from typing import Callable, Iterable

from askanu_rag.models import CommonRecord
from askanu_rag.retrieval.formatting import format_rerank_document
from askanu_rag.retrieval.reranking import Reranker, RerankerUnavailableError

LOGGER = logging.getLogger("askanu_rag.retrieval")


class CandidateTier(IntEnum):
    EXACT = 1
    STRUCTURED = 2
    DISCOVERY = 3


@dataclass(frozen=True)
class RankedCandidate:
    record: CommonRecord
    tier: CandidateTier
    sparse_score: float | None = None
    semantic_score: float | None = None
    retrieval_unit_ids: tuple[str, ...] = ()
    sparse_rank: int | None = None
    semantic_rank: int | None = None
    rrf_score: float = 0.0


@dataclass(frozen=True)
class HybridSelection:
    candidates: tuple[RankedCandidate, ...]
    sparse_count: int
    dense_count: int
    fused_count: int
    rejected_count: int
    reranker_used: bool
    reranker_fallback: bool
    provider_error_category: str | None = None


class SharedHybridRetriever:
    """Merge unlike signals by precedence, then rank only within a tier."""

    def __init__(self, *, max_candidates: int = 20, rrf_k: int = 60) -> None:
        if not 1 <= max_candidates <= 50:
            raise ValueError("max_candidates must be between 1 and 50")
        if not 1 <= rrf_k <= 1_000:
            raise ValueError("rrf_k must be between 1 and 1000")
        self.max_candidates = max_candidates
        self.rrf_k = rrf_k

    def merge(
        self,
        *,
        exact: Iterable[CommonRecord] = (),
        structured: Iterable[CommonRecord] = (),
        sparse: Iterable[tuple[CommonRecord, float]] = (),
        semantic: Iterable[tuple[CommonRecord, float, tuple[str, ...]]] = (),
    ) -> tuple[RankedCandidate, ...]:
        by_id: dict[str, RankedCandidate] = {}

        def keep(candidate: RankedCandidate) -> None:
            previous = by_id.get(candidate.record.record_id)
            if previous is not None and (
                previous.tier == candidate.tier == CandidateTier.DISCOVERY
            ):
                by_id[candidate.record.record_id] = RankedCandidate(
                    record=previous.record,
                    tier=previous.tier,
                    sparse_score=max_optional(
                        previous.sparse_score, candidate.sparse_score
                    ),
                    semantic_score=max_optional(
                        previous.semantic_score, candidate.semantic_score
                    ),
                    retrieval_unit_ids=tuple(
                        sorted(
                            set(
                                previous.retrieval_unit_ids
                                + candidate.retrieval_unit_ids
                            )
                        )
                    ),
                    sparse_rank=min_optional(
                        previous.sparse_rank, candidate.sparse_rank
                    ),
                    semantic_rank=min_optional(
                        previous.semantic_rank, candidate.semantic_rank
                    ),
                )
            elif previous is None or candidate.tier < previous.tier:
                by_id[candidate.record.record_id] = candidate

        for record in exact:
            keep(RankedCandidate(record, CandidateTier.EXACT))
        for record in structured:
            keep(RankedCandidate(record, CandidateTier.STRUCTURED))
        for rank, (record, score) in enumerate(sparse, start=1):
            if math.isfinite(score):
                keep(
                    RankedCandidate(
                        record,
                        CandidateTier.DISCOVERY,
                        sparse_score=score,
                        sparse_rank=rank,
                    )
                )
        for rank, (record, score, unit_ids) in enumerate(semantic, start=1):
            if math.isfinite(score):
                keep(
                    RankedCandidate(
                        record,
                        CandidateTier.DISCOVERY,
                        semantic_score=score,
                        retrieval_unit_ids=unit_ids,
                        semantic_rank=rank,
                    )
                )
        scored = tuple(self._with_rrf(candidate) for candidate in by_id.values())
        return tuple(sorted(scored, key=self._key)[: self.max_candidates])

    def select(
        self,
        *,
        query: str,
        sparse: Iterable[tuple[CommonRecord, float]] = (),
        semantic: Iterable[tuple[CommonRecord, float, tuple[str, ...]]] = (),
        reranker: Reranker | None = None,
        top_n: int = 5,
        conclusively_invalid: Callable[[CommonRecord], bool] | None = None,
        sparse_status: str = "ok",
        dense_status: str = "ok",
    ) -> HybridSelection:
        sparse_values = tuple(sparse)
        semantic_values = tuple(semantic)
        fused = self.merge(sparse=sparse_values, semantic=semantic_values)
        predicate = conclusively_invalid or (lambda _record: False)
        valid = tuple(item for item in fused if not predicate(item.record))
        rejected = len(fused) - len(valid)
        reranker_used = False
        fallback = reranker is None
        error_category = "not_configured" if reranker is None else None
        selected = valid[:top_n]
        started = perf_counter()
        if reranker is not None and valid:
            documents = tuple(
                format_rerank_document(item.record, item.retrieval_unit_ids)
                for item in valid[:20]
            )
            try:
                ranked = reranker.rerank(
                    query, documents, top_n=min(top_n, len(documents))
                )
                selected = tuple(valid[item.index] for item in ranked)
                reranker_used = True
            except RerankerUnavailableError:
                fallback = True
                error_category = "transient"
                selected = valid[:top_n]
        LOGGER.info(
            "hybrid_selection sparse_status=%s dense_status=%s "
            "sparse_count=%s dense_count=%s fused_count=%s "
            "rejected_count=%s selected_count=%s reranker_used=%s "
            "reranker_fallback=%s provider_error_category=%s latency_ms=%.2f",
            sparse_status, dense_status,
            len(sparse_values), len(semantic_values), len(fused), rejected,
            len(selected), reranker_used, fallback, error_category,
            (perf_counter() - started) * 1000,
        )
        return HybridSelection(
            selected, len(sparse_values), len(semantic_values), len(fused), rejected,
            reranker_used, fallback, error_category,
        )

    def _with_rrf(self, candidate: RankedCandidate) -> RankedCandidate:
        score = sum(
            1.0 / (self.rrf_k + rank)
            for rank in (candidate.sparse_rank, candidate.semantic_rank)
            if rank is not None
        )
        return RankedCandidate(
            record=candidate.record,
            tier=candidate.tier,
            sparse_score=candidate.sparse_score,
            semantic_score=candidate.semantic_score,
            retrieval_unit_ids=candidate.retrieval_unit_ids,
            sparse_rank=candidate.sparse_rank,
            semantic_rank=candidate.semantic_rank,
            rrf_score=score,
        )

    def _key(self, candidate: RankedCandidate) -> tuple[object, ...]:
        # Reciprocal-rank fusion compares positions, never unlike raw scores.
        return (
            candidate.tier,
            -candidate.rrf_score,
            candidate.record.record_id,
        )


def max_optional(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None


def min_optional(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None
