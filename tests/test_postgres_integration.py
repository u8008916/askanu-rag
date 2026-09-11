"""Opt-in disposable local PostgreSQL smoke; never accepts a cloud database."""

import logging
import os
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
from pydantic import SecretStr

from askanu_rag.config import Settings
from askanu_rag.database import DatabaseConnectionConfig
from askanu_rag.main import create_app
from askanu_rag.retrieval import PostgresCourseProgramRepository
from test_postgres_repository import (
    CapturingSynthesisClient,
    ask_payload,
    make_record,
)

TEST_DATABASE_URL = os.environ.get("ASKANU_TEST_DATABASE_URL")


def _local_test_url() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip("ASKANU_TEST_DATABASE_URL is not configured")
    values = conninfo_to_dict(TEST_DATABASE_URL)
    if values.get("host") not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("Integration database must be local")
    if not values.get("dbname", "").endswith("_test"):
        pytest.fail("Integration database name must end with _test")
    return TEST_DATABASE_URL


def _insert_record(connection, record, *, ignore_conflict: bool = False) -> int:
    values = record.model_dump(mode="python")
    values["canonical_url"] = str(record.canonical_url)
    values["metadata_json"] = Jsonb(
        record.metadata_json.model_dump(mode="python")
    )
    columns = (
        "record_id", "source_id", "entity_id", "domain", "title", "content",
        "canonical_url", "status", "effective_from", "effective_to",
        "collected_at", "last_seen_at", "content_hash", "embedding_version",
        "index_status", "metadata_json",
    )
    placeholders = ", ".join(["%s"] * len(columns))
    conflict_clause = " ON CONFLICT DO NOTHING" if ignore_conflict else ""
    cursor = connection.execute(
        f"INSERT INTO course_program_records ({', '.join(columns)}) "
        f"VALUES ({placeholders}){conflict_clause}",
        tuple(values[column] for column in columns),
    )
    return cursor.rowcount


def test_real_local_migration_repository_and_api_path(caplog):
    database_url = _local_test_url()
    config = DatabaseConnectionConfig.from_settings(
        Settings(database_url=SecretStr(database_url))
    )
    record_2025 = make_record(year="2025")
    record_2026 = make_record(year="2026")
    started_at = datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)

    with psycopg.connect(database_url) as connection:
        connection.execute(
            "TRUNCATE TABLE course_program_records, ingestion_runs"
        )
        connection.execute(
            """
            INSERT INTO ingestion_runs (
                run_id, source_id, started_at, completed_at, records_seen,
                records_added, records_changed, records_unchanged,
                records_missing, status, error
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "run:local-day7-contract",
                "courses_programs_and_courses",
                started_at,
                started_at + timedelta(seconds=12),
                3,
                1,
                1,
                1,
                0,
                "SUCCESS",
                None,
            ),
        )
        _insert_record(connection, record_2025)
        _insert_record(connection, record_2026)

    with psycopg.connect(database_url) as connection:
        run = connection.execute(
            """
            SELECT source_id, records_seen, records_added, records_changed,
                   records_unchanged, records_missing, status, error
            FROM ingestion_runs
            WHERE run_id = %s
            """,
            ("run:local-day7-contract",),
        ).fetchone()
    assert run == (
        "courses_programs_and_courses", 3, 1, 1, 1, 0, "SUCCESS", None
    )

    with psycopg.connect(database_url) as connection:
        assert _insert_record(
            connection, record_2026, ignore_conflict=True
        ) == 0

    repository = PostgresCourseProgramRepository(config.connect)
    assert len(repository.all_records()) == 2
    exact = repository.find_course_by_code("comp 1110", "2026")
    assert exact is not None and not isinstance(exact, tuple)
    assert exact.record_id == "courses:course:COMP1110_2026"
    assert exact.metadata_json.academic_year == "2026"
    assert exact.metadata_json.prerequisites == (
        "COMP1100 OR COMP1130 OR COMP1730"
    )
    assert str(exact.canonical_url) == (
        "https://programsandcourses.anu.edu.au/2026/course/comp1110"
    )
    assert exact.content_hash == record_2026.content_hash
    assert exact.metadata_json.assumed_knowledge is None
    assert repository.find_course_by_code("COMP1110", "2030") is None

    ambiguous = repository.find_course_by_code("COMP1110")
    assert isinstance(ambiguous, tuple)
    assert [record.metadata_json.academic_year for record in ambiguous] == [
        "2025", "2026"
    ]

    synthesis = CapturingSynthesisClient()
    caplog.set_level(logging.INFO, logger="uvicorn.error.askanu_rag.requests")
    with TestClient(create_app(repository, synthesis)) as client:
        response = client.post(
            "/api/v1/ask",
            json=ask_payload("What are the prerequisites for COMP1110 in 2026?"),
            headers={"X-Request-Id": "app-day7-postgres-smoke"},
        )
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["request_id"].startswith("req_")
    assert body["request_id"] != "app-day7-postgres-smoke"
    assert body["sources"][0]["url"] == str(record_2026.canonical_url)
    assert body["answer"].endswith("COMP1100 OR COMP1130 OR COMP1730")
    assert f"request_id={body['request_id']}" in caplog.text
    assert "upstream_request_id=app-day7-postgres-smoke" in caplog.text
    assert "http_status=200" in caplog.text
    assert "response_status=ok" in caplog.text
    assert "latency_ms=" in caplog.text
