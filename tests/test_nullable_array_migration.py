"""Regression tests for nullable-array PostgreSQL constraint hotfix 0007."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[1]
REVISION = (
    ROOT
    / "migrations"
    / "versions"
    / "20260915_0007_nullable_array_checks.py"
)


def load_revision():
    spec = importlib.util.spec_from_file_location(
        "nullable_array_revision",
        REVISION,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recorder:
    def __init__(self):
        self.created = []
        self.dropped = []

    def create_check_constraint(self, name, table, condition):
        self.created.append((name, table, condition))

    def drop_constraint(self, name, table, type_):
        self.dropped.append((name, table, type_))


def run_upgrade():
    revision = load_revision()
    recorder = Recorder()
    original = revision.op
    revision.op = recorder
    try:
        revision.upgrade()
    finally:
        revision.op = original
    return revision, recorder


def test_0007_is_append_only_after_0006():
    revision = load_revision()

    assert revision.revision == "20260915_0007"
    assert revision.down_revision == "20260915_0006"


def test_0007_replaces_only_the_three_nullable_array_checks():
    _revision, recorder = run_upgrade()

    assert {name for name, _table, _type in recorder.dropped} == {
        "ck_source_records_job_metadata_types",
        "ck_source_records_subplan_metadata",
        "ck_source_records_courses_optional_metadata_types",
    }

    assert {name for name, _table, _condition in recorder.created} == {
        "ck_source_records_job_metadata_types",
        "ck_source_records_subplan_metadata",
        "ck_source_records_courses_optional_metadata_types",
    }


def test_0007_null_guards_are_explicit():
    _revision, recorder = run_upgrade()
    checks = {
        name: condition
        for name, _table, condition in recorder.created
    }

    jobs = checks["ck_source_records_job_metadata_types"]
    assert "role_requirements" in jobs
    assert (
        "jsonb_typeof(metadata_json -> 'role_requirements') = 'null'"
        in jobs
    )

    courses = checks["ck_source_records_courses_optional_metadata_types"]
    assert "learning_outcomes" in courses
    assert (
        "jsonb_typeof(metadata_json -> 'learning_outcomes') = 'null'"
        in courses
    )

    subplans = checks["ck_source_records_subplan_metadata"]
    assert "learning_outcomes" in subplans
    assert "relevant_degrees" in subplans
    assert (
        "jsonb_typeof(metadata_json -> 'learning_outcomes') = 'null'"
        in subplans
    )
    assert (
        "jsonb_typeof(metadata_json -> 'relevant_degrees') = 'null'"
        in subplans
    )


def test_0007_downgrade_does_not_reintroduce_known_invalid_checks():
    revision = load_revision()
    recorder = Recorder()
    original = revision.op
    revision.op = recorder
    try:
        revision.downgrade()
    finally:
        revision.op = original

    assert recorder.created == []
    assert recorder.dropped == []
