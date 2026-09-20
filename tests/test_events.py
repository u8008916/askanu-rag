"""Frozen Day 15 Event model, repository, API and chat coverage."""

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from askanu_rag.event_time import CANBERRA
from askanu_rag.event_queries import upcoming_event_item
from askanu_rag.main import create_app
from askanu_rag.models import CommonRecord, EventRecord
from askanu_rag.retrieval import (
    CourseProgramRepository,
    PostgresCourseProgramRepository,
    load_common_records,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "day15_event_records.json"
NOW = datetime(2026, 9, 19, 9, tzinfo=CANBERRA)


def records():
    return load_common_records(FIXTURE)


def payload(question: str):
    return {
        "question": question,
        "history": [],
        "conversation_state": {"pending_clarification": None},
    }


def test_frozen_fixture_is_consumed_through_common_record_envelope():
    loaded = records()
    assert len(loaded) == 4
    assert all(isinstance(record, CommonRecord) for record in loaded)
    assert all(record.domain == "events" for record in loaded)
    assert {record.source_id for record in loaded} == {
        "events_anu_official",
        "rubric_unified_search",
    }


def test_record_id_uses_existing_common_record_convention():
    record = EventRecord.model_validate(records()[0].model_dump(mode="python"))
    assert record.record_id == f"events:event:{record.entity_id}"
    bad = record.model_dump(mode="python")
    bad["record_id"] = "event:1001"
    with pytest.raises(ValidationError, match="record_id"):
        EventRecord.model_validate(bad)


def test_required_start_must_be_timezone_aware_and_optional_keys_may_be_missing():
    minimal = EventRecord.model_validate(records()[2].model_dump(mode="python"))
    assert minimal.metadata_json.end_at is None
    assert minimal.metadata_json.venue_name is None
    bad = minimal.model_dump(mode="python")
    bad["metadata_json"]["start_at"] = "2026-09-21T09:00:00"
    with pytest.raises(ValidationError, match="timezone|offset"):
        EventRecord.model_validate(bad)


def test_unknown_event_metadata_is_not_silently_widened():
    bad = records()[0].model_dump(mode="python")
    bad["metadata_json"]["is_official"] = True
    with pytest.raises(ValidationError, match="extra"):
        EventRecord.model_validate(bad)


def test_rubric_internal_detail_api_can_never_be_a_student_source_link():
    rubric = next(record for record in records() if record.source_id == "rubric_unified_search")
    bad = rubric.model_dump(mode="python")
    bad["canonical_url"] = (
        "https://appserver.getqpay.com:9090/AppServerSwapnil/event/details"
    )
    with pytest.raises(ValidationError, match="public event page"):
        EventRecord.model_validate(bad)


def test_source_id_cannot_be_relabelled_without_matching_public_canonical_url():
    official = records()[0].model_dump(mode="python")
    official["source_id"] = "rubric_unified_search"
    with pytest.raises(ValidationError, match="public event page"):
        EventRecord.model_validate(official)


def test_upcoming_endpoint_is_official_only_past_safe_and_deterministic():
    repository = CourseProgramRepository(records())
    client = TestClient(create_app(repository, events_now_provider=lambda: NOW))
    response = client.get("/api/v1/events/upcoming")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert [item["record_id"] for item in body["items"]] == [
        "events:event:anu-official-1001",
        "events:event:anu-official-1002",
    ]
    assert all(item["source_id"] == "events_anu_official" for item in body["items"])
    assert all(item["domain"] == "events" for item in body["items"])
    assert body["items"][1]["end_at"] is None
    assert body["items"][1]["venue"] is None
    assert "rubric-78459" not in str(body)
    assert "anu-official-0999" not in str(body)


def test_upcoming_dto_refuses_a_rubric_record_even_if_called_directly():
    rubric = EventRecord.model_validate(
        next(
            record for record in records()
            if record.source_id == "rubric_unified_search"
        ).model_dump(mode="python")
    )
    with pytest.raises(ValueError, match="official ANU"):
        upcoming_event_item(rubric)


def test_upcoming_endpoint_limits_after_filtering_and_rejects_bad_limits():
    repository = CourseProgramRepository(records())
    client = TestClient(create_app(repository, events_now_provider=lambda: NOW))
    assert len(client.get("/api/v1/events/upcoming?limit=1").json()["items"]) == 1
    for value in ("0", "-1", "21", "bad"):
        assert client.get(f"/api/v1/events/upcoming?limit={value}").status_code == 400


def test_event_chat_reads_official_and_rubric_and_preserves_provenance():
    repository = CourseProgramRepository(records())
    client = TestClient(create_app(repository, events_now_provider=lambda: NOW))
    response = client.post("/api/v1/ask", json=payload("What events are upcoming?"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert {source["source_id"] for source in body["sources"]} == {
        "events_anu_official",
        "rubric_unified_search",
    }
    assert all(source["domain"] == "events" for source in body["sources"])
    rubric = next(
        source for source in body["sources"]
        if source["source_id"] == "rubric_unified_search"
    )
    assert rubric["url"] == "https://campus.hellorubric.com/?eid=78459"


def test_event_chat_keeps_missing_optional_facts_unknown():
    repository = CourseProgramRepository(records())
    today = datetime(2026, 9, 20, 8, tzinfo=CANBERRA)
    client = TestClient(create_app(repository, events_now_provider=lambda: today))
    body = client.post(
        "/api/v1/ask", json=payload("Where are the events today?")
    ).json()
    assert body["status"] == "ok"
    assert "Venue: not published in the stored source record." in body["answer"]
    assert "free" not in body["answer"].casefold()
    assert "tickets remaining" not in body["answer"].casefold()


def test_postgres_read_paths_enforce_official_only_upcoming_in_sql():
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, parameters):
            calls.append((query, parameters))

        def fetchall(self):
            return []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

    repository = PostgresCourseProgramRepository(lambda: Connection())
    assert repository.upcoming_official_events(5, NOW) == ()
    query, parameters = calls[-1]
    assert "source_id = 'events_anu_official'" in query
    assert "rubric_unified_search" not in query
    assert "::timestamptz >= %s" in query
    assert parameters == (NOW, 5)

    assert repository.all_events() == ()
    broad_query, _parameters = calls[-1]
    assert "events_anu_official" in broad_query
    assert "rubric_unified_search" in broad_query
