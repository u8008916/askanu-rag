"""Versioned migration structure tests; real PostgreSQL is a separate smoke."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

ROOT = Path(__file__).parents[1]
REVISION_PATH = (
    ROOT / "migrations" / "versions" / "20260911_0001_course_program_records.py"
)


def load_revision():
    spec = importlib.util.spec_from_file_location("day7_revision", REVISION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OperationRecorder:
    def __init__(self):
        self.created = None
        self.executed = []
        self.indexes = []
        self.dropped = []

    def create_table(self, name, *items):
        self.created = (name, items)

    def execute(self, statement):
        self.executed.append(statement)

    def create_index(self, name, table, columns, unique=False):
        self.indexes.append((name, table, columns, unique))

    def drop_table(self, name):
        self.dropped.append(name)


def test_alembic_revision_is_single_versioned_head():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "20260911_0001 (head)" in result.stdout


def test_offline_upgrade_compiles_postgresql_sql_without_connecting():
    environment = os.environ.copy()
    environment["ASKANU_ENV"] = "production"
    environment["DATABASE_URL"] = (
        "postgresql://local_test@127.0.0.1/askanu_test"
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    sql = result.stdout
    assert "CREATE TABLE course_program_records" in sql
    assert "CREATE UNIQUE INDEX uq_course_program_records_identity" in sql
    assert "INSERT INTO alembic_version" in sql
    assert "CREATE EXTENSION" not in sql


def test_migration_creates_frozen_schema_and_identity_guards(monkeypatch):
    revision = load_revision()
    recorder = OperationRecorder()
    monkeypatch.setattr(revision, "op", recorder)

    revision.upgrade()

    assert revision.revision == "20260911_0001"
    assert revision.down_revision is None
    assert recorder.created is not None
    table_name, items = recorder.created
    assert table_name == "course_program_records"
    columns = {item.name: item for item in items if isinstance(item, sa.Column)}
    assert set(columns) == {
        "record_id", "source_id", "entity_id", "domain", "title", "content",
        "canonical_url", "status", "effective_from", "effective_to",
        "collected_at", "last_seen_at", "content_hash", "embedding_version",
        "index_status", "metadata_json",
    }
    assert columns["record_id"].primary_key
    assert isinstance(columns["metadata_json"].type, JSONB)
    assert columns["effective_from"].nullable
    assert columns["embedding_version"].nullable
    assert not columns["collected_at"].nullable
    checks = " ".join(
        str(item.sqltext) for item in items if isinstance(item, sa.CheckConstraint)
    )
    for required in (
        "content_hash", "academic_year", "entity_type", "course_code",
        "program_code", "record_id", "entity_id",
    ):
        assert required in checks
    assert any("CREATE UNIQUE INDEX uq_course_program_records_identity" in sql
               for sql in recorder.executed)
    assert {index[0] for index in recorder.indexes} == {
        "ix_course_program_records_title",
        "ix_course_program_records_last_seen_at",
    }


def test_migration_downgrade_is_explicit(monkeypatch):
    revision = load_revision()
    recorder = OperationRecorder()
    monkeypatch.setattr(revision, "op", recorder)

    revision.downgrade()

    assert recorder.dropped == ["course_program_records"]


def test_pgvector_is_not_claimed_or_enabled_by_current_migration():
    migration = REVISION_PATH.read_text(encoding="utf-8").lower()
    assert "create extension" not in migration
    assert "vector(" not in migration


def test_container_includes_explicit_migration_entrypoint_files():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "COPY pyproject.toml README.md alembic.ini ./" in dockerfile
    assert "COPY migrations ./migrations" in dockerfile
    assert "!alembic.ini" in dockerignore
    assert "!migrations/**" in dockerignore
