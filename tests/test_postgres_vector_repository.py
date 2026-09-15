"""SQL-boundary tests for shared pgvector persistence and source rehydration."""

from __future__ import annotations

from pathlib import Path

from askanu_rag.retrieval import load_course_program_records
from askanu_rag.retrieval.vector import PostgresVectorRepository

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
