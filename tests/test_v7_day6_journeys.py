"""Day 6 acceptance journeys for Jobs, Events and Support."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from askanu_rag.event_queries import EVENT_POPULATION_COMPLETE
from askanu_rag.event_time import CANBERRA
from askanu_rag.main import create_app
from askanu_rag.models import (
    EventMetadata,
    EventRecord,
    JobMetadata,
    JobRecord,
    SupportContact,
    SupportMetadata,
    SupportRecord,
    SupportTopic,
)
from askanu_rag.retrieval import CourseProgramRepository

TODAY = date(2026, 9, 14)
NOW = datetime(2026, 9, 14, 9, tzinfo=CANBERRA)


def job(
    identifier: str,
    *,
    title: str,
    closing_date: str | None = "2026-09-30",
    status: str | None = "current",
    requirements: list[str] | None = None,
) -> JobRecord:
    content = f"{title}. Verified role evidence."
    observed = datetime(2026, 9, 14, tzinfo=timezone.utc)
    return JobRecord(
        record_id=f"jobs:job:{identifier}",
        source_id="jobs_anu_search",
        entity_id=identifier,
        domain="jobs",
        title=title,
        content=content,
        canonical_url=f"https://jobs.anu.edu.au/jobs/{identifier}",
        status="NEW",
        effective_from=None,
        effective_to=None,
        collected_at=observed,
        last_seen_at=observed,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        embedding_version=None,
        index_status="PENDING",
        metadata_json=JobMetadata(
            entity_type="job",
            job_id=identifier,
            category="Information Technology",
            employment_types=["Fixed-term"],
            location="Canberra / ACT",
            classification="ANU08",
            salary=None,
            closing_text=closing_date,
            closing_date=closing_date,
            closing_at=None,
            status=status,
            summary=content,
            role_requirements=requirements,
        ),
    )


def event(
    identifier: str,
    *,
    day: int,
    hour: int,
    source_id: str = "events_anu_official",
    venue: str | None = "Kambri",
    organiser: str | None = "ANU Events",
) -> EventRecord:
    canonical_id = (
        identifier
        if source_id == "events_anu_official"
        else f"rubric-{identifier}"
    )
    title = f"Event {identifier}"
    content = f"{title}. Approved event evidence."
    observed = datetime(2026, 9, 14, tzinfo=timezone.utc)
    return EventRecord(
        record_id=f"events:event:{canonical_id}",
        source_id=source_id,
        entity_id=canonical_id,
        domain="events",
        title=title,
        content=content,
        canonical_url=(
            f"https://www.anu.edu.au/events/{identifier}"
            if source_id == "events_anu_official"
            else f"https://campus.hellorubric.com/?eid={identifier}"
        ),
        status="NEW",
        effective_from=None,
        effective_to=None,
        collected_at=observed,
        last_seen_at=observed,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        embedding_version=None,
        index_status="PENDING",
        metadata_json=EventMetadata(
            entity_type="event",
            source_event_id=identifier,
            start_at=f"2026-09-{day:02d}T{hour:02d}:00:00+10:00",
            end_at=None,
            timezone="Australia/Canberra",
            organiser_name=organiser,
            venue_name=venue,
            address=None,
            latitude=None,
            longitude=None,
            category="Community",
            tags=["student"],
            registration_url=None,
            source_status="scheduled",
            cancellation_status=None,
            audience="ANU community",
        ),
    )


def support_service(*, with_contact: bool = True) -> SupportRecord:
    title = "ANUSA Student Assistance"
    content = (
        "Academic advocacy and help for assignment grading, assessment concerns, "
        "grade reviews and study difficulties."
    )
    observed = datetime(2026, 9, 14, tzinfo=timezone.utc)
    return SupportRecord(
        record_id="support:support_service:student-assistance",
        source_id="support_anusa_student_assistance",
        entity_id="student-assistance",
        domain="support",
        title=title,
        content=content,
        canonical_url="https://anusa.com.au/student-assistance/student-assistance/",
        status="NEW",
        effective_from=None,
        effective_to=None,
        collected_at=observed,
        last_seen_at=observed,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        embedding_version=None,
        index_status="PENDING",
        metadata_json=SupportMetadata(
            entity_type="support_service",
            category="Academic advocacy",
            purpose=content,
            audiences=["ANU students"],
            contact=SupportContact(
                email="student.assistance@anusa.com.au" if with_contact else None,
                phone=None,
                location="ANUSA office, Kambri" if with_contact else None,
            ),
            hours=None,
            access="Use the published enquiry form.",
            cost="Free for ANU students",
            topics=[
                SupportTopic(
                    title="Assessment concerns",
                    description="Academic advocacy for assessment and grading concerns.",
                    url="https://anusa.com.au/student-assistance/student-assistance/assessment/",
                )
            ],
            referrals=[],
        ),
    )


def post(
    client: TestClient,
    question: str,
    state: dict | None = None,
    *,
    selected_result: dict | None = None,
) -> dict:
    payload = {
        "question": question,
        "history": [],
        "conversation_state": state or {},
    }
    if selected_result is not None:
        payload["selected_result"] = selected_result
    response = client.post(
        "/api/v1/ask",
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_jobs_resultset_selection_requirements_and_continuation_are_stable():
    records = [
        job(
            str(700000 + index),
            title=("Software Engineer" if index == 1 else f"Verified Role {index}"),
            closing_date=f"2026-09-{14 + index:02d}",
            requirements=["Published requirement A", "Published requirement B"],
        )
        for index in range(1, 8)
    ]
    class MustNotRun:
        def __init__(self):
            self.calls = 0

        def search(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("generic listing and continuation must not rerank")

    vector = MustNotRun()
    with TestClient(
        create_app(
            CourseProgramRepository(records),
            jobs_today_provider=lambda: TODAY,
            vector_retriever=vector,
        )
    ) as client:
        broad = post(client, "What jobs are available at ANU?")
        assert broad["answer_state"] == "PARTIAL"
        assert "population is incomplete" in broad["answer"]
        assert [item["ordinal"] for item in broad["items"]] == [1, 2, 3, 4, 5]
        assert broad["result_page"]["next_ordinal"] == 6

        clicked = post(
            client,
            "What are the requirements?",
            broad["conversation_state"],
            selected_result={
                "result_set_id": broad["result_page"]["result_set_id"],
                "canonical_id": records[0].entity_id,
                "ordinal": 1,
            },
        )
        assert clicked["items"][0]["canonical_id"] == records[0].entity_id
        assert "Published requirement A" in clicked["answer"]

        first = post(client, "Tell me about the first one", broad["conversation_state"])
        assert first["items"][0]["canonical_id"] == records[0].entity_id
        assert first["items"][0]["ordinal"] == 1

        requirements = post(
            client, "What are the requirements?", first["conversation_state"]
        )
        assert "Published requirement A" in requirements["answer"]
        assert "you qualify" not in requirements["answer"].casefold()

        more = post(client, "Any more?", requirements["conversation_state"])
        assert [item["ordinal"] for item in more["items"]] == [6, 7]
        assert vector.calls == 0


def test_jobs_closing_window_and_incomplete_empty_remain_truthful():
    records = [
        job("710001", title="Closes this week", closing_date="2026-09-18"),
        job("710002", title="No published close", closing_date=None),
        job("710003", title="Closes later", closing_date="2026-09-25"),
    ]
    with TestClient(
        create_app(CourseProgramRepository(records), jobs_today_provider=lambda: TODAY)
    ) as client:
        broad = post(client, "What jobs are available at ANU?")
        closing = post(
            client, "Which ones close this week?", broad["conversation_state"]
        )
        assert [item["canonical_id"] for item in closing["items"]] == ["710001"]
        assert closing["answer_state"] == "PARTIAL"

    with TestClient(
        create_app(
            CourseProgramRepository(
                [job("710099", title="Closed role", status="closed")]
            ),
            jobs_today_provider=lambda: TODAY,
        )
    ) as client:
        empty = post(client, "What jobs are available at ANU?")
        assert empty["status"] == "insufficient_evidence"
        assert "does not establish" in empty["answer"]
        assert empty["conversation_state"]["result_sets"][-1]["status"] == "INCOMPLETE"


def test_events_temporal_constraints_replace_independently():
    records = [
        event("today-early", day=14, hour=13),
        event("today-late", day=14, hour=18),
        event("tomorrow-early", day=15, hour=13),
        event("tomorrow-late", day=15, hour=18),
    ]
    with TestClient(
        create_app(CourseProgramRepository(records), events_now_provider=lambda: NOW)
    ) as client:
        today = post(client, "What events are on at ANU today?")
        after = post(client, "Only after 5pm", today["conversation_state"])
        assert [item["canonical_id"] for item in after["items"]] == ["today-late"]

        tomorrow = post(client, "What about tomorrow?", after["conversation_state"])
        assert [item["canonical_id"] for item in tomorrow["items"]] == ["tomorrow-late"]
        values = {
            item["semantic_type"]: item["value"]
            for item in tomorrow["conversation_state"]["constraints"]["items"]
            if item["scope"]["domain"] == "events"
        }
        assert values == {
            "date_window": "tomorrow",
            "time_of_day_window": "after 17:00",
        }

        before = post(client, "Before 2pm instead", tomorrow["conversation_state"])
        assert [item["canonical_id"] for item in before["items"]] == ["tomorrow-early"]


def test_events_items_provenance_selection_and_continuation():
    records = [
        event(
            str(800000 + index),
            day=14,
            hour=10 + index,
            source_id=("rubric_unified_search" if index == 6 else "events_anu_official"),
            venue=f"Venue {index}",
            organiser=f"Organiser {index}",
        )
        for index in range(1, 8)
    ]
    with TestClient(
        create_app(CourseProgramRepository(records), events_now_provider=lambda: NOW)
    ) as client:
        broad = post(client, "What events are on at ANU today?")
        assert [item["ordinal"] for item in broad["items"]] == [1, 2, 3, 4, 5]
        assert broad["items"][0]["fields"]["provenance_class"] == "official_anu"

        second = post(client, "Where is the second one?", broad["conversation_state"])
        assert second["items"][0]["ordinal"] == 2
        selected_id = second["items"][0]["canonical_id"]
        assert "Venue 2" in second["answer"]

        organiser = post(
            client, "Who is organising it?", second["conversation_state"]
        )
        assert organiser["items"][0]["canonical_id"] == selected_id
        assert "Organiser 2" in organiser["answer"]

        more = post(client, "Any more?", organiser["conversation_state"])
        assert [item["ordinal"] for item in more["items"]] == [6, 7]
        community = next(
            item
            for item in more["items"]
            if item["canonical_id"] == "rubric-800006"
        )
        assert community["source_id"] == "rubric_unified_search"
        assert community["fields"]["provenance_class"] == "approved_community"


def test_event_population_stays_incomplete_until_both_source_gates_close():
    records = [
        event(f"official-{index}", day=14, hour=10 + index % 10)
        for index in range(1, 30)
    ]
    records.append(
        event(
            "rubric-source-control",
            day=14,
            hour=19,
            source_id="rubric_unified_search",
        )
    )

    with TestClient(
        create_app(CourseProgramRepository(records), events_now_provider=lambda: NOW)
    ) as client:
        broad = post(client, "What events are on at ANU today?")
        no_match = post(
            client,
            "What events are in Antarctica?",
            broad["conversation_state"],
        )

    assert EVENT_POPULATION_COMPLETE is False
    assert broad["status"] == "ok"
    assert broad["items"]
    assert {record.source_id for record in records} == {
        "events_anu_official",
        "rubric_unified_search",
    }
    assert no_match["status"] == "insufficient_evidence"
    assert no_match["items"] == []
    assert no_match["conversation_state"]["result_sets"][0]["status"] == (
        "INCOMPLETE"
    )
    assert "population is incomplete" in no_match["answer"]
    assert "does not establish that no such events exist" in no_match["answer"]
    assert "no events" not in no_match["answer"].casefold()


def test_support_natural_routing_structured_item_and_pronoun_followups():
    record = support_service()
    questions = (
        "I think I was graded unfairly on an assignment, who should I talk to?",
        "I have a concern with an assessment",
        "I need academic help",
        "Tell me about ANUSA Student Assistance",
    )
    with TestClient(create_app(CourseProgramRepository([record]))) as client:
        for question in questions:
            body = post(client, question)
            assert body["status"] == "ok"
            assert body["items"][0]["type"] == "result"
            assert body["items"][0]["canonical_id"] == record.entity_id
            assert "marker was wrong" not in body["answer"].casefold()
            assert "appeal will succeed" not in body["answer"].casefold()

        routed = post(client, questions[0])
        contact = post(client, "How do I contact them?", routed["conversation_state"])
        assert "student.assistance@anusa.com.au" in contact["answer"]
        location = post(client, "Where are they?", contact["conversation_state"])
        assert "ANUSA office, Kambri" in location["answer"]


def test_support_missing_contact_is_unknown_and_clear_chat_drops_reference():
    with TestClient(
        create_app(CourseProgramRepository([support_service(with_contact=False)]))
    ) as client:
        routed = post(client, "I need academic help")
        missing = post(client, "How do I contact them?", routed["conversation_state"])
        assert missing["status"] == "insufficient_evidence"
        assert missing["answer_state"] == "UNKNOWN"

        cleared = post(client, "Clear Chat", missing["conversation_state"])
        assert cleared["conversation_state"]["result_sets"] == []
        after = post(client, "How do I contact them?", cleared["conversation_state"])
        assert after["status"] != "ok"
        assert after["sources"] == []


def test_day6_explicit_domain_switches_isolate_resultsets_and_ordinals():
    records = [
        job("720001", title="Verified Job One"),
        job("720002", title="Verified Job Two"),
        event("event-one", day=14, hour=12),
        event("event-two", day=14, hour=13),
        support_service(),
    ]
    with TestClient(
        create_app(
            CourseProgramRepository(records),
            jobs_today_provider=lambda: TODAY,
            events_now_provider=lambda: NOW,
        )
    ) as client:
        jobs = post(client, "What jobs are available at ANU?")
        assert jobs["conversation_state"]["focus"]["domain"] == "jobs"

        events = post(
            client,
            "What events are on at ANU today?",
            jobs["conversation_state"],
        )
        assert events["conversation_state"]["focus"]["domain"] == "events"
        second = post(client, "Where is the second one?", events["conversation_state"])
        assert second["items"][0]["domain"] == "events"
        assert second["items"][0]["canonical_id"] == "event-two"

        support = post(
            client,
            "I think I was graded unfairly on an assignment, who should I talk to?",
            second["conversation_state"],
        )
        assert support["conversation_state"]["focus"]["domain"] == "support"
        assert support["items"][0]["domain"] == "support"
        assert all(item["domain"] != "jobs" for item in support["items"])
