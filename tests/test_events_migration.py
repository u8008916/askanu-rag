"""Static contract tests for the append-only Events migration chain."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
REVISION_0009 = (
    ROOT / "migrations" / "versions" / "20260919_0009_events_contract.py"
)
REVISION_0010 = (
    ROOT / "migrations" / "versions" / "20260921_0010_event_source_identity.py"
)


def load_revision(path=REVISION_0009):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recorder:
    def __init__(self):
        self.events = []

    def execute(self, sql):
        self.events.append(("execute", str(sql)))

    def create_check_constraint(self, name, table, condition):
        self.events.append(("create", name, table, str(condition)))

    def drop_constraint(self, name, table, type_):
        self.events.append(("drop", name, table, type_))


def run(direction, path=REVISION_0009):
    revision = load_revision(path)
    recorder = Recorder()
    original = revision.op
    revision.op = recorder
    try:
        getattr(revision, direction)()
    finally:
        revision.op = original
    return revision, recorder


def test_0009_is_linear_and_uses_shared_source_records():
    revision = load_revision()
    assert revision.revision == "20260919_0009"
    assert revision.down_revision == "20260916_0008"
    text = REVISION_0009.read_text(encoding="utf-8")
    assert "source_records" in text
    assert "CREATE TABLE" not in text
    assert "ck_source_records_event_source_identity" not in text


def test_upgrade_adds_both_sources_event_identity_and_common_record_id():
    _revision, recorder = run("upgrade")
    checks = {
        event[1]: event[3] for event in recorder.events if event[0] == "create"
    }
    source_domain = checks["ck_source_records_source_domain"]
    assert "events_anu_official" in source_domain
    assert "rubric_unified_search" in source_domain
    assert "domain = 'events'" in source_domain
    assert "metadata_json ->> 'entity_type' = 'event'" in checks[
        "ck_source_records_entity_type"
    ]
    assert "'events:event:' || entity_id" in checks["ck_source_records_record_id"]


def test_metadata_validator_has_only_frozen_core_keys_and_aware_times():
    revision = load_revision()
    sql = revision.EVENT_METADATA_VALIDATOR_SQL
    for key in (
        "source_event_id", "start_at", "end_at", "timezone", "organiser_name",
        "venue_name", "address", "latitude", "longitude", "category", "tags",
        "registration_url", "source_status", "cancellation_status", "audience",
    ):
        assert key in sql
    assert "?& ARRAY['entity_type', 'source_event_id', 'start_at']" in sql
    assert "Z|[+-]" in sql
    assert "is_official" not in sql
    assert "upcoming" not in sql
    assert "last_refreshed" not in sql


def test_canonical_checks_keep_official_and_rubric_boundaries_distinct():
    _revision, recorder = run("upgrade")
    check = next(
        event[3]
        for event in recorder.events
        if event[0] == "create"
        and event[1] == "ck_source_records_event_canonical_url"
    )
    assert "www[.]anu[.]edu[.]au/events/" in check
    assert "campus[.]hellorubric[.]com" in check
    assert "eid=" in check


def test_downgrade_refuses_event_data_and_restores_previous_checks():
    _revision, recorder = run("downgrade")
    sql = "\n".join(event[1] for event in recorder.events if event[0] == "execute")
    checks = {
        event[1]: event[3] for event in recorder.events if event[0] == "create"
    }
    assert "Cannot downgrade the Events contract while Event records exist" in sql
    assert "events_anu_official" not in checks["ck_source_records_source_domain"]
    assert "events:event:" not in checks["ck_source_records_record_id"]
    assert "DROP FUNCTION askanu_v6_event_metadata_valid" in sql


def test_0010_is_additive_and_enforces_frozen_event_source_identity():
    revision, recorder = run("upgrade", REVISION_0010)
    assert revision.revision == "20260921_0010"
    assert revision.down_revision == "20260919_0009"
    assert recorder.events == [
        (
            "create",
            "ck_source_records_event_source_identity",
            "source_records",
            revision.CONSTRAINT_SQL,
        )
    ]
    constraint = revision.CONSTRAINT_SQL
    assert "entity_id = metadata_json ->> 'source_event_id'" in constraint
    assert "entity_id = 'rubric-' ||" in constraint
    assert "substring(canonical_url" in constraint
    assert "eid=" in constraint


def test_0010_downgrade_removes_only_its_constraint():
    _revision, recorder = run("downgrade", REVISION_0010)
    assert recorder.events == [
        (
            "drop",
            "ck_source_records_event_source_identity",
            "source_records",
            "check",
        )
    ]
