"""Shared persisted-vector indexing and semantic retrieval primitives."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol, Sequence

from askanu_rag.database import ConnectionFactory, RepositoryUnavailableError
from askanu_rag.index_lifecycle import (
    IndexAction,
    IndexTaskIdentity,
    plan_index_action,
    resolve_index_result,
)
from askanu_rag.models import CommonRecord
from askanu_rag.retrieval.embeddings import EmbeddingProvider, validate_vector
from askanu_rag.retrieval.units import RetrievalUnit, RetrievalUnitBuilder


@dataclass(frozen=True)
class PersistedEmbedding:
    source_record_id: str
    retrieval_unit_id: str
    source_content_hash: str
    retrieval_content_hash: str
    embedding_model: str
    embedding_version: str
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class VectorHit:
    record: CommonRecord
    score: float
    retrieval_unit_ids: tuple[str, ...]


class VectorRepository(Protocol):
    def existing_units(
        self,
        record_id: str,
        source_content_hash: str,
        embedding_model: str,
        embedding_version: str,
    ) -> dict[str, frozenset[str]]: ...

    def persist_success(
        self,
        record: CommonRecord,
        rows: Sequence[PersistedEmbedding],
        target_version: str,
    ) -> None: ...

    def persist_failure(self, record: CommonRecord) -> None: ...

    def search(
        self,
        query_vector: Sequence[float],
        *,
        domain: str,
        embedding_model: str,
        embedding_version: str,
        allowed_record_ids: Sequence[str] = (),
        top_k: int,
        min_score: float,
        max_units_per_record: int,
    ) -> tuple[VectorHit, ...]: ...


def effective_embedding_version(model_version: str, policy_version: str) -> str:
    """Bind model and retrieval-unit policy into one stored rollout version."""

    if not model_version.strip() or not policy_version.strip():
        raise ValueError("embedding and retrieval policy versions must not be blank")
    return f"{model_version.strip()}+{policy_version.strip()}"


class EmbeddingIndexService:
    """Explicit, bounded indexer; scheduling remains outside the RAG service."""

    def __init__(
        self,
        repository: VectorRepository,
        provider: EmbeddingProvider,
        *,
        unit_builder: RetrievalUnitBuilder | None = None,
        dimension: int | None = None,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.unit_builder = unit_builder or RetrievalUnitBuilder()
        self.dimension = dimension
        self.target_version = effective_embedding_version(
            provider.version, self.unit_builder.policy_version
        )

    def index_record(
        self, record: CommonRecord, *, explicit_retry: bool = False
    ) -> int:
        decision = plan_index_action(
            record,
            explicit_retry=explicit_retry,
            target_version=self.target_version,
        )
        if decision.action is IndexAction.NONE:
            return 0
        if decision.action not in {
            IndexAction.INDEX_CONTENT_CHANGE,
            IndexAction.RETRY,
            IndexAction.REINDEX_VERSION,
        }:
            raise ValueError("record is not eligible for indexing")

        units = self.unit_builder.build(record)
        existing = self.repository.existing_units(
            record.record_id,
            record.content_hash,
            self.provider.model,
            self.target_version,
        )
        missing = tuple(
            unit
            for unit in units
            if unit.retrieval_content_hash
            not in existing.get(unit.retrieval_unit_id, frozenset())
        )
        task = IndexTaskIdentity(
            record.record_id, record.content_hash, self.target_version
        )
        try:
            vectors = (
                self.provider.embed_documents([unit.content for unit in missing])
                if missing
                else ()
            )
            if len(vectors) != len(missing):
                raise ValueError("embedding provider returned the wrong batch size")
            rows = tuple(
                self._row(unit, vector) for unit, vector in zip(missing, vectors)
            )
        except Exception:
            failure = resolve_index_result(record, task, succeeded=False)
            if failure.action is IndexAction.APPLY_FAILURE:
                self.repository.persist_failure(record)
            raise
        result = resolve_index_result(
            record,
            task,
            succeeded=True,
            produced_version=self.target_version,
        )
        if result.action is not IndexAction.APPLY_SUCCESS:
            return 0
        # Persistence failures have an unknown commit outcome. Do not issue a
        # second blind write that could overwrite a successful commit.
        self.repository.persist_success(record, rows, self.target_version)
        return len(rows)

    def _row(
        self, unit: RetrievalUnit, vector: Sequence[float]
    ) -> PersistedEmbedding:
        return PersistedEmbedding(
            source_record_id=unit.source_record_id,
            retrieval_unit_id=unit.retrieval_unit_id,
            source_content_hash=unit.source_content_hash,
            retrieval_content_hash=unit.retrieval_content_hash,
            embedding_model=self.provider.model,
            embedding_version=self.target_version,
            embedding=validate_vector(vector, dimension=self.dimension),
        )


class PersistedSemanticRetriever:
    """Embed one query and retrieve only source-rehydrated current evidence."""

    uses_persistent_index = True

    def __init__(
        self,
        repository: VectorRepository,
        provider: EmbeddingProvider,
        *,
        top_k: int = 5,
        min_score: float = 0.35,
        max_units_per_record: int = 3,
        dimension: int | None = None,
        retrieval_policy_version: str | None = None,
    ) -> None:
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        if not 0 < min_score <= 1:
            raise ValueError("min_score must be in (0, 1]")
        if not 1 <= max_units_per_record <= 20:
            raise ValueError("max_units_per_record must be between 1 and 20")
        self.repository = repository
        self.provider = provider
        self.top_k = top_k
        self.min_score = min_score
        self.max_units_per_record = max_units_per_record
        self.dimension = dimension
        policy_version = retrieval_policy_version or RetrievalUnitBuilder().policy_version
        self.target_version = effective_embedding_version(provider.version, policy_version)

    def search(
        self,
        query: str,
        *,
        domain: str,
        allowed_records: Sequence[CommonRecord] = (),
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> tuple[VectorHit, ...]:
        limit = self.top_k if top_k is None else top_k
        threshold = self.min_score if min_score is None else min_score
        vector = validate_vector(
            self.provider.embed_query(query), dimension=self.dimension
        )
        return self.repository.search(
            vector,
            domain=domain,
            embedding_model=self.provider.model,
            embedding_version=self.target_version,
            allowed_record_ids=tuple(record.record_id for record in allowed_records),
            top_k=limit,
            min_score=threshold,
            max_units_per_record=self.max_units_per_record,
        )


class InMemoryVectorRepository:
    """Faithful test/local adapter with source-level dedupe and freshness gates."""

    def __init__(self, records: Iterable[CommonRecord]) -> None:
        self.records = {record.record_id: record for record in records}
        self.rows: dict[
            tuple[str, str, str, str, str], PersistedEmbedding
        ] = {}

    def existing_units(
        self,
        record_id: str,
        source_content_hash: str,
        embedding_model: str,
        embedding_version: str,
    ) -> dict[str, frozenset[str]]:
        hashes: dict[str, set[str]] = defaultdict(set)
        for (
            row_record_id,
            unit_id,
            retrieval_hash,
            model,
            version,
        ), row in self.rows.items():
            if (
                row_record_id == record_id
                and row.source_content_hash == source_content_hash
                and model == embedding_model
                and version == embedding_version
            ):
                hashes[unit_id].add(retrieval_hash)
        return {unit_id: frozenset(values) for unit_id, values in hashes.items()}

    def persist_success(
        self,
        record: CommonRecord,
        rows: Sequence[PersistedEmbedding],
        target_version: str,
    ) -> None:
        current = self.records.get(record.record_id)
        if (
            current is None
            or current.content_hash != record.content_hash
            or current.index_status != record.index_status
            or current.embedding_version != record.embedding_version
        ):
            raise ValueError("source/index state changed before embedding commit")
        for row in rows:
            key = (
                row.source_record_id,
                row.retrieval_unit_id,
                row.retrieval_content_hash,
                row.embedding_model,
                row.embedding_version,
            )
            self.rows[key] = row
        self.records[record.record_id] = current.model_copy(
            update={"index_status": "INDEXED", "embedding_version": target_version}
        )

    def persist_failure(self, record: CommonRecord) -> None:
        current = self.records.get(record.record_id)
        if (
            current is not None
            and current.content_hash == record.content_hash
            and current.index_status == record.index_status
            and current.embedding_version == record.embedding_version
            and not (
                record.index_status == "INDEXED"
                and record.embedding_version is not None
            )
        ):
            self.records[record.record_id] = current.model_copy(
                update={"index_status": "FAILED"}
            )

    def search(
        self,
        query_vector: Sequence[float],
        *,
        domain: str,
        embedding_model: str,
        embedding_version: str,
        allowed_record_ids: Sequence[str] = (),
        top_k: int,
        min_score: float,
        max_units_per_record: int,
    ) -> tuple[VectorHit, ...]:
        query = validate_vector(query_vector)
        allowed = set(allowed_record_ids)
        scores: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for row in self.rows.values():
            record = self.records.get(row.source_record_id)
            if (
                record is None
                or record.domain != domain
                or (allowed and record.record_id not in allowed)
                or record.index_status != "INDEXED"
                or record.embedding_version != embedding_version
                or row.source_content_hash != record.content_hash
                or row.embedding_model != embedding_model
                or row.embedding_version != embedding_version
                or len(row.embedding) != len(query)
            ):
                continue
            score = _cosine(query, row.embedding)
            if math.isfinite(score) and score >= min_score:
                scores[record.record_id].append((score, row.retrieval_unit_id))
        hits = []
        for record_id, unit_scores in scores.items():
            ranked = sorted(unit_scores, key=lambda item: (-item[0], item[1]))
            hits.append(
                VectorHit(
                    self.records[record_id],
                    ranked[0][0],
                    tuple(unit_id for _, unit_id in ranked[:max_units_per_record]),
                )
            )
        return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.record.record_id))[:top_k])


class PostgresVectorRepository:
    """pgvector adapter; exact cosine search is intentionally used for MVP."""

    _SOURCE_COLUMNS = (
        "record_id",
        "source_id",
        "entity_id",
        "domain",
        "title",
        "content",
        "canonical_url",
        "status",
        "effective_from",
        "effective_to",
        "collected_at",
        "last_seen_at",
        "content_hash",
        "embedding_version",
        "index_status",
        "metadata_json",
    )

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def existing_units(
        self,
        record_id: str,
        source_content_hash: str,
        embedding_model: str,
        embedding_version: str,
    ) -> dict[str, frozenset[str]]:
        query = """
            SELECT retrieval_unit_id, retrieval_content_hash
            FROM source_record_embeddings
            WHERE source_record_id = %s AND embedding_model = %s
              AND embedding_version = %s AND source_content_hash = %s
        """
        try:
            with self._connection_factory() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        query,
                        (
                            record_id,
                            embedding_model,
                            embedding_version,
                            source_content_hash,
                        ),
                    )
                    rows = cursor.fetchall()
        except Exception:
            raise RepositoryUnavailableError() from None
        hashes: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            hashes[row["retrieval_unit_id"]].add(row["retrieval_content_hash"])
        return {unit_id: frozenset(values) for unit_id, values in hashes.items()}

    def persist_success(
        self,
        record: CommonRecord,
        rows: Sequence[PersistedEmbedding],
        target_version: str,
    ) -> None:
        try:
            with self._connection_factory() as connection:
                with connection.cursor() as cursor:
                    for row in rows:
                        cursor.execute(
                            """
                            INSERT INTO source_record_embeddings (
                                source_record_id, retrieval_unit_id,
                                source_content_hash, retrieval_content_hash,
                                embedding_model, embedding_version, embedding
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                            ON CONFLICT (
                                source_record_id, retrieval_unit_id,
                                retrieval_content_hash, embedding_model,
                                embedding_version
                            ) DO UPDATE SET
                                source_content_hash = EXCLUDED.source_content_hash,
                                embedding = EXCLUDED.embedding,
                                updated_at = now()
                            """,
                            (
                                row.source_record_id,
                                row.retrieval_unit_id,
                                row.source_content_hash,
                                row.retrieval_content_hash,
                                row.embedding_model,
                                row.embedding_version,
                                _vector_literal(row.embedding),
                            ),
                        )
                    cursor.execute(
                        """
                        UPDATE source_records
                        SET index_status = 'INDEXED', embedding_version = %s
                        WHERE record_id = %s AND content_hash = %s
                          AND index_status = %s
                          AND embedding_version IS NOT DISTINCT FROM %s
                        """,
                        (
                            target_version,
                            record.record_id,
                            record.content_hash,
                            record.index_status,
                            record.embedding_version,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError(
                            "source/index state changed before embedding commit"
                        )
        except Exception:
            raise RepositoryUnavailableError() from None

    def persist_failure(self, record: CommonRecord) -> None:
        # A failed model/policy rollout must not disable a still-current LKG
        # vector. PENDING/FAILED current content has no usable LKG and is marked
        # failed with a compare-and-set so a late failure cannot clobber a
        # concurrent successful index commit.
        if record.index_status == "INDEXED" and record.embedding_version is not None:
            return
        try:
            with self._connection_factory() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE source_records SET index_status = 'FAILED'
                        WHERE record_id = %s AND content_hash = %s
                          AND index_status = %s
                          AND embedding_version IS NOT DISTINCT FROM %s
                        """,
                        (
                            record.record_id,
                            record.content_hash,
                            record.index_status,
                            record.embedding_version,
                        ),
                    )
        except Exception:
            raise RepositoryUnavailableError() from None

    def search(
        self,
        query_vector: Sequence[float],
        *,
        domain: str,
        embedding_model: str,
        embedding_version: str,
        allowed_record_ids: Sequence[str] = (),
        top_k: int,
        min_score: float,
        max_units_per_record: int,
    ) -> tuple[VectorHit, ...]:
        if not 1 <= top_k <= 20 or not 1 <= max_units_per_record <= 20:
            raise ValueError("vector retrieval bounds are invalid")
        if not 0 < min_score <= 1:
            raise ValueError("min_score must be in (0, 1]")
        vector = _vector_literal(validate_vector(query_vector))
        allowed_clause = ""
        parameters: list[object] = [
            vector,
            vector,
            domain,
            embedding_version,
            embedding_model,
        ]
        if allowed_record_ids:
            allowed_clause = " AND s.record_id = ANY(%s)"
            parameters.append(list(allowed_record_ids))
        parameters.extend([vector, min_score, max_units_per_record, top_k])
        source_select = ", ".join(
            f"s.{column}" for column in self._SOURCE_COLUMNS
        )
        bounded_select = ", ".join(
            f"b.{column}" for column in self._SOURCE_COLUMNS
        )
        query = f"""
            WITH scored AS (
                SELECT {source_select}, e.retrieval_unit_id,
                       1 - (e.embedding <=> %s::vector) AS similarity,
                       row_number() OVER (
                           PARTITION BY s.record_id
                           ORDER BY e.embedding <=> %s::vector,
                                    e.retrieval_unit_id
                       ) AS unit_rank
                FROM source_record_embeddings e
                JOIN source_records s ON s.record_id = e.source_record_id
                WHERE s.domain = %s
                  AND s.index_status = 'INDEXED'
                  AND s.embedding_version = %s
                  AND e.source_content_hash = s.content_hash
                  AND e.embedding_model = %s
                  AND e.embedding_version = s.embedding_version
                  {allowed_clause}
                  AND 1 - (e.embedding <=> %s::vector) >= %s
            ),
            bounded_units AS (
                SELECT * FROM scored WHERE unit_rank <= %s
            ),
            top_sources AS (
                SELECT record_id, max(similarity) AS best_similarity
                FROM bounded_units
                GROUP BY record_id
                ORDER BY best_similarity DESC, record_id
                LIMIT %s
            )
            SELECT {bounded_select}, b.retrieval_unit_id, b.similarity
            FROM bounded_units b
            JOIN top_sources t ON t.record_id = b.record_id
            ORDER BY t.best_similarity DESC, b.record_id,
                     b.similarity DESC, b.retrieval_unit_id
        """
        try:
            with self._connection_factory() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, tuple(parameters))
                    rows = cursor.fetchall()
        except Exception:
            raise RepositoryUnavailableError() from None

        grouped: dict[str, list[tuple[float, str, CommonRecord]]] = defaultdict(list)
        for raw in rows:
            values = dict(raw)
            score = float(values.pop("similarity"))
            unit_id = str(values.pop("retrieval_unit_id"))
            if math.isfinite(score) and score >= min_score:
                record = CommonRecord.model_validate(values)
                grouped[record.record_id].append((score, unit_id, record))
        hits = []
        for unit_hits in grouped.values():
            ranked = sorted(unit_hits, key=lambda item: (-item[0], item[1]))
            hits.append(
                VectorHit(
                    ranked[0][2],
                    ranked[0][0],
                    tuple(item[1] for item in ranked[:max_units_per_record]),
                )
            )
        return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.record.record_id))[:top_k])


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _vector_literal(vector: Sequence[float]) -> str:
    values = validate_vector(vector)
    return "[" + ",".join(format(value, ".17g") for value in values) + "]"
