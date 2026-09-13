"""Day 7 PostgreSQL adapter tests without any live database or secret."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from askanu_rag.config import Settings
from askanu_rag.database import DatabaseConnectionConfig
from askanu_rag.main import (
    create_app,
    create_configured_app,
    create_configured_repository,
)
from askanu_rag.models import (
    CommonRecord,
    CourseMetadata,
    CourseProgramRecord,
    ProgramMetadata,
    ScholarshipRecord,
)
from askanu_rag.retrieval import (
    CourseProgramRepository,
    PostgresCourseProgramRepository,
    UnavailableCourseProgramRepository,
    load_common_records,
)

SCHOLARSHIP_FIXTURE = (
    Path(__file__).parents[1] / "fixtures/day9_scholarship_records.json"
)


def make_record(
    code: str = "COMP1110",
    year: str = "2026",
    *,
    entity_type: str = "course",
) -> CourseProgramRecord:
    is_course = entity_type == "course"
    title = "Structured Programming" if is_course else "Bachelor of Accounting"
    content = (
        "Structured Programming\nCourse Code: COMP1110\nAcademic Year: 2026\n"
        "Prerequisites: COMP1100 OR COMP1130 OR COMP1730"
        if is_course
        else "Bachelor of Accounting\nProgram Code: BACCT\nAcademic Year: 2026"
    )
    metadata = (
        CourseMetadata(
            entity_type="course",
            course_code=code,
            academic_year=year,
            prerequisites="COMP1100 OR COMP1130 OR COMP1730",
            incompatibilities="COMP1140 or COMP6710 or COMP7710",
            assumed_knowledge=None,
            offerings=None,
        )
        if is_course
        else ProgramMetadata(
            entity_type="program", program_code=code, academic_year=year
        )
    )
    observed = datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc)
    return CourseProgramRecord(
        record_id=f"courses:{entity_type}:{code}_{year}",
        source_id="courses_programs_and_courses",
        entity_id=f"{code}_{year}",
        domain="courses",
        title=title,
        content=content,
        canonical_url=(
            f"https://programsandcourses.anu.edu.au/{year}/"
            f"{'course' if is_course else 'program'}/{code.lower()}"
        ),
        status="NEW",
        effective_from=None,
        effective_to=None,
        collected_at=observed,
        last_seen_at=observed,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        embedding_version=None,
        index_status="PENDING",
        metadata_json=metadata,
    )


def database_row(record: CourseProgramRecord) -> dict[str, object]:
    row = record.model_dump(mode="python")
    row["canonical_url"] = str(record.canonical_url)
    row["metadata_json"] = record.metadata_json.model_dump(mode="python")
    return row


def make_scholarship(index: int = 0) -> ScholarshipRecord:
    record = load_common_records(SCHOLARSHIP_FIXTURE)[index]
    return ScholarshipRecord.model_validate(record.model_dump(mode="python"))


class FakeCursor:
    def __init__(self, rows, calls):
        self.rows = rows
        self.calls = calls
        self.results = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, parameters=()):
        self.calls.append((query, parameters))
        if "scholarships_anu_finder" in query:
            self.results = [
                row for row in self.rows if row["domain"] == "scholarships"
            ]
            if parameters:
                self.results = [
                    row
                    for row in self.results
                    if row["entity_id"] == parameters[0]
                ]
            self.results.sort(key=lambda row: row["record_id"])
            return
        if not parameters:
            self.results = sorted(
                (row for row in self.rows if row["domain"] == "courses"),
                key=lambda row: row["record_id"],
            )
            return
        entity_type, code, *year = parameters
        code_key = "course_code" if entity_type == "course" else "program_code"
        self.results = [
            row
            for row in self.rows
            if row["metadata_json"]["entity_type"] == entity_type
            and row["metadata_json"][code_key] == code
            and (
                not year or row["metadata_json"]["academic_year"] == year[0]
            )
        ]
        self.results.sort(
            key=lambda row: (row["metadata_json"]["academic_year"], row["record_id"])
        )

    def fetchall(self):
        return self.results


class FakeConnection:
    def __init__(self, rows, calls):
        self.rows = rows
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return FakeCursor(self.rows, self.calls)


def fake_repository(records):
    calls = []
    rows = [database_row(record) for record in records]
    return PostgresCourseProgramRepository(
        lambda: FakeConnection(rows, calls)
    ), calls


def ask_payload(question):
    return {
        "question": question,
        "history": [],
        "conversation_state": {"pending_clarification": None},
    }


def test_cloud_sql_connection_uses_protected_unix_socket_components(monkeypatch):
    settings = Settings(
        environment="production",
        database_name="askanu",
        database_user="askanu_backend",
        database_password=SecretStr("local-test-password-sentinel"),
        cloud_sql_instance_connection_name=(
            "askanu-dev-gdg:australia-southeast1:askanu-postgres-dev"
        ),
    )
    config = DatabaseConnectionConfig.from_settings(settings)
    captured = {}

    def fake_connect(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("askanu_rag.database.psycopg.connect", fake_connect)
    config.connect()

    assert captured["args"] == ()
    assert captured["kwargs"]["dbname"] == "askanu"
    assert captured["kwargs"]["user"] == "askanu_backend"
    assert captured["kwargs"]["host"] == (
        "/cloudsql/askanu-dev-gdg:australia-southeast1:askanu-postgres-dev"
    )
    assert "local-test-password-sentinel" not in repr(config)


def test_protected_sqlalchemy_style_url_is_normalized_for_direct_psycopg(monkeypatch):
    config = DatabaseConnectionConfig.from_settings(
        Settings(database_url=SecretStr(
            "postgresql+psycopg://local_user:local_password@127.0.0.1/local_db"
        ))
    )
    captured = {}

    def fake_connect(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("askanu_rag.database.psycopg.connect", fake_connect)
    config.connect()

    assert captured["args"] == (
        "postgresql://local_user:local_password@127.0.0.1/local_db",
    )
    assert "local_password" not in repr(config)


def test_postgres_exact_course_program_year_and_parameterised_queries():
    records = [
        make_record(year="2025"),
        make_record(year="2026"),
        make_record("BACCT", entity_type="program"),
    ]
    repository, calls = fake_repository(records)

    result = repository.find_course_by_code("comp 1110", "2026")
    assert result is not None and not isinstance(result, tuple)
    assert result.metadata_json.academic_year == "2026"
    assert str(result.canonical_url).endswith("/2026/course/comp1110")
    assert result.content_hash == records[1].content_hash
    assert result.metadata_json.assumed_knowledge is None
    assert result.metadata_json.offerings is None

    assert repository.find_course_by_code("COMP1110", "2030") is None
    ambiguous = repository.find_course_by_code("COMP1110")
    assert isinstance(ambiguous, tuple)
    assert [record.metadata_json.academic_year for record in ambiguous] == [
        "2025",
        "2026",
    ]
    program = repository.find_program_by_code(" bacct ", "2026")
    assert program is not None and not isinstance(program, tuple)
    assert program.metadata_json.entity_type == "program"

    query, parameters = calls[0]
    assert "%s" in query
    assert "COMP1110" not in query
    assert parameters == ("course", "COMP1110", "2026")


def test_postgres_catalog_preserves_full_validated_records():
    records = [make_record(), make_record("BACCT", entity_type="program")]
    repository, _calls = fake_repository(records)

    assert repository.all_records() == tuple(sorted(records, key=lambda r: r.record_id))


def test_postgres_scholarship_round_trip_uses_generic_table_and_exact_metadata():
    scholarship = make_scholarship()
    repository, calls = fake_repository([make_record(), scholarship])

    found = repository.find_scholarship_by_entity_id(scholarship.entity_id)
    all_scholarships = repository.all_scholarships()

    assert found == scholarship
    assert all_scholarships == (scholarship,)
    assert isinstance(found, ScholarshipRecord)
    assert set(found.metadata_json.model_dump()) == {
        "entity_type",
        "featured",
        "status",
        "application_required",
        "study_stage",
        "student_type",
        "study_level",
        "area_of_study",
        "value",
        "selection_basis",
        "opening_date",
        "closing_date",
        "eligibility",
    }
    assert found.embedding_version is None
    assert found.index_status == "PENDING"
    assert found.content_hash == scholarship.content_hash
    assert str(found.canonical_url) == str(scholarship.canonical_url)
    assert all("FROM source_records" in query for query, _parameters in calls)
    assert "academic_year" not in found.metadata_json.model_dump()
    assert set(CommonRecord.model_fields) == {
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
    }


class CapturingSynthesisClient:
    def __init__(self):
        self.context = None

    async def synthesize(self, context):
        self.context = context
        return json.dumps({"answer": context.allowed_answers[0], "supported": True})


def test_db_backed_api_grounding_and_source_are_programmatic():
    record = make_record()
    repository, _calls = fake_repository([record])
    synthesis = CapturingSynthesisClient()
    client = TestClient(create_app(repository, synthesis))

    response = client.post(
        "/api/v1/ask",
        json=ask_payload("What are the prerequisites for COMP1110 in 2026?"),
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["answer"].endswith("COMP1100 OR COMP1130 OR COMP1730")
    assert body["sources"][0]["url"] == (
        "https://programsandcourses.anu.edu.au/2026/course/comp1110"
    )
    assert body["request_id"].startswith("req_")
    assert synthesis.context.academic_year == "2026"
    assert synthesis.context.prerequisites == "COMP1100 OR COMP1130 OR COMP1730"
    assert "canonical_url" not in synthesis.context.contents()


def test_production_selects_postgres_and_never_fixture(tmp_path):
    configured = Settings(
        environment="production",
        database_name="askanu",
        database_user="askanu_backend",
        database_password=SecretStr("local-only"),
        cloud_sql_instance_connection_name="project:region:instance",
        course_records_path=tmp_path / "must-not-be-read.json",
    )
    assert isinstance(
        create_configured_repository(configured), PostgresCourseProgramRepository
    )
    assert isinstance(
        create_configured_repository(Settings(environment="production")),
        UnavailableCourseProgramRepository,
    )
    assert isinstance(create_configured_repository(Settings()), CourseProgramRepository)


def test_missing_production_db_config_keeps_health_shallow_and_ask_controlled(
    monkeypatch,
):
    monkeypatch.setattr(
        Settings,
        "from_environment",
        classmethod(lambda cls: Settings(environment="production")),
    )
    with TestClient(create_configured_app(), raise_server_exceptions=False) as client:
        health = client.get("/health")
        response = client.post(
            "/api/v1/ask", json=ask_payload("Prerequisites for COMP1110 2026")
        )

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert response.status_code == 500
    assert response.json()["status"] == "error"
    assert response.json()["request_id"].startswith("req_")


def test_db_failure_is_controlled_and_logs_no_diagnostics(caplog):
    def fail_connect():
        raise RuntimeError(
            "postgresql://test_user:fake-value@db.invalid/test_db "
            "traceback /synthetic/private.py"
        )

    repository = PostgresCourseProgramRepository(fail_connect)
    client = TestClient(create_app(repository), raise_server_exceptions=False)
    caplog.set_level(logging.INFO, logger="uvicorn.error.askanu_rag.requests")

    response = client.post(
        "/api/v1/ask", json=ask_payload("Prerequisites for COMP1110 2026")
    )

    body = response.json()
    assert response.status_code == 500
    assert set(body) == {
        "status", "answer", "items", "sources", "clarification", "request_id"
    }
    assert body["status"] == "error"
    assert body["request_id"].startswith("req_")
    combined = (response.text + caplog.text).lower()
    for forbidden in (
        "fake-value", "db.invalid", "test_user", "postgresql://", "traceback",
        "/synthetic/private.py",
    ):
        assert forbidden not in combined
    assert "http_status=500" in caplog.text
    assert "response_status=error" in caplog.text
    assert "latency_ms=" in caplog.text


def test_request_metrics_log_valid_upstream_id_separately_without_raw_question(
    caplog,
):
    sentinel = "raw-question-sentinel"
    upstream_request_id = "app-7f8a02d4-4c71-4fe1-a23c"
    caplog.set_level(logging.INFO, logger="uvicorn.error.askanu_rag.requests")
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/ask",
        json=ask_payload(sentinel),
        headers={"X-Request-Id": upstream_request_id},
    )

    assert response.status_code == 200
    api_request_id = response.json()["request_id"]
    assert api_request_id.startswith("req_")
    assert api_request_id != upstream_request_id
    assert f"request_id={api_request_id}" in caplog.text
    assert f"upstream_request_id={upstream_request_id}" in caplog.text
    assert "path=/api/v1/ask" in caplog.text
    assert "http_status=200" in caplog.text
    assert "response_status=off_topic" in caplog.text
    assert "latency_ms=" in caplog.text
    assert sentinel not in caplog.text


def test_invalid_upstream_request_id_is_not_logged_or_used_as_api_id(caplog):
    unsafe_header = "invalid/request-id-secret-sentinel"
    caplog.set_level(logging.INFO, logger="uvicorn.error.askanu_rag.requests")
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/ask",
        json=ask_payload("hello"),
        headers={"X-Request-Id": unsafe_header},
    )

    assert response.status_code == 200
    assert response.json()["request_id"].startswith("req_")
    assert response.json()["request_id"] != unsafe_header
    assert "upstream_request_id=invalid" in caplog.text
    assert unsafe_header not in caplog.text
