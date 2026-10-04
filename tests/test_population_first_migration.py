"""Offline schema migration checks: never connect to a database."""
from pathlib import Path
from test_events_migration import load_revision, run

PATH = Path(__file__).parents[1] / "migrations/versions/20261004_0011_population_first.py"

def test_forward_revision_and_no_data_rewrite():
    revision, recorder = run("upgrade", PATH)
    assert revision.down_revision == "20260921_0010"
    sql = "\n".join(str(item) for item in recorder.events)
    assert "UPDATE source_records" not in sql
    assert "DELETE FROM" not in sql
    assert "INSERT INTO" not in sql
    assert "DROP TABLE" not in sql

def test_legacy_and_canonical_job_identity_and_optional_requisition():
    _, recorder = run("upgrade", PATH)
    checks = {event[1]: event[3] for event in recorder.events if event[0] == "create"}
    identity = checks["ck_source_records_job_identity"]
    assert "^[0-9]+$" in identity
    assert "canonical_url" in identity
    assert "requisition_id" in checks["ck_source_records_job_metadata_keys"]
    assert "requisition_id" in checks["ck_source_records_job_metadata_types"]

def test_official_date_precision_and_rubric_legacy_validator():
    module = load_revision(PATH)
    sql = module.EVENT_SQL
    assert "askanu_v6_event_metadata_valid" in sql
    assert "rubric_unified_search" in sql
    assert "start_date" in sql and "end_date" in sql
    assert "date_precision" in sql
    assert "RETURN FALSE" in sql
    assert "::date" in sql

def test_downgrade_cannot_silently_discard_new_contract():
    module = load_revision(PATH)
    import pytest
    with pytest.raises(RuntimeError, match="forward"):
        module.downgrade()
