"""SQL-boundary tests for shared pgvector persistence and source rehydration."""

from __future__ import annotations

from pathlib import Path

import pytest

from askanu_rag.database import RepositoryUnavailableError
from askanu_rag.retrieval import load_course_program_records
from askanu_rag.retrieval.vector import (
    PersistedEmbedding,
    PostgresVectorRepository,
)

FIXTURE = Path(__file__).parents[1] / "fixtures/day5_course_program_records.json"


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, parameters=()):
        self.calls.append((query, parameters))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


class StatefulSuccessCursor(FakeCursor):
    def __init__(self, state):
        super().__init__([])
        self.state = state
        self.pending_rows = []
        self.committed_rows = []

    def execute(self, query, parameters=()):
        self.calls.append((query, parameters))
        if "INSERT INTO source_record_embeddings" in query:
            self.pending_rows.append(parameters)
            self.rowcount = 1
            return
        if "UPDATE source_records" in query and "embedding_version = %s" in query:
            target, record_id, content_hash, index_status, embedding_version = (
                parameters
            )
            matches = (
                self.state["record_id"] == record_id
                and self.state["content_hash"] == content_hash
                and self.state["index_status"] == index_status
                and self.state["embedding_version"] == embedding_version
            )
            self.rowcount = int(matches)
            if matches:
                self.state.update(
                    index_status="INDEXED", embedding_version=target
                )


class TransactionalFakeConnection(FakeConnection):
    def __enter__(self):
        self._original_state = dict(self._cursor.state)
        return self

    def __exit__(self, exc_type, *_args):
        if exc_type is not None:
            self._cursor.state.clear()
            self._cursor.state.update(self._original_state)
            self._cursor.pending_rows.clear()
        else:
            self._cursor.committed_rows.extend(self._cursor.pending_rows)
            self._cursor.pending_rows.clear()
        return False


def test_postgres_vector_search_hard_filters_and_rehydrates_source_record():
    record = load_course_program_records(FIXTURE)[0].model_copy(
        update={
            "status": "UNCHANGED",
            "index_status": "INDEXED",
            "embedding_version": "v1",
        }
    )
    row = record.model_dump(mode="python") | {
        "retrieval_unit_id": "chunk-0001",
        "similarity": 0.91,
    }
    cursor = FakeCursor([row])
    repository = PostgresVectorRepository(lambda: FakeConnection(cursor))

    hits = repository.search(
        (1.0, 0.0),
        domain="courses",
        embedding_model="model-a",
        embedding_version="v1",
        allowed_record_ids=[record.record_id],
        top_k=2,
        min_score=0.5,
        max_units_per_record=3,
    )

    assert len(hits) == 1
    assert hits[0].record.model_dump(mode="json") == record.model_dump(mode="json")
    assert hits[0].retrieval_unit_ids == ("chunk-0001",)
    query, parameters = cursor.calls[0]
    assert "JOIN source_records" in query
    assert "s.index_status = 'INDEXED'" in query
    assert "e.source_content_hash = s.content_hash" in query
    assert "s.record_id = ANY(%s)" in query
    assert "row_number() OVER" in query
    assert "unit_rank <= %s" in query
    assert parameters == (
        "[1,0]",
        "[1,0]",
        "courses",
        "v1",
        "model-a",
        [record.record_id],
        "[1,0]",
        0.5,
        3,
        2,
    )


def test_postgres_existing_unit_lookup_is_model_and_version_scoped():
    cursor = FakeCursor(
        [{"retrieval_unit_id": "whole", "retrieval_content_hash": "a" * 64}]
    )
    repository = PostgresVectorRepository(lambda: FakeConnection(cursor))

    found = repository.existing_units(
        "courses:course:X_2026", "c" * 64, "model-a", "v2"
    )

    assert found == {"whole": frozenset({"a" * 64})}
    assert cursor.calls[0][1] == (
        "courses:course:X_2026",
        "model-a",
        "v2",
        "c" * 64,
    )


def test_postgres_existing_unit_lookup_preserves_all_historical_hashes():
    cursor = FakeCursor(
        [
            {"retrieval_unit_id": "whole", "retrieval_content_hash": "a" * 64},
            {"retrieval_unit_id": "whole", "retrieval_content_hash": "b" * 64},
        ]
    )
    repository = PostgresVectorRepository(lambda: FakeConnection(cursor))

    assert repository.existing_units(
        "record", "c" * 64, "model", "version"
    ) == {
        "whole": frozenset({"a" * 64, "b" * 64})
    }


def test_postgres_failure_preserves_valid_last_known_good_without_write():
    record = load_course_program_records(FIXTURE)[0].model_copy(
        update={
            "status": "UNCHANGED",
            "index_status": "INDEXED",
            "embedding_version": "model-v1+policy-v1",
        }
    )
    repository = PostgresVectorRepository(
        lambda: (_ for _ in ()).throw(AssertionError("must not write LKG state"))
    )

    repository.persist_failure(record)


def test_postgres_failure_uses_index_state_compare_and_set():
    record = load_course_program_records(FIXTURE)[0].model_copy(
        update={"status": "UNCHANGED", "index_status": "PENDING"}
    )
    cursor = FakeCursor([])
    repository = PostgresVectorRepository(lambda: FakeConnection(cursor))

    repository.persist_failure(record)

    query, parameters = cursor.calls[0]
    assert "SET index_status = 'FAILED'" in query
    assert "content_hash = %s" in query
    assert "index_status = %s" in query
    assert "embedding_version IS NOT DISTINCT FROM %s" in query
    assert parameters == (
        record.record_id,
        record.content_hash,
        "PENDING",
        None,
    )


def persisted_row(record, version="v2"):
    return PersistedEmbedding(
        record.record_id,
        "whole",
        record.content_hash,
        "a" * 64,
        "model",
        version,
        (1.0, 0.0),
    )


@pytest.mark.parametrize(
    ("index_status", "embedding_version"),
    [("PENDING", None), ("INDEXED", "v1")],
)
def test_postgres_success_cas_commits_matching_start_state(
    index_status, embedding_version
):
    snapshot = load_course_program_records(FIXTURE)[0].model_copy(
        update={
            "status": "CHANGED" if index_status == "PENDING" else "UNCHANGED",
            "index_status": index_status,
            "embedding_version": embedding_version,
        }
    )
    state = {
        "record_id": snapshot.record_id,
        "content_hash": snapshot.content_hash,
        "index_status": index_status,
        "embedding_version": embedding_version,
    }
    cursor = StatefulSuccessCursor(state)
    repository = PostgresVectorRepository(
        lambda: TransactionalFakeConnection(cursor)
    )

    repository.persist_success(snapshot, (persisted_row(snapshot),), "v2")

    assert (state["index_status"], state["embedding_version"]) == (
        "INDEXED",
        "v2",
    )
    assert len(cursor.committed_rows) == 1
    update_query, update_parameters = cursor.calls[-1]
    assert "content_hash = %s" in update_query
    assert "index_status = %s" in update_query
    assert "embedding_version IS NOT DISTINCT FROM %s" in update_query
    assert update_parameters == (
        "v2",
        snapshot.record_id,
        snapshot.content_hash,
        index_status,
        embedding_version,
    )


def test_postgres_late_v2_success_cannot_overwrite_committed_v3():
    snapshot = load_course_program_records(FIXTURE)[0].model_copy(
        update={
            "status": "UNCHANGED",
            "index_status": "INDEXED",
            "embedding_version": "v1",
        }
    )
    state = {
        "record_id": snapshot.record_id,
        "content_hash": snapshot.content_hash,
        "index_status": "INDEXED",
        "embedding_version": "v3",
    }
    cursor = StatefulSuccessCursor(state)
    repository = PostgresVectorRepository(
        lambda: TransactionalFakeConnection(cursor)
    )

    with pytest.raises(RepositoryUnavailableError):
        repository.persist_success(snapshot, (persisted_row(snapshot),), "v2")

    assert (state["index_status"], state["embedding_version"]) == (
        "INDEXED",
        "v3",
    )
    assert cursor.committed_rows == []
    assert cursor.pending_rows == []
    assert cursor.calls[-1][1] == (
        "v2",
        snapshot.record_id,
        snapshot.content_hash,
        "INDEXED",
        "v1",
    )
