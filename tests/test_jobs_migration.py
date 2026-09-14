"""Static contract checks for the additive Day 10 Jobs migration."""

import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
DAY7 = ROOT / "migrations/versions/20260911_0001_course_program_records.py"
DAY9 = ROOT / "migrations/versions/20260913_0002_shared_source_records.py"
READ_ONLY = (
    ROOT / "migrations/versions/20260914_0003_readonly_course_program_view.py"
)
JOBS = ROOT / "migrations/versions/20260914_0004_jobs_records.py"

EXPECTED_KEYS = {
    "entity_type",
    "job_id",
    "category",
    "employment_types",
    "location",
    "classification",
    "salary",
    "closing_text",
    "closing_date",
    "closing_at",
    "status",
    "summary",
}


def load_jobs_revision():
    spec = importlib.util.spec_from_file_location("jobs_revision", JOBS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_jobs_revision_follows_readonly_view_and_preserves_history():
    revision = load_jobs_revision()

    assert revision.revision == "20260914_0004"
    assert revision.down_revision == "20260914_0003"
    assert hashlib.sha256(DAY7.read_bytes()).hexdigest() == (
        "80836b03d4484a33626121655355263202839f715e07ebcf1a7e5dcdee28c74c"
    )
    assert hashlib.sha256(DAY9.read_bytes()).hexdigest() == (
        "45186d09b822626bb7d7ea61a78761ea43ee3f859967a4ffba7b4f344f983026"
    )
    assert hashlib.sha256(READ_ONLY.read_bytes()).hexdigest() == (
        "909ce0831afc27093f880161dc5aa8959ae1c2802d4b06db0897ad4366494c86"
    )


def test_jobs_migration_uses_frozen_source_identity_and_exact_metadata_keys():
    revision = load_jobs_revision()
    migration = JOBS.read_text(encoding="utf-8")
    keys = {
        value.strip().strip("'")
        for value in revision.JOB_KEYS.removeprefix("ARRAY[")
        .removesuffix("]")
        .split(",")
    }

    assert keys == EXPECTED_KEYS
    assert "source_id = 'jobs_anu_search' AND domain = 'jobs'" in migration
    assert "metadata_json ->> 'entity_type' = 'job'" in migration
    assert "entity_id ~ '^[0-9]+$'" in migration
    assert "metadata_json ->> 'job_id' = entity_id" in migration
    assert "'jobs:job:' || entity_id" in migration
    assert "uq_source_records_job_identity" in migration


def test_jobs_url_dates_status_and_list_types_are_database_checked():
    migration = JOBS.read_text(encoding="utf-8")

    assert "^https://jobs[.]anu[.]edu[.]au/jobs/[^/?#[:space:]]+$" in migration
    assert "effective_from IS NULL AND effective_to IS NULL" in migration
    assert "('current', 'closed')" in migration
    assert "jsonb_typeof(metadata_json -> 'employment_types') = 'array'" in migration
    assert '@.type() != \\"string\\"' in migration
    assert "::date" in migration
    assert "::timestamptz" in migration


def test_jobs_migration_does_not_modify_view_tables_or_data():
    migration = JOBS.read_text(encoding="utf-8").upper()

    assert "COURSE_PROGRAM_RECORDS" not in migration
    assert "CREATE TABLE" not in migration
    assert "DROP TABLE" not in migration
    assert "ALTER COLUMN" not in migration
    assert "INSERT INTO" not in migration
    assert "UPDATE SOURCE_RECORDS" not in migration
    assert "DELETE FROM" not in migration


def test_jobs_downgrade_refuses_rows_and_restores_pre_jobs_shared_checks():
    migration = JOBS.read_text(encoding="utf-8")

    assert "Cannot downgrade while Jobs source_records exist" in migration
    assert "_create_shared_checks(include_jobs=False)" in migration
    assert "courses_programs_and_courses" in migration
    assert "scholarships_anu_finder" in migration
    assert "DELETE FROM source_records" not in migration
