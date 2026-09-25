"""V6 retrieval-unit, embedding, vector and shared-merge evaluation."""

from __future__ import annotations

from pathlib import Path
import hashlib

import pytest

from askanu_rag.hybrid_queries import HybridQueryService
from askanu_rag.query_planner import plan_query
from askanu_rag.retrieval import CourseProgramRepository
from askanu_rag.retrieval import load_course_program_records
from askanu_rag.retrieval.embeddings import DeterministicFakeEmbedder
from askanu_rag.retrieval.hybrid import CandidateTier, SharedHybridRetriever
from askanu_rag.retrieval.units import RetrievalUnitBuilder
from askanu_rag.retrieval.semantic import SemanticHit
from askanu_rag.retrieval.vector import (
    EmbeddingIndexService,
    InMemoryVectorRepository,
    PersistedEmbedding,
    PersistedSemanticRetriever,
    VectorHit,
    effective_embedding_version,
)

FIXTURE = Path(__file__).parents[1] / "fixtures/day5_course_program_records.json"


def records():
    return load_course_program_records(FIXTURE)


def test_short_record_is_one_stable_whole_retrieval_unit():
    record = records()[0]
    builder = RetrievalUnitBuilder(max_chars=2_000)

    first = builder.build(record)
    second = builder.build(record)

    assert first == second
    assert len(first) == 1
    assert first[0].retrieval_unit_id == "whole"
    assert first[0].source_record_id == record.record_id
    assert first[0].source_content_hash == record.content_hash
    assert len(first[0].retrieval_content_hash) == 64


def test_long_sectioned_record_chunks_deterministically_with_bounded_size():
    record = records()[0].model_copy(
        update={"content": "\n\n".join(["alpha " * 80, "beta " * 80, "gamma " * 80])}
    )
    builder = RetrievalUnitBuilder(max_chars=300, max_units=20)

    units = builder.build(record)

    assert len(units) > 1
    assert [unit.retrieval_unit_id for unit in units] == [
        f"chunk-{index:04d}" for index in range(1, len(units) + 1)
    ]
    assert all(len(unit.content) <= 300 for unit in units)
    assert units == builder.build(record)


def test_indexing_is_hash_and_version_aware_and_avoids_repeat_embedding():
    source = records()[0]
    repository = InMemoryVectorRepository([source])
    provider = DeterministicFakeEmbedder(version="test-v1")
    service = EmbeddingIndexService(repository, provider)

    assert service.index_record(source) == 1
    assert provider.document_calls == 1
    indexed = repository.records[source.record_id].model_copy(
        update={"status": "UNCHANGED"}
    )
    repository.records[source.record_id] = indexed

    assert service.index_record(indexed) == 0
    assert provider.document_calls == 1

    next_provider = DeterministicFakeEmbedder(version="test-v2")
    next_service = EmbeddingIndexService(repository, next_provider)
    assert next_service.index_record(indexed, explicit_retry=True) == 1
    assert next_provider.document_calls == 1
    assert repository.records[source.record_id].embedding_version == next_service.target_version


def test_embedding_failure_preserves_last_known_good_rows_and_version():
    source = records()[0]
    repository = InMemoryVectorRepository([source])
    first = DeterministicFakeEmbedder(version="test-v1")
    EmbeddingIndexService(repository, first).index_record(source)
    previous_keys = set(repository.rows)
    indexed = repository.records[source.record_id].model_copy(
        update={"status": "UNCHANGED"}
    )
    repository.records[source.record_id] = indexed

    class FailingProvider(DeterministicFakeEmbedder):
        def embed_documents(self, texts):
            raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        failed_service = EmbeddingIndexService(
            repository, FailingProvider(version="test-v2")
        )
        failed_service.index_record(indexed, explicit_retry=True)

    failed = repository.records[source.record_id]
    assert failed.index_status == "INDEXED"
    assert failed.embedding_version == EmbeddingIndexService(repository, first).target_version
    assert set(repository.rows) == previous_keys
    old_row = next(iter(repository.rows.values()))
    assert repository.search(
        old_row.embedding,
        domain="courses",
        embedding_model=old_row.embedding_model,
        embedding_version=old_row.embedding_version,
        top_k=1,
        min_score=0.99,
        max_units_per_record=1,
    )[0].record.record_id == source.record_id
    assert repository.search(
        old_row.embedding,
        domain="courses",
        embedding_model=old_row.embedding_model,
        embedding_version=failed_service.target_version,
        top_k=1,
        min_score=0.99,
        max_units_per_record=1,
    ) == ()


def test_content_change_failure_keeps_rows_but_cannot_masquerade_as_current():
    source = records()[0]
    repository = InMemoryVectorRepository([source])
    provider = DeterministicFakeEmbedder(version="test-v1")
    service = EmbeddingIndexService(repository, provider)
    service.index_record(source)
    previous_rows = set(repository.rows)
    changed_content = source.content + "\nNew source-backed detail."
    changed = source.model_copy(
        update={
            "status": "CHANGED",
            "content": changed_content,
            "content_hash": hashlib.sha256(changed_content.encode()).hexdigest(),
            "index_status": "PENDING",
            "embedding_version": None,
        }
    )
    repository.records[source.record_id] = changed

    class FailingProvider(DeterministicFakeEmbedder):
        def embed_documents(self, texts):
            raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        EmbeddingIndexService(
            repository, FailingProvider(version="test-v1")
        ).index_record(changed)

    failed = repository.records[source.record_id]
    assert (failed.index_status, failed.embedding_version) == ("FAILED", None)
    assert set(repository.rows) == previous_rows
    old_row = next(iter(repository.rows.values()))
    assert repository.search(
        old_row.embedding,
        domain="courses",
        embedding_model=old_row.embedding_model,
        embedding_version=old_row.embedding_version,
        top_k=1,
        min_score=0.99,
        max_units_per_record=1,
    ) == ()


def test_late_failure_cannot_overwrite_concurrent_index_success():
    source = records()[0]
    repository = InMemoryVectorRepository([source])
    pending = source.model_copy(
        update={"status": "UNCHANGED", "index_status": "PENDING"}
    )
    repository.records[source.record_id] = pending.model_copy(
        update={"index_status": "INDEXED", "embedding_version": "new-version"}
    )

    repository.persist_failure(pending)

    current = repository.records[source.record_id]
    assert (current.index_status, current.embedding_version) == (
        "INDEXED",
        "new-version",
    )


def test_late_success_cannot_overwrite_newer_committed_version_in_memory():
    source = records()[0]
    snapshot = source.model_copy(
        update={
            "status": "UNCHANGED",
            "index_status": "INDEXED",
            "embedding_version": "v1",
        }
    )
    repository = InMemoryVectorRepository([snapshot])
    repository.records[source.record_id] = snapshot.model_copy(
        update={"embedding_version": "v3"}
    )
    late_v2 = PersistedEmbedding(
        source.record_id,
        "whole",
        source.content_hash,
        "a" * 64,
        "model",
        "v2",
        (1.0, 0.0),
    )

    with pytest.raises(
        ValueError, match="source/index state changed before embedding commit"
    ):
        repository.persist_success(snapshot, (late_v2,), "v2")

    current = repository.records[source.record_id]
    assert (current.index_status, current.embedding_version) == ("INDEXED", "v3")
    assert repository.rows == {}


def test_persisted_semantic_search_dedupes_units_and_rejects_stale_or_weak_rows():
    first, second = records()[:2]
    version = effective_embedding_version(
        "v1", RetrievalUnitBuilder().policy_version
    )
    first = first.model_copy(
        update={"status": "UNCHANGED", "index_status": "INDEXED", "embedding_version": version}
    )
    second = second.model_copy(
        update={"status": "UNCHANGED", "index_status": "INDEXED", "embedding_version": version}
    )
    repository = InMemoryVectorRepository([first, second])
    repository.rows[(first.record_id, "chunk-0001", "a" * 64, "fixed", version)] = PersistedEmbedding(
        first.record_id, "chunk-0001", first.content_hash, "a" * 64, "fixed", version, (1.0, 0.0)
    )
    repository.rows[(first.record_id, "chunk-0002", "b" * 64, "fixed", version)] = PersistedEmbedding(
        first.record_id, "chunk-0002", first.content_hash, "b" * 64, "fixed", version, (0.9, 0.1)
    )
    repository.rows[(second.record_id, "whole", "c" * 64, "fixed", version)] = PersistedEmbedding(
        second.record_id, "whole", "f" * 64, "c" * 64, "fixed", version, (1.0, 0.0)
    )

    class FixedProvider:
        model = "fixed"
        version = "v1"

        def embed_query(self, _text):
            return (1.0, 0.0)

        def embed_documents(self, _texts):
            raise AssertionError("query path must not embed documents")

    hits = PersistedSemanticRetriever(
        repository,
        FixedProvider(),
        top_k=5,
        min_score=0.8,
        max_units_per_record=2,
        dimension=2,
    ).search("functional programming", domain="courses")

    assert [hit.record.record_id for hit in hits] == [first.record_id]
    assert hits[0].retrieval_unit_ids == ("chunk-0001", "chunk-0002")


def test_missing_observation_preserves_last_known_good_vector_evidence():
    record = records()[0].model_copy(
        update={"status": "MISSING", "index_status": "INDEXED", "embedding_version": "v1"}
    )
    repository = InMemoryVectorRepository([record])
    repository.rows[(record.record_id, "whole", "a" * 64, "fixed", "v1")] = PersistedEmbedding(
        record.record_id,
        "whole",
        record.content_hash,
        "a" * 64,
        "fixed",
        "v1",
        (1.0, 0.0),
    )

    hits = repository.search(
        (1.0, 0.0),
        domain="courses",
        embedding_model="fixed",
        embedding_version="v1",
        top_k=3,
        min_score=0.5,
        max_units_per_record=1,
    )

    assert [hit.record.record_id for hit in hits] == [record.record_id]


def test_vector_threshold_rejects_the_nearest_weak_match():
    record = records()[0].model_copy(
        update={"status": "UNCHANGED", "index_status": "INDEXED", "embedding_version": "v1"}
    )
    repository = InMemoryVectorRepository([record])
    repository.rows[(record.record_id, "whole", "a" * 64, "fixed", "v1")] = PersistedEmbedding(
        record.record_id,
        "whole",
        record.content_hash,
        "a" * 64,
        "fixed",
        "v1",
        (0.0, 1.0),
    )

    assert repository.search(
        (1.0, 0.0),
        domain="courses",
        embedding_model="fixed",
        embedding_version="v1",
        top_k=3,
        min_score=0.2,
        max_units_per_record=1,
    ) == ()


def test_shared_merge_exact_wins_dedupes_and_has_stable_bounded_order():
    first, second, third = records()[:3]
    merged = SharedHybridRetriever(max_candidates=2).merge(
        exact=[second],
        structured=[first, second],
        sparse=[(third, 0.9), (first, 0.7)],
        semantic=[(third, 0.8, ("whole",)), (first, 0.95, ("whole",))],
    )

    assert [candidate.record.record_id for candidate in merged] == [
        second.record_id,
        first.record_id,
    ]
    assert [candidate.tier for candidate in merged] == [
        CandidateTier.EXACT,
        CandidateTier.STRUCTURED,
    ]


def test_historical_and_current_unit_hashes_do_not_force_repeat_embedding():
    source = records()[0]
    repository = InMemoryVectorRepository([source])
    provider = DeterministicFakeEmbedder(version="model-v1")
    service = EmbeddingIndexService(repository, provider)
    unit = service.unit_builder.build(source)[0]
    for retrieval_hash, source_hash in (
        ("0" * 64, "f" * 64),
        (unit.retrieval_content_hash, source.content_hash),
    ):
        row = PersistedEmbedding(
            source.record_id,
            unit.retrieval_unit_id,
            source_hash,
            retrieval_hash,
            provider.model,
            service.target_version,
            (1.0,) * provider.dimension,
        )
        repository.rows[(source.record_id, unit.retrieval_unit_id, retrieval_hash, provider.model, service.target_version)] = row

    assert service.index_record(source) == 0
    assert provider.document_calls == 0

    changed_content = source.content + "\nA new source-backed section."
    changed = source.model_copy(
        update={
            "content": changed_content,
            "content_hash": hashlib.sha256(changed_content.encode()).hexdigest(),
        }
    )
    repository.records[source.record_id] = changed
    assert service.index_record(changed) == 1
    assert provider.document_calls == 1


def test_title_only_change_cannot_change_retrieval_units_or_freshness_hash():
    source = records()[0]
    renamed = source.model_copy(update={"title": "A display-only renamed title"})
    builder = RetrievalUnitBuilder()

    assert builder.build(renamed) == builder.build(source)
    assert builder.build(source)[0].content == source.content


def test_retrieval_policy_change_requires_explicit_version_reindex():
    source = records()[0]
    repository = InMemoryVectorRepository([source])
    provider = DeterministicFakeEmbedder(version="model-v1")
    first = EmbeddingIndexService(
        repository,
        provider,
        unit_builder=RetrievalUnitBuilder(policy_version="policy-a"),
    )
    assert first.index_record(source) == 1
    indexed = repository.records[source.record_id].model_copy(
        update={"status": "UNCHANGED"}
    )
    repository.records[source.record_id] = indexed

    second_provider = DeterministicFakeEmbedder(version="model-v1")
    second = EmbeddingIndexService(
        repository,
        second_provider,
        unit_builder=RetrievalUnitBuilder(policy_version="policy-b"),
    )
    assert second.target_version != first.target_version
    assert second.index_record(indexed, explicit_retry=True) == 1
    assert repository.records[source.record_id].embedding_version == second.target_version


def test_discovery_rank_fusion_never_compares_sparse_and_dense_raw_scores():
    first, second, third = records()[:3]
    merged = SharedHybridRetriever().merge(
        sparse=[(first, 0.01), (third, 0.99)],
        semantic=[(second, 1.0, ("whole",)), (third, 0.01, ("whole",))],
    )

    assert merged[0].record == third  # dual signal wins
    assert [candidate.record.record_id for candidate in merged[1:]] == sorted(
        (first.record_id, second.record_id)
    )


def test_discovery_rank_fusion_ties_are_stable_by_record_id():
    first, second = records()[:2]
    merged = SharedHybridRetriever().merge(
        sparse=[(second, 0.9)],
        semantic=[(first, 0.1, ("whole",))],
    )
    assert [candidate.record.record_id for candidate in merged] == sorted(
        (first.record_id, second.record_id)
    )


def test_courses_preserve_sparse_signal_and_merge_dense_candidates_by_record():
    catalogue = records()
    comp1110, comp1100 = catalogue[:2]

    class FixedSparse:
        uses_persistent_index = False

        def search(self, _query, _candidates, *, top_k, min_score):
            assert top_k == 5
            assert min_score == 0.2
            return (SemanticHit(comp1110.record_id, 0.8),)

    class FixedVector:
        def search(self, _query, *, domain, allowed_records, **_kwargs):
            assert domain == "courses"
            assert comp1110 in allowed_records
            return (
                VectorHit(comp1110, 0.95, ("chunk-0001",)),
                VectorHit(comp1100, 0.85, ("whole",)),
            )

    repository = CourseProgramRepository(catalogue)
    service = HybridQueryService(
        repository,
        semantic_retriever=FixedSparse(),
        vector_retriever=FixedVector(),
    )
    plan = plan_query(
        "What courses in 2026 involve functional programming?", repository
    )

    chosen = service.retrieve(plan)

    assert [record.record_id for record in chosen] == [
        comp1110.record_id,
        comp1100.record_id,
    ]


def test_course_after_exact_code_applies_stored_prerequisite_before_semantic():
    catalogue = list(records())
    candidate = catalogue[3].model_copy(
        update={
            "title": "Cybersecurity Systems",
            "content": "Network defence and cybersecurity infrastructure.",
            "metadata_json": catalogue[3].metadata_json.model_copy(
                update={"prerequisites": "COMP1110"}
            ),
        }
    )
    catalogue[3] = candidate

    class FixedSparse:
        uses_persistent_index = False

        def search(self, _query, candidates, **_kwargs):
            assert candidates == (candidate,)
            return (SemanticHit(candidate.record_id, 0.8),)

    class FixedVector:
        def search(self, _query, *, allowed_records, **_kwargs):
            assert allowed_records == (candidate,)
            return (VectorHit(candidate, 0.9, ("whole",)),)

    repository = CourseProgramRepository(catalogue)
    service = HybridQueryService(
        repository,
        semantic_retriever=FixedSparse(),
        vector_retriever=FixedVector(),
    )
    plan = plan_query(
        "I want a course about cybersecurity after COMP1110", repository
    )

    assert plan.route == "hybrid"
    assert service.retrieve(plan) == (candidate,)


def test_course_after_code_abstains_without_stored_prerequisite_relationship():
    catalogue = records()

    class MustNotRun:
        uses_persistent_index = False

        def search(self, *_args, **_kwargs):
            raise AssertionError("semantic ranking must not relax the hard constraint")

    repository = CourseProgramRepository(catalogue)
    service = HybridQueryService(
        repository,
        semantic_retriever=MustNotRun(),
        vector_retriever=MustNotRun(),
    )
    plan = plan_query(
        "I want a course about cybersecurity after COMP1110", repository
    )

    assert service.retrieve(plan) == ()


def test_dense_hit_identity_is_rehydrated_and_cannot_supply_forged_evidence():
    catalogue = records()
    original = catalogue[0]
    forged = original.model_copy(
        update={"title": "Forged title", "content": "Forged vector payload"}
    )

    class EmptySparse:
        uses_persistent_index = False

        def search(self, *_args, **_kwargs):
            return ()

    class ForgedVector:
        def search(self, *_args, **_kwargs):
            return (VectorHit(forged, 0.99, ("whole",)),)

    repository = CourseProgramRepository(catalogue)
    service = HybridQueryService(
        repository,
        semantic_retriever=EmptySparse(),
        vector_retriever=ForgedVector(),
    )
    plan = plan_query(
        "What courses in 2026 involve functional programming?", repository
    )

    assert service.retrieve(plan) == (original,)
