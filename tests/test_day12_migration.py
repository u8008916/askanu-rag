"""Focused static tests for append-only Day 12 contract revision 0008."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[1]
REVISION = (
    ROOT
    / "migrations"
    / "versions"
    / "20260916_0008_day12_resource_contracts.py"
)
PREVIOUS = ROOT / "migrations" / "versions" / "20260915_0007_nullable_array_checks.py"


def load_revision():
    spec = importlib.util.spec_from_file_location("day12_resource_revision", REVISION)
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


def run(direction: str):
    revision = load_revision()
    recorder = Recorder()
    original = revision.op
    revision.op = recorder
    try:
        getattr(revision, direction)()
    finally:
        revision.op = original
    return revision, recorder


def test_0008_is_linear_after_current_0007_head() -> None:
    revision = load_revision()

    assert revision.revision == "20260916_0008"
    assert revision.down_revision == "20260915_0007"
    assert PREVIOUS.exists()


def test_read_only_guard_runs_before_any_existing_constraint_is_replaced() -> None:
    _revision, recorder = run("upgrade")
    guard_index = next(
        index
        for index, event in enumerate(recorder.events)
        if event[0] == "execute"
        and "Unexpected Accommodation/Support rows" in event[1]
    )
    first_drop = next(
        index for index, event in enumerate(recorder.events) if event[0] == "drop"
    )

    assert guard_index < first_drop


def test_guard_recognizes_frozen_and_known_provisional_shapes_but_refuses_risk() -> None:
    revision = load_revision()
    guard = revision.PRE_MIGRATION_GUARD_SQL

    assert "askanu_day12_accommodation_metadata_valid" in guard
    assert "askanu_day12_support_metadata_valid" in guard
    assert "accommodation:accommodation:" in guard
    assert "accommodation:residence:" in guard
    assert "support:support_service:" in guard
    assert "Unexpected Accommodation/Support rows require manual contract review" in guard
    assert "Known provisional Accommodation/Support rows require manual reingestion" in guard
    assert "UPDATE source_records" not in guard
    assert "DELETE FROM source_records" not in guard


def test_upgrade_replaces_only_day12_related_checks() -> None:
    _revision, recorder = run("upgrade")
    dropped = {event[1] for event in recorder.events if event[0] == "drop"}
    created = {
        event[1]: event[3]
        for event in recorder.events
        if event[0] == "create"
    }

    assert dropped == {
        "ck_source_records_entity_type",
        "ck_source_records_record_id",
        "ck_source_records_accommodation_identity",
        "ck_source_records_accommodation_metadata",
        "ck_source_records_support_identity",
        "ck_source_records_support_metadata",
    }
    assert set(created) == dropped
    assert "'residence'" in created["ck_source_records_entity_type"]
    assert "accommodation:residence:" in created["ck_source_records_record_id"]
    assert "support:support_service:" in created["ck_source_records_record_id"]


def test_frozen_identity_checks_require_exact_slug_canonical_urls() -> None:
    _revision, recorder = run("upgrade")
    checks = {
        event[1]: event[3]
        for event in recorder.events
        if event[0] == "create"
    }

    accommodation = checks["ck_source_records_accommodation_identity"]
    support = checks["ck_source_records_support_identity"]
    assert "canonical_url =" in accommodation
    assert "our-residences/' || entity_id" in accommodation
    assert "canonical_url =" in support
    assert "student-assistance/' || entity_id || '/'" in support


def test_frozen_metadata_validators_have_exact_nested_contracts() -> None:
    revision = load_revision()
    accommodation = revision.ACCOMMODATION_VALIDATOR_SQL
    support = revision.SUPPORT_VALIDATOR_SQL

    for field in (
        "catering_options",
        "audiences",
        "cost_period",
        "rooms",
        "other_fees",
        "application_url",
        "vacancy_status",
    ):
        assert field in accommodation
    assert "source_authority" not in accommodation
    assert "starrezhousing[.]com" in accommodation
    for field in (
        "purpose",
        "audiences",
        "contact",
        "access",
        "topics",
        "referrals",
    ):
        assert field in support
    assert "source_authority" not in support
    assert "student-assistance" in support
    assert "external" not in support.casefold()  # behavior is encoded, not inferred text


def test_upgrade_never_rewrites_or_deletes_resource_rows() -> None:
    _revision, recorder = run("upgrade")
    sql = "\n".join(event[1] for event in recorder.events if event[0] == "execute")

    assert "UPDATE source_records" not in sql
    assert "DELETE FROM source_records" not in sql


def test_downgrade_refuses_data_and_restores_provisional_checks_only_when_empty() -> None:
    _revision, recorder = run("downgrade")
    sql = "\n".join(event[1] for event in recorder.events if event[0] == "execute")
    checks = {
        event[1]: event[3]
        for event in recorder.events
        if event[0] == "create"
    }

    assert "Cannot downgrade frozen Day 12 contracts" in sql
    assert "'accommodation'" in checks["ck_source_records_entity_type"]
    assert "accommodation:accommodation:" in checks["ck_source_records_record_id"]
    assert "DROP FUNCTION askanu_day12_support_metadata_valid" in sql
    assert "DROP FUNCTION askanu_day12_accommodation_metadata_valid" in sql
