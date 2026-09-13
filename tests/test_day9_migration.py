"""Day 9 additive migration contract checks."""

import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
DAY7 = ROOT / "migrations/versions/20260911_0001_course_program_records.py"
DAY9 = ROOT / "migrations/versions/20260913_0002_shared_source_records.py"


def load_day9_revision():
    spec = importlib.util.spec_from_file_location("day9_revision", DAY9)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deployed_day7_revision_is_byte_for_byte_untouched():
    digest = hashlib.sha256(DAY7.read_bytes()).hexdigest()
    assert digest == "80836b03d4484a33626121655355263202839f715e07ebcf1a7e5dcdee28c74c"


def test_day9_is_additive_revision_after_deployed_day7():
    revision = load_day9_revision()
    assert revision.revision == "20260913_0002"
    assert revision.down_revision == "20260911_0001"


def test_day9_uses_one_generic_table_and_course_compatibility_view():
    migration = DAY9.read_text(encoding="utf-8")
    normalized = " ".join(migration.split())

    assert 'op.rename_table("course_program_records", "source_records")' in migration
    assert "CREATE VIEW course_program_records AS" in migration
    assert "scholarships_anu_finder" in migration
    assert "domain = 'scholarships'" in migration
    assert "uq_source_records_course_program_identity" in migration
    assert "uq_source_records_scholarship_identity" in migration
    assert "CREATE TABLE SCHOLARSHIPS" not in normalized.upper()
    assert "scholarships_records" not in migration


def test_scholarship_url_slug_identity_uses_literal_equality_not_record_regex():
    migration = DAY9.read_text(encoding="utf-8")

    assert "reverse(split_part(reverse(canonical_url), '/', 1))" in migration
    assert "= entity_id" in migration
    assert "|| entity_id ||" not in migration


def test_downgrade_refuses_to_discard_scholarship_rows():
    migration = DAY9.read_text(encoding="utf-8")
    assert "Cannot downgrade while non-course source_records exist" in migration
    assert "DELETE FROM SOURCE_RECORDS" not in migration.upper()
