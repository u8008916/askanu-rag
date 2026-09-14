"""Static contract checks for the Day 9 read-only-view follow-up."""

import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
DAY7 = ROOT / "migrations/versions/20260911_0001_course_program_records.py"
DAY9 = ROOT / "migrations/versions/20260913_0002_shared_source_records.py"
READ_ONLY_VIEW = (
    ROOT
    / "migrations/versions/20260914_0003_readonly_course_program_view.py"
)

EXPECTED_COLUMNS = (
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


def load_revision():
    spec = importlib.util.spec_from_file_location("readonly_view_revision", READ_ONLY_VIEW)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_is_additive_after_day9_without_editing_deployed_migrations():
    revision = load_revision()

    assert revision.revision == "20260914_0003"
    assert revision.down_revision == "20260913_0002"
    assert hashlib.sha256(DAY7.read_bytes()).hexdigest() == (
        "80836b03d4484a33626121655355263202839f715e07ebcf1a7e5dcdee28c74c"
    )
    assert hashlib.sha256(DAY9.read_bytes()).hexdigest() == (
        "45186d09b822626bb7d7ea61a78761ea43ee3f859967a4ffba7b4f344f983026"
    )


def test_view_projection_and_course_filter_are_exact():
    revision = load_revision()

    assert tuple(part.strip() for part in revision.VIEW_COLUMNS.split(",")) == (
        EXPECTED_COLUMNS
    )
    assert "source_id = 'courses_programs_and_courses'" in (
        revision.COURSE_PROGRAM_FILTER
    )
    assert "domain = 'courses'" in revision.COURSE_PROGRAM_FILTER


def test_revision_changes_only_the_view_and_uses_a_structural_guard():
    migration = READ_ONLY_VIEW.read_text(encoding="utf-8")

    assert migration.count('op.execute("DROP VIEW course_program_records")') == 2
    assert 'structural_guard = "OFFSET 0"' in migration
    assert "CREATE VIEW course_program_records AS" in migration
    assert "ALTER TABLE" not in migration
    assert "CREATE TABLE" not in migration
    assert "DROP TABLE" not in migration
    assert "INSERT INTO" not in migration
    assert "UPDATE source_records" not in migration
    assert "DELETE FROM" not in migration


def test_downgrade_recreates_the_previous_simple_view_shape():
    revision = load_revision()
    calls: list[str] = []
    original_execute = revision.op.execute
    revision.op.execute = calls.append
    try:
        revision.downgrade()
    finally:
        revision.op.execute = original_execute

    assert calls[0] == "DROP VIEW course_program_records"
    normalized = " ".join(calls[1].split())
    assert "CREATE VIEW course_program_records AS SELECT" in normalized
    assert "FROM source_records WHERE" in normalized
    assert "OFFSET" not in normalized
    assert tuple(
        part.strip()
        for part in normalized.split("SELECT", 1)[1]
        .split("FROM", 1)[0]
        .split(",")
    ) == EXPECTED_COLUMNS
