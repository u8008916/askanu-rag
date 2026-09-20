"""Opt-in disposable local PostgreSQL smoke; never accepts a cloud database."""

import copy
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
from pydantic import SecretStr
from sqlalchemy.exc import DBAPIError

from askanu_rag.config import Settings
from askanu_rag.database import DatabaseConnectionConfig
from askanu_rag.main import create_app
from askanu_rag.retrieval import PostgresCourseProgramRepository, load_common_records
from test_postgres_repository import (
    CapturingSynthesisClient,
    ask_payload,
    make_record,
    make_scholarship,
)
from test_jobs import make_job
from test_courses_family import make_subplan
from test_day12_contracts import accommodation_payload, support_payload
from askanu_rag.models import AccommodationRecord, EventRecord, SupportRecord

TEST_DATABASE_URL = os.environ.get("ASKANU_TEST_DATABASE_URL")
ROOT = Path(__file__).parents[1]
EVENT_FIXTURE = ROOT / "fixtures" / "day15_event_records.json"
SCHOLARSHIP_URL_PREFIX = (
    "https://study.anu.edu.au/scholarships/find-scholarship/"
)
COMPATIBILITY_VIEW_COLUMNS = (
    "record_id", "source_id", "entity_id", "domain", "title", "content",
    "canonical_url", "status", "effective_from", "effective_to",
    "collected_at", "last_seen_at", "content_hash", "embedding_version",
    "index_status", "metadata_json",
)


def _local_test_url() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip("ASKANU_TEST_DATABASE_URL is not configured")
    values = conninfo_to_dict(TEST_DATABASE_URL)
    if values.get("host") not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("Integration database must be local")
    if not values.get("dbname", "").endswith("_test"):
        pytest.fail("Integration database name must end with _test")
    return TEST_DATABASE_URL


def _record_values(record) -> dict[str, object]:
    values = record.model_dump(mode="python")
    values["canonical_url"] = str(record.canonical_url)
    values["metadata_json"] = Jsonb(
        record.metadata_json.model_dump(mode="python")
    )
    return values


def _insert_record_values(
    connection, values: dict[str, object], *, ignore_conflict: bool = False
) -> int:
    columns = (
        "record_id", "source_id", "entity_id", "domain", "title", "content",
        "canonical_url", "status", "effective_from", "effective_to",
        "collected_at", "last_seen_at", "content_hash", "embedding_version",
        "index_status", "metadata_json",
    )
    placeholders = ", ".join(["%s"] * len(columns))
    conflict_clause = " ON CONFLICT DO NOTHING" if ignore_conflict else ""
    cursor = connection.execute(
        f"INSERT INTO source_records ({', '.join(columns)}) "
        f"VALUES ({placeholders}){conflict_clause}",
        tuple(values[column] for column in columns),
    )
    return cursor.rowcount


def _insert_record(connection, record, *, ignore_conflict: bool = False) -> int:
    return _insert_record_values(
        connection,
        _record_values(record),
        ignore_conflict=ignore_conflict,
    )


def _provisional_accommodation_values(
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    values = _record_values(AccommodationRecord.model_validate(accommodation_payload()))
    values["record_id"] = "accommodation:accommodation:yukeembruk"
    values["metadata_json"] = Jsonb(
        metadata
        or {
            "entity_type": "accommodation",
            "source_authority": "official_anu",
            "accommodation_type": "Residence hall",
            "location": "Acton campus",
            "catering": "Self-catered",
            "audience": ["Students"],
            "room_types": ["Single room"],
            "advertised_rate": "$340 per week",
            "rate_inclusions": ["Utilities"],
            "rate_exclusions": ["Meals"],
            "facilities": ["Study room"],
            "application_information": "Apply online",
            "eligibility": None,
            "contract_term": "44 weeks",
            "contact": "Accommodation Services",
        }
    )
    return values


def _provisional_support_values(
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    values = _record_values(SupportRecord.model_validate(support_payload()))
    values["metadata_json"] = Jsonb(
        metadata
        or {
            "entity_type": "support_service",
            "source_authority": "approved_anusa",
            "categories": ["Academic"],
            "contact": "Student Assistance",
            "location": "Kambri",
            "hours": "Monday to Friday",
            "audience": ["Students"],
            "access_instructions": "Book an appointment",
            "cost": "Free",
        }
    )
    return values


def _support_values_with_nested_url(
    collection: str, url: str
) -> dict[str, object]:
    record = SupportRecord.model_validate(support_payload())
    values = _record_values(record)
    metadata = record.metadata_json.model_dump(mode="python")
    metadata[collection][0]["url"] = url
    values["metadata_json"] = Jsonb(metadata)
    return values


def _insert_is_accepted(database_url: str, values: dict[str, object]) -> bool:
    with psycopg.connect(database_url) as connection:
        try:
            _insert_record_values(connection, values)
        except psycopg.errors.CheckViolation:
            connection.rollback()
            return False
        connection.execute(
            "DELETE FROM source_records WHERE record_id = %s", (values["record_id"],)
        )
        return True


def _compatibility_snapshot(connection) -> tuple[object, ...]:
    source_count = connection.execute(
        "SELECT count(*) FROM source_records"
    ).fetchone()[0]
    persisted_records = tuple(
        connection.execute(
            """
            SELECT record_id, canonical_url, content_hash, collected_at,
                   last_seen_at, index_status, embedding_version
            FROM source_records
            ORDER BY record_id
            """
        ).fetchall()
    )
    source_columns = tuple(
        connection.execute(
            """
            SELECT column_name, data_type, udt_name, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'source_records'
            ORDER BY ordinal_position
            """
        ).fetchall()
    )
    source_constraints = tuple(
        connection.execute(
            """
            SELECT conname, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'public.source_records'::regclass
            ORDER BY conname
            """
        ).fetchall()
    )
    return source_count, persisted_records, source_columns, source_constraints


def _view_update_flags(connection) -> tuple[str, str]:
    return connection.execute(
        """
        SELECT is_updatable, is_insertable_into
        FROM information_schema.views
        WHERE table_schema = 'public'
          AND table_name = 'course_program_records'
        """
    ).fetchone()


def test_real_local_migration_repository_and_api_path(caplog):
    database_url = _local_test_url()
    config = DatabaseConnectionConfig.from_settings(
        Settings(database_url=SecretStr(database_url))
    )
    record_2025 = make_record(year="2025")
    record_2026 = make_record(year="2026")
    scholarship = make_scholarship()
    started_at = datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)

    with psycopg.connect(database_url) as connection:
        connection.execute(
            "TRUNCATE TABLE source_record_embeddings, source_records, ingestion_runs"
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
        _insert_record(connection, scholarship)
        assert connection.execute(
            "SELECT count(*) FROM course_program_records"
        ).fetchone()[0] == 2

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

    repository = PostgresCourseProgramRepository(config.connect)
    found = repository.find_scholarship_by_entity_id(scholarship.entity_id)
    assert found == scholarship
    assert repository.all_scholarships() == (scholarship,)


def test_compatibility_view_is_structurally_read_only_but_selectable():
    database_url = _local_test_url()

    with psycopg.connect(database_url) as connection:
        objects = dict(
            connection.execute(
                """
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'source_records', 'course_program_records', 'ingestion_runs'
                  )
                """
            ).fetchall()
        )
        columns = tuple(
            row[0]
            for row in connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'course_program_records'
                ORDER BY ordinal_position
                """
            ).fetchall()
        )
        assert objects == {
            "source_records": "BASE TABLE",
            "course_program_records": "VIEW",
            "ingestion_runs": "BASE TABLE",
        }
        assert columns == COMPATIBILITY_VIEW_COLUMNS
        assert _view_update_flags(connection) == ("NO", "NO")
        assert connection.execute(
            "SELECT count(*) FROM course_program_records"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM course_program_records WHERE domain <> 'courses'"
        ).fetchone()[0] == 0

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """
                INSERT INTO course_program_records
                SELECT * FROM course_program_records
                WHERE record_id = 'courses:course:COMP1110_2026'
                """
            )
        connection.rollback()

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                """
                UPDATE course_program_records
                SET title = title
                WHERE record_id = 'courses:course:COMP1110_2026'
                """
            )
        connection.rollback()


def test_subplans_persist_in_source_records_but_not_compatibility_view():
    database_url = _local_test_url()
    records = (
        make_subplan("major", "ACCT-MAJ"),
        make_subplan("minor", "AAGR-MIN", title="Agricultural Innovation Minor"),
        make_subplan(
            "specialisation", "MEAS-SPEC", title="Measurement Specialisation"
        ),
    )

    with psycopg.connect(database_url) as connection:
        for record in records:
            _insert_record(connection, record)
        stored_types = {
            row[0]
            for row in connection.execute(
                """
                SELECT metadata_json ->> 'entity_type'
                FROM source_records
                WHERE record_id = ANY(%s)
                """,
                ([record.record_id for record in records],),
            ).fetchall()
        }
        visible = connection.execute(
            """
            SELECT count(*) FROM course_program_records
            WHERE record_id = ANY(%s)
            """,
            ([record.record_id for record in records],),
        ).fetchone()[0]
        assert stored_types == {"major", "minor", "specialisation"}
        assert visible == 0
        connection.rollback()



def test_nullable_subplan_arrays_match_validated_model_contract():
    database_url = _local_test_url()
    record = make_subplan(
        "major",
        "NULL-MAJ",
        title="Nullable Arrays Major",
    )
    values = _record_values(record)
    metadata = record.metadata_json.model_dump(mode="python")
    metadata["learning_outcomes"] = None
    metadata["relevant_degrees"] = None
    values["metadata_json"] = Jsonb(metadata)

    with psycopg.connect(database_url) as connection:
        assert _insert_record_values(connection, values) == 1
        connection.rollback()


def test_view_migration_round_trip_preserves_schema_data_and_legacy_reads(monkeypatch):
    database_url = _local_test_url()
    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic_config = Config(ROOT / "alembic.ini")

    with psycopg.connect(database_url) as connection:
        head_before = _compatibility_snapshot(connection)
        assert _view_update_flags(connection) == ("NO", "NO")

    command.downgrade(alembic_config, "20260914_0003")
    try:
        with psycopg.connect(database_url) as connection:
            view_before = _compatibility_snapshot(connection)
            assert _view_update_flags(connection) == ("NO", "NO")

        command.downgrade(alembic_config, "20260913_0002")
        with psycopg.connect(database_url) as connection:
            assert _view_update_flags(connection) == ("YES", "YES")
            assert _compatibility_snapshot(connection) == view_before
            assert connection.execute(
                "SELECT count(*) FROM course_program_records WHERE domain <> 'courses'"
            ).fetchone()[0] == 0
    finally:
        command.upgrade(alembic_config, "head")

    with psycopg.connect(database_url) as connection:
        assert _view_update_flags(connection) == ("NO", "NO")
        assert _compatibility_snapshot(connection) == head_before


def test_real_downgrade_refuses_while_scholarship_rows_exist(monkeypatch):
    database_url = _local_test_url()
    monkeypatch.setenv("DATABASE_URL", database_url)

    with psycopg.connect(database_url) as connection:
        version_before = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        scholarship_count_before = connection.execute(
            "SELECT count(*) FROM source_records WHERE domain = 'scholarships'"
        ).fetchone()[0]

    assert scholarship_count_before == 1

    with pytest.raises(DBAPIError, match="Cannot downgrade while non-course"):
        command.downgrade(Config(ROOT / "alembic.ini"), "20260911_0001")

    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == version_before
        assert connection.execute(
            "SELECT count(*) FROM source_records WHERE domain = 'scholarships'"
        ).fetchone()[0] == scholarship_count_before


def test_real_jobs_repository_filter_order_limit_exact_lookup_and_endpoint():
    database_url = _local_test_url()
    config = DatabaseConnectionConfig.from_settings(
        Settings(database_url=SecretStr(database_url))
    )
    jobs = (
        make_job(
            "10",
            title="Same date ten",
            closing_date="2026-09-20",
            closing_at="2026-09-20T23:55:00+10:00",
        ),
        make_job("9", title="Same date nine", closing_date="2026-09-20"),
        make_job("2", title="Undated current", closing_date=None),
        make_job("7", title="Closing today", closing_date="2026-09-14"),
        make_job("3", title="Expired", closing_date="2026-09-13"),
        make_job("4", title="Closed", status="closed", closing_date="2026-09-30"),
        make_job("5", title="Unknown", status=None, closing_date=None),
    )
    try:
        with psycopg.connect(database_url) as connection:
            connection.execute("DELETE FROM source_records WHERE domain = 'jobs'")
            for job in jobs:
                _insert_record(connection, job)

        repository = PostgresCourseProgramRepository(config.connect)
        assert repository.find_job_by_entity_id("9") == jobs[1]
        assert repository.find_jobs_by_title("  SAME   date NINE ") == (jobs[1],)
        assert [
            record.entity_id
            for record in repository.current_jobs(20, date(2026, 9, 14))
        ] == ["7", "9", "10", "2"]
        assert [
            record.entity_id
            for record in repository.current_jobs(2, date(2026, 9, 14))
        ] == ["7", "9"]

        with TestClient(
            create_app(repository, jobs_today_provider=lambda: date(2026, 9, 14))
        ) as client:
            response = client.get("/api/v1/jobs/current?limit=3")
            chat = client.post(
                "/api/v1/ask",
                json=ask_payload("Tell me about job 9"),
            )
        assert response.status_code == 200
        assert [item["job_id"] for item in response.json()["items"]] == [
            "7", "9", "10"
        ]
        assert chat.status_code == 200
        assert chat.json()["sources"][0]["url"] == str(jobs[1].canonical_url)
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute("DELETE FROM source_records WHERE domain = 'jobs'")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("extra", "not-approved"),
        ("job_id", "different"),
        ("status", "open"),
        ("closing_date", "2026-02-30"),
        ("closing_at", "2026-09-27T23:55:00"),
        ("employment_types", ["Fixed Term", 7]),
    ],
)
def test_database_rejects_jobs_metadata_outside_frozen_contract(field, value):
    database_url = _local_test_url()
    job = make_job()
    values = _record_values(job)
    metadata = job.metadata_json.model_dump(mode="python")
    metadata[field] = value
    values["metadata_json"] = Jsonb(metadata)

    with psycopg.connect(database_url) as connection:
        with pytest.raises((psycopg.errors.CheckViolation, psycopg.DataError)):
            _insert_record_values(connection, values)
        connection.rollback()


@pytest.mark.parametrize(
    "canonical_url",
    [
        "http://jobs.anu.edu.au/jobs/test-role",
        "https://jobs.anu.edu.au/jobs/test-role/",
        "https://jobs.anu.edu.au/jobs/test/role",
        "https://jobs.anu.edu.au/jobs/test-role?ref=search",
        "https://jobs.anu.edu.au/jobs/test-role#details",
        "https://jobs.anu.edu.au/me",
    ],
)
def test_database_rejects_noncanonical_job_url(canonical_url):
    database_url = _local_test_url()
    values = _record_values(make_job())
    values["canonical_url"] = canonical_url

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_record_values(connection, values)
        connection.rollback()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entity_id", "not-numeric"),
        ("record_id", "jobs:job:different"),
        ("effective_from", datetime(2026, 9, 14, tzinfo=timezone.utc)),
        ("effective_to", datetime(2026, 9, 14, tzinfo=timezone.utc)),
    ],
)
def test_database_rejects_jobs_identity_and_effective_date_mismatches(field, value):
    database_url = _local_test_url()
    values = _record_values(make_job())
    values[field] = value

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_record_values(connection, values)
        connection.rollback()


def test_jobs_downgrade_refuses_without_deleting_rows(monkeypatch):
    database_url = _local_test_url()
    monkeypatch.setenv("DATABASE_URL", database_url)
    job = make_job("765432")
    try:
        with psycopg.connect(database_url) as connection:
            _insert_record(connection, job)

        with psycopg.connect(database_url) as connection:
            version_before = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]

        with pytest.raises(DBAPIError, match="Cannot downgrade while Jobs"):
            command.downgrade(Config(ROOT / "alembic.ini"), "20260914_0003")

        with psycopg.connect(database_url) as connection:
            assert connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0] == version_before
            assert connection.execute(
                "SELECT count(*) FROM source_records WHERE record_id = %s",
                (job.record_id,),
            ).fetchone()[0] == 1
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute("DELETE FROM source_records WHERE domain = 'jobs'")


@pytest.mark.parametrize(
    ("entity_id", "different_url_slug"),
    [
        ("foo.*", "foo-123"),
        ("foo|bar", "bar"),
        ("foo[0-9]", "foo7"),
        ("foo+", "fooo"),
        ("foo?", "fo"),
    ],
)
def test_database_rejects_regex_like_entity_id_for_different_literal_url_slug(
    entity_id, different_url_slug
):
    database_url = _local_test_url()
    values = _record_values(make_scholarship())
    values.update(
        entity_id=entity_id,
        record_id=f"scholarships:scholarship:{entity_id}",
        canonical_url=f"{SCHOLARSHIP_URL_PREFIX}{different_url_slug}",
    )

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_record_values(connection, values)
        connection.rollback()


def test_database_accepts_exact_literal_scholarship_url_slug():
    database_url = _local_test_url()
    entity_id = "foo-bar"
    values = _record_values(make_scholarship())
    values.update(
        entity_id=entity_id,
        record_id=f"scholarships:scholarship:{entity_id}",
        canonical_url=f"{SCHOLARSHIP_URL_PREFIX}{entity_id}",
    )

    with psycopg.connect(database_url) as connection:
        assert _insert_record_values(connection, values) == 1
        stored = connection.execute(
            "SELECT entity_id, canonical_url FROM source_records WHERE record_id = %s",
            (values["record_id"],),
        ).fetchone()
        assert stored == (entity_id, values["canonical_url"])
        connection.rollback()


@pytest.mark.parametrize(
    "canonical_url",
    [
        "http://study.anu.edu.au/scholarships/find-scholarship/foo",
        "HTTPS://study.anu.edu.au/scholarships/find-scholarship/foo",
        "https://STUDY.ANU.EDU.AU/scholarships/find-scholarship/foo",
        "https://study.anu.edu.au:443/scholarships/find-scholarship/foo",
        "https://www.anu.edu.au/scholarships/find-scholarship/foo",
        "https://example.anu.edu.au/scholarships/find-scholarship/foo",
        "https://study.anu.edu.au/study/scholarships/find-scholarship/foo",
        "https://study.anu.edu.au/scholarships/find-a-scholarship/foo",
        "https://study.anu.edu.au/find-scholarship/foo",
        "https://study.anu.edu.au/scholarships/find-scholarship/foo/",
        "https://study.anu.edu.au/scholarships/find-scholarship/foo?year=2026",
        "https://study.anu.edu.au/scholarships/find-scholarship/foo#details",
    ],
)
def test_database_rejects_noncanonical_scholarship_url_boundary(canonical_url):
    database_url = _local_test_url()
    values = _record_values(make_scholarship())
    values.update(
        entity_id="foo",
        record_id="scholarships:scholarship:foo",
        canonical_url=canonical_url,
    )

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_record_values(connection, values)
        connection.rollback()


@pytest.mark.parametrize(
    "invalid_slug",
    [
        "Foo",
        "FOO",
        "foo_bar",
        "foo--bar",
        "-foo",
        "foo-",
        "foo.bar",
        "foo/bar",
        "foo%20bar",
        "foo*bar",
        "foo.*",
        "foo+bar",
        "foo?",
        "foo|bar",
        "foo[0-9]",
        "foo[bar]",
    ],
)
def test_database_rejects_scholarship_slug_outside_frozen_grammar(invalid_slug):
    database_url = _local_test_url()
    values = _record_values(make_scholarship())
    values.update(
        entity_id=invalid_slug,
        record_id=f"scholarships:scholarship:{invalid_slug}",
        canonical_url=f"{SCHOLARSHIP_URL_PREFIX}{invalid_slug}",
    )

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_record_values(connection, values)
        connection.rollback()


def test_day12_previous_head_upgrades_to_new_head_without_resource_rows(monkeypatch):
    database_url = _local_test_url()
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(ROOT / "alembic.ini")
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "DELETE FROM source_records WHERE domain IN ('accommodation', 'support')"
        )
    command.downgrade(config, "20260915_0007")
    command.upgrade(config, "head")

    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == ScriptDirectory.from_config(config).get_current_head()


def test_day12_round_trip_restores_exact_0007_resource_behavior(monkeypatch):
    database_url = _local_test_url()
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(ROOT / "alembic.ini")

    accommodation_base = _provisional_accommodation_values()["metadata_json"].obj
    support_base = _provisional_support_values()["metadata_json"].obj

    def changed(base, key, value):
        metadata = copy.deepcopy(base)
        if key == "extra":
            metadata["unexpected"] = value
        else:
            metadata[key] = value
        return metadata

    cases = (
        ("accommodation valid", _provisional_accommodation_values(), True),
        (
            "accommodation invalid scalar type",
            _provisional_accommodation_values(
                changed(accommodation_base, "accommodation_type", [])
            ),
            False,
        ),
        (
            "accommodation invalid array type",
            _provisional_accommodation_values(
                changed(accommodation_base, "audience", "Students")
            ),
            False,
        ),
        (
            "accommodation invalid array nullability",
            _provisional_accommodation_values(
                changed(accommodation_base, "room_types", None)
            ),
            False,
        ),
        (
            "accommodation extra key",
            _provisional_accommodation_values(
                changed(accommodation_base, "extra", True)
            ),
            False,
        ),
        (
            "accommodation source authority",
            _provisional_accommodation_values(
                changed(accommodation_base, "source_authority", "approved_anusa")
            ),
            False,
        ),
        ("support valid", _provisional_support_values(), True),
        (
            "support invalid scalar type",
            _provisional_support_values(changed(support_base, "contact", [])),
            False,
        ),
        (
            "support invalid array member",
            _provisional_support_values(changed(support_base, "categories", [1])),
            False,
        ),
        (
            "support invalid array nullability",
            _provisional_support_values(changed(support_base, "audience", None)),
            False,
        ),
        (
            "support extra key",
            _provisional_support_values(changed(support_base, "extra", True)),
            False,
        ),
        (
            "support source authority",
            _provisional_support_values(
                changed(support_base, "source_authority", "official_anu")
            ),
            False,
        ),
    )
    expected = {name: accepted for name, _values, accepted in cases}

    def observed_behavior() -> dict[str, bool]:
        return {
            name: _insert_is_accepted(database_url, values)
            for name, values, _accepted in cases
        }

    try:
        command.upgrade(config, "head")
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM source_records WHERE domain IN ('accommodation', 'support')"
            )
        command.downgrade(config, "20260915_0007")
        before = observed_behavior()
        assert before == expected

        command.upgrade(config, "20260916_0008")
        command.downgrade(config, "20260915_0007")
        after = observed_behavior()
        assert after == before
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM source_records WHERE domain IN ('accommodation', 'support')"
            )
        command.upgrade(config, "head")


def test_database_accepts_frozen_day12_records_and_rejects_obsolete_shape(monkeypatch):
    database_url = _local_test_url()
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(ROOT / "alembic.ini"), "head")
    accommodation = AccommodationRecord.model_validate(accommodation_payload())
    support = SupportRecord.model_validate(support_payload())
    try:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM source_records WHERE domain IN ('accommodation', 'support')"
            )
            assert _insert_record(connection, accommodation) == 1
            assert _insert_record(connection, support) == 1
            connection.execute(
                "DELETE FROM source_records WHERE domain = 'accommodation'"
            )

        obsolete = _record_values(accommodation)
        obsolete["record_id"] = "accommodation:accommodation:yukeembruk"
        obsolete_metadata = accommodation.metadata_json.model_dump(mode="python")
        obsolete_metadata["entity_type"] = "accommodation"
        obsolete["metadata_json"] = Jsonb(obsolete_metadata)
        with psycopg.connect(database_url) as connection:
            with pytest.raises(psycopg.errors.CheckViolation):
                _insert_record_values(connection, obsolete)
            connection.rollback()
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM source_records WHERE domain IN ('accommodation', 'support')"
            )


@pytest.mark.parametrize(
    "url",
    [
        "https://anusa.com.au/student-assistance/academic/",
        "https://ANUSA.com.au/student-assistance/academic/",
        "https://AnUsA.com.au/student-assistance/academic/",
        "https://WWW.ANUSA.COM.AU/student-assistance/academic/",
        "https://WwW.AnUsA.CoM.aU/student-assistance/academic/",
    ],
    ids=[
        "lowercase",
        "uppercase",
        "mixed-case",
        "www-uppercase",
        "www-mixed-case",
    ],
)
def test_database_rejects_internal_anusa_support_referral_for_any_hostname_case(
    url,
):
    database_url = _local_test_url()
    values = _support_values_with_nested_url("referrals", url)

    assert not _insert_is_accepted(database_url, values)


def test_database_accepts_valid_external_support_referral():
    database_url = _local_test_url()
    values = _support_values_with_nested_url(
        "referrals", "https://www.legalaidact.org.au/get-legal-help"
    )

    assert _insert_is_accepted(database_url, values)


@pytest.mark.parametrize(
    "url",
    [
        "https://AnUsA.com.au/student-assistance/academic/appeals/",
        "https://WWW.ANUSA.COM.AU/student-assistance/academic/appeals/",
    ],
    ids=["mixed-case", "www-uppercase"],
)
def test_database_accepts_mixed_case_support_topic_like_python_validator(url):
    database_url = _local_test_url()
    payload = support_payload()
    payload["metadata_json"]["topics"][0]["url"] = url
    record = SupportRecord.model_validate(payload)

    assert record.metadata_json.topics[0].url == url
    assert _insert_is_accepted(database_url, _record_values(record))


@pytest.mark.parametrize(
    ("record_factory", "field", "value"),
    [
        (lambda: AccommodationRecord.model_validate(accommodation_payload()), "record_id", "accommodation:residence:bruce-hall"),
        (lambda: AccommodationRecord.model_validate(accommodation_payload()), "canonical_url", "https://study.anu.edu.au/accommodation/our-residences/bruce-hall"),
        (lambda: SupportRecord.model_validate(support_payload()), "record_id", "support:service:academic"),
        (lambda: SupportRecord.model_validate(support_payload()), "canonical_url", "https://anusa.com.au/student-assistance/financial/"),
    ],
)
def test_database_rejects_day12_identity_mismatches(record_factory, field, value):
    database_url = _local_test_url()
    values = _record_values(record_factory())
    values[field] = value

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_record_values(connection, values)
        connection.rollback()


def test_day12_guard_refuses_known_provisional_rows_without_rewrite(monkeypatch):
    database_url = _local_test_url()
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(ROOT / "alembic.ini")
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "DELETE FROM source_records WHERE domain IN ('accommodation', 'support')"
        )
    command.downgrade(config, "20260915_0007")
    frozen = AccommodationRecord.model_validate(accommodation_payload())
    values = _record_values(frozen)
    values["record_id"] = "accommodation:accommodation:yukeembruk"
    values["metadata_json"] = Jsonb(
        {
            "entity_type": "accommodation",
            "source_authority": "official_anu",
            "accommodation_type": "Residence hall",
            "location": "Acton campus",
            "catering": "Self-catered",
            "audience": ["Students"],
            "room_types": ["Single room"],
            "advertised_rate": "$340 per week",
            "rate_inclusions": ["Utilities"],
            "rate_exclusions": ["Meals"],
            "facilities": ["Study room"],
            "application_information": "Apply online",
            "eligibility": None,
            "contract_term": "44 weeks",
            "contact": "Accommodation Services",
        }
    )
    try:
        with psycopg.connect(database_url) as connection:
            _insert_record_values(connection, values)

        with pytest.raises(DBAPIError, match="Known provisional"):
            command.upgrade(config, "head")

        with psycopg.connect(database_url) as connection:
            assert connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0] == "20260915_0007"
            assert connection.execute(
                "SELECT record_id FROM source_records WHERE entity_id = 'yukeembruk'"
            ).fetchone()[0] == "accommodation:accommodation:yukeembruk"
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM source_records WHERE domain IN ('accommodation', 'support')"
            )
        command.upgrade(config, "head")


@pytest.mark.parametrize("field", ["effective_from", "effective_to"])
def test_database_rejects_non_null_scholarship_effective_dates(field):
    database_url = _local_test_url()
    values = _record_values(make_scholarship())
    values[field] = datetime(2026, 9, 13, tzinfo=timezone.utc)

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert_record_values(connection, values)
        connection.rollback()


def test_database_accepts_frozen_official_and_rubric_event_records():
    database_url = _local_test_url()
    events = load_common_records(EVENT_FIXTURE)[:2]
    for event in events:
        assert isinstance(
            EventRecord.model_validate(event.model_dump(mode="python")),
            EventRecord,
        )
        assert _insert_is_accepted(database_url, _record_values(event))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("record_id", "event:anu-official-1001"),
        ("source_id", "rubric_unified_search"),
        (
            "canonical_url",
            "https://appserver.getqpay.com:9090/AppServerSwapnil/event/details",
        ),
    ],
)
def test_database_rejects_event_identity_source_and_url_mismatches(field, value):
    database_url = _local_test_url()
    values = _record_values(load_common_records(EVENT_FIXTURE)[0])
    values[field] = value
    assert not _insert_is_accepted(database_url, values)


def test_database_rejects_naive_event_start_and_unknown_metadata():
    database_url = _local_test_url()
    base = _record_values(load_common_records(EVENT_FIXTURE)[0])
    metadata = dict(base["metadata_json"].obj)
    metadata["start_at"] = "2026-09-20T10:00:00"
    base["metadata_json"] = Jsonb(metadata)
    assert not _insert_is_accepted(database_url, base)

    metadata["start_at"] = "2026-09-20T10:00:00+10:00"
    metadata["is_official"] = True
    base["metadata_json"] = Jsonb(metadata)
    assert not _insert_is_accepted(database_url, base)


def test_postgres_upcoming_events_path_is_official_only():
    database_url = _local_test_url()
    config = DatabaseConnectionConfig.from_settings(
        Settings(database_url=SecretStr(database_url))
    )
    events = load_common_records(EVENT_FIXTURE)
    with psycopg.connect(database_url) as connection:
        connection.execute("DELETE FROM source_records WHERE domain = 'events'")
        for event in events:
            _insert_record(connection, event)
    try:
        repository = PostgresCourseProgramRepository(config.connect)
        selected = repository.upcoming_official_events(
            5, datetime(2026, 9, 19, 9, tzinfo=timezone(timedelta(hours=10)))
        )
        assert [record.entity_id for record in selected] == [
            "anu-official-1001",
            "anu-official-1002",
        ]
        assert all(record.source_id == "events_anu_official" for record in selected)
        assert {record.source_id for record in repository.all_events()} == {
            "events_anu_official",
            "rubric_unified_search",
        }
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute("DELETE FROM source_records WHERE domain = 'events'")
