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
FINAL_PRODUCER_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "day16_scraper_event_records.json"
)
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


def test_final_merged_scraper_records_cross_the_consumer_boundary_unchanged():
    official, rubric = load_common_records(FINAL_PRODUCER_FIXTURE)
    assert isinstance(EventRecord.model_validate(official.model_dump()), EventRecord)
    assert isinstance(EventRecord.model_validate(rubric.model_dump()), EventRecord)
    assert (
        official.source_id,
        official.entity_id,
        official.metadata_json.source_event_id,
        official.record_id,
        str(official.canonical_url),
    ) == (
        "events_anu_official",
        "1001",
        "1001",
        "events:event:1001",
        "https://www.anu.edu.au/events/window-opening",
    )
    assert (
        rubric.source_id,
        rubric.entity_id,
        rubric.metadata_json.source_event_id,
        rubric.record_id,
        str(rubric.canonical_url),
    ) == (
        "rubric_unified_search",
        "rubric-78459",
        "78459",
        "events:event:rubric-78459",
        "https://campus.hellorubric.com/?eid=78459",
    )
    assert official.content_hash == (
        "31a1c414bd822e2e35c895a05799b6eb3494dca89800ed7efdf13b78f4c821b7"
    )
    assert rubric.content_hash == (
        "3e103cb9abcb83dc6c5138083b4837a3b9b6fd00fcfafd489faf430dda78b9bf"
    )


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


@pytest.mark.parametrize(
    ("source_id", "wrong_source_event_id"),
    [("events_anu_official", "99999"), ("rubric_unified_search", "99999")],
)
def test_source_event_id_must_match_the_frozen_source_identity(
    source_id, wrong_source_event_id
):
    bad = next(
        record.model_dump(mode="python")
        for record in records()
        if record.source_id == source_id
    )
    bad["metadata_json"]["source_event_id"] = wrong_source_event_id
    with pytest.raises(ValidationError, match="entity_id|public event page"):
        EventRecord.model_validate(bad)


@pytest.mark.parametrize("key", ["format", "registration_links", "status"])
def test_old_or_ambiguous_event_metadata_vocabulary_is_rejected(key):
    bad = records()[0].model_dump(mode="python")
    bad["metadata_json"][key] = "unsupported"
    with pytest.raises(ValidationError, match="extra"):
        EventRecord.model_validate(bad)


def test_date_only_event_start_is_rejected_without_inventing_midnight():
    bad = records()[0].model_dump(mode="python")
    bad["metadata_json"]["start_at"] = "2026-09-20"
    with pytest.raises(ValidationError, match="ISO-8601|timestamp"):
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
        "events:event:1001",
        "events:event:1002",
    ]
    assert all(item["source_id"] == "events_anu_official" for item in body["items"])
    assert all(item["domain"] == "events" for item in body["items"])
    assert body["items"][1]["end_at"] is None
    assert body["items"][1]["venue"] is None
    assert "rubric-78459" not in str(body)
    assert "events:event:0999" not in str(body)


def test_upcoming_keeps_an_official_event_until_its_known_end():
    ongoing_payload = records()[0].model_dump(mode="python")
    ongoing_payload.update(
        entity_id="ongoing-1001",
        record_id="events:event:ongoing-1001",
        canonical_url="https://www.anu.edu.au/events/ongoing-event",
        title="Ongoing official Event",
    )
    ongoing_payload["metadata_json"].update(
        source_event_id="ongoing-1001",
        start_at="2026-09-19T08:00:00+10:00",
        end_at="2026-09-19T10:00:00+10:00",
    )
    ongoing = EventRecord.model_validate(ongoing_payload)
    client = TestClient(
        create_app(
            CourseProgramRepository([ongoing]),
            events_now_provider=lambda: NOW,
        )
    )
    response = client.get("/api/v1/events/upcoming")
    assert response.status_code == 200
    assert [item["record_id"] for item in response.json()["items"]] == [
        "events:event:ongoing-1001"
    ]


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


def test_no_event_evidence_is_controlled_and_never_fabricated():
    client = TestClient(
        create_app(CourseProgramRepository([]), events_now_provider=lambda: NOW)
    )
    upcoming = client.get("/api/v1/events/upcoming")
    assert upcoming.status_code == 200
    assert upcoming.json()["status"] == "ok"
    assert upcoming.json()["items"] == []

    chat = client.post("/api/v1/ask", json=payload("What events are upcoming?"))
    assert chat.status_code == 200
    assert chat.json()["status"] == "insufficient_evidence"
    assert chat.json()["sources"] == []


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
    assert "registration available" not in body["answer"].casefold()
    assert "online" not in body["answer"].casefold()
    assert "in-person" not in body["answer"].casefold()
    assert "cancelled" not in body["answer"].casefold()


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
    assert "COALESCE(" in query
    assert "metadata_json ->> 'end_at'" in query
    assert ")::timestamptz >= %s" in query
    assert parameters == (NOW, 5)

    assert repository.all_events() == ()
    broad_query, _parameters = calls[-1]
    assert "events_anu_official" in broad_query
    assert "rubric_unified_search" in broad_query
