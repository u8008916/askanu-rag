"""Shared deterministic-first candidate merge for every AskANU domain."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable

from askanu_rag.models import CommonRecord


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


class SharedHybridRetriever:
    """Merge unlike signals by precedence, then rank only within a tier."""

    def __init__(self, *, max_candidates: int = 10) -> None:
        if not 1 <= max_candidates <= 50:
            raise ValueError("max_candidates must be between 1 and 50")
        self.max_candidates = max_candidates

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
        return tuple(sorted(by_id.values(), key=self._key)[: self.max_candidates])

    @staticmethod
    def _key(candidate: RankedCandidate) -> tuple[object, ...]:
        signal_count = int(candidate.sparse_rank is not None) + int(
            candidate.semantic_rank is not None
        )
        # Reciprocal-rank fusion compares positions, never unlike raw scores.
        fused_rank = sum(
            1.0 / (60 + rank)
            for rank in (candidate.sparse_rank, candidate.semantic_rank)
            if rank is not None
        )
        return (
            candidate.tier,
            -signal_count,
            -fused_rank,
            candidate.record.record_id,
        )


def max_optional(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None


def min_optional(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None
