"""Static contract tests for append-only Courses-family revision 0006."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
REVISION = ROOT / "migrations/versions/20260915_0006_courses_family_subplans.py"
PREVIOUS = ROOT / "migrations/versions/20260915_0005_shared_hybrid_embeddings.py"


def load_revision():
    spec = importlib.util.spec_from_file_location("courses_family_revision", REVISION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recorder:
    def __init__(self):
        self.executed = []
        self.created_checks = []
        self.dropped_checks = []
        self.dropped_indexes = []

    def execute(self, sql):
        self.executed.append(str(sql))

    def create_check_constraint(self, name, table, condition):
        self.created_checks.append((name, table, condition))

    def drop_constraint(self, name, table, type_):
        self.dropped_checks.append((name, table, type_))

    def drop_index(self, name, table_name):
        self.dropped_indexes.append((name, table_name))


def run_migration(direction):
    revision = load_revision()
    recorder = Recorder()
    original = revision.op
    revision.op = recorder
    try:
        getattr(revision, direction)()
    finally:
        revision.op = original
    return revision, recorder


def test_0006_is_linear_after_existing_hybrid_revision():
    revision = load_revision()

    assert revision.revision == "20260915_0006"
    assert revision.down_revision == "20260915_0005"
    assert PREVIOUS.exists()


def test_upgrade_expands_identity_url_metadata_and_uniqueness_contracts():
    _revision, recorder = run_migration("upgrade")
    checks = {name: condition for name, _table, condition in recorder.created_checks}

    assert all(
        entity in checks["ck_source_records_entity_type"]
        for entity in ("course", "program", "major", "minor", "specialisation")
    )
    assert "subplan_code" in checks["ck_source_records_course_normalized_code"]
    assert "subplan_code" in checks["ck_source_records_course_entity_id"]
    canonical = checks["ck_source_records_courses_canonical_url"]
    assert "https://programsandcourses.anu.edu.au/" in canonical
    assert "lower" in canonical
    metadata = checks["ck_source_records_subplan_metadata"]
    for field in (
        "overview",
        "learning_outcomes",
        "requirements",
        "relevant_degrees",
        "other_information",
    ):
        assert field in metadata
    assert "metadata_json - ARRAY[" in metadata
    assert "= '{}'::jsonb" in metadata
    executed = "\n".join(recorder.executed)
    assert "CREATE UNIQUE INDEX uq_source_records_courses_identity" in executed
    assert "UPDATE source_records" in executed
    assert "Cannot normalize unexpected Courses canonical URL" in executed


def test_compatibility_view_is_read_only_and_excludes_all_subplans():
    _revision, recorder = run_migration("upgrade")
    view_sql = next(
        sql for sql in recorder.executed if "CREATE VIEW course_program_records" in sql
    )

    assert "entity_type' IN ('course', 'program')" in view_sql
    assert "OFFSET 0" in view_sql
    assert "major" not in view_sql
    assert "minor" not in view_sql
    assert "specialisation" not in view_sql


def test_downgrade_refuses_subplan_data_and_restores_0005_shapes():
    _revision, recorder = run_migration("downgrade")
    checks = {name: condition for name, _table, condition in recorder.created_checks}
    executed = "\n".join(recorder.executed)

    assert "Cannot downgrade while Courses subplan records exist" in executed
    assert "('course', 'program')" in checks["ck_source_records_entity_type"]
    assert "subplan_code" not in checks["ck_source_records_course_normalized_code"]
    assert "CREATE UNIQUE INDEX uq_source_records_course_program_identity" in executed
    assert "DROP TABLE" not in executed
    assert "DELETE FROM" not in executed
    assert "upper(canonical_url)" not in executed
    assert "UPDATE source_records" not in executed


def test_0006_nullable_course_and_subplan_arrays_are_null_safe():
    text = REVISION.read_text(encoding="utf-8")

    assert (
        "jsonb_typeof(metadata_json -> 'learning_outcomes') = 'null'"
        in text
    )
    assert (
        "jsonb_typeof(metadata_json -> 'relevant_degrees') = 'null'"
        in text
    )
