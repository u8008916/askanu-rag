from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from askanu_rag.models.records import EventRecord, JobRecord
from askanu_rag.retrieval.repository import CourseProgramRepository
from askanu_rag.event_time import select_event_records
from askanu_rag.retrieval.semantic import LocalBm25Retriever
from askanu_rag.job_queries import requisition_label

NOW = datetime(2026,10,4,23,0,tzinfo=ZoneInfo("Australia/Canberra"))

def payload(domain, key):
    return dict(record_id=f"{domain}:{'job' if domain == 'jobs' else 'event'}:{key}",
        source_id="jobs_anu_search" if domain == "jobs" else "events_anu_official",
        entity_id=key, domain=domain, title="Research", content="Research vacancy", status="NEW",
        canonical_url=f"https://jobs.anu.edu.au/jobs/{key}" if domain == "jobs" else f"https://www.anu.edu.au/events/{key}",
        effective_from=None, effective_to=None, collected_at=NOW, last_seen_at=NOW,
        content_hash="a"*64, embedding_version=None, index_status="PENDING")

def job():
    m = dict.fromkeys(("category", "location", "classification", "salary", "closing_text", "closing_date", "closing_at", "summary", "role_requirements", "requisition_id"))
    m.update(entity_type="job", job_id="research-role", employment_types=[], status="current")
    return JobRecord(**payload("jobs","research-role"), metadata_json=m)

def event():
    return EventRecord(**payload("events","research-talk"), metadata_json=dict(entity_type="event", source_event_id=None,
        start_at=None, end_at=None, start_date="2026-10-04", end_date="2026-10-05", date_precision="date"))

def test_listing_job_optional_requisition_and_no_slug_in_answer():
    record=job()
    assert requisition_label(record) == ""
    assert CourseProgramRepository([record]).current_jobs(5,NOW.date()) == (record,)
    enriched=record.model_copy(update={"metadata_json":record.metadata_json.model_copy(update={"requisition_id":"123"})})
    assert CourseProgramRepository([enriched]).find_job_by_entity_id("123") == enriched
    assert requisition_label(enriched) == "Requisition ID: 123."

def test_date_only_event_canberra_overlap_has_no_timestamp():
    record=event()
    assert record.metadata_json.start_at is None
    assert select_event_records([record], now=NOW) == (record,)
    assert select_event_records([record], now=NOW.replace(day=6)) == ()


def test_all_events_orders_mixed_precision_by_canberra_date():
    base = event()

    def variant(key, *, start_at=None, start_date=None):
        metadata = base.metadata_json.model_copy(
            update={
                "start_at": start_at,
                "end_at": None,
                "start_date": start_date,
                "end_date": start_date,
                "date_precision": "timestamp" if start_at is not None else "date",
            }
        )
        return base.model_copy(
            update={
                "record_id": f"events:event:{key}",
                "entity_id": key,
                "canonical_url": f"https://www.anu.edu.au/events/{key}",
                "metadata_json": metadata,
            }
        )

    timed_same_day = variant(
        "z-timed-same-day",
        start_at="2026-10-03T22:00:00+00:00",
    )
    date_only_same_day = variant(
        "a-date-only-same-day",
        start_date="2026-10-04",
    )
    timed_next_day = variant(
        "b-timed-next-day",
        start_at="2026-10-04T22:00:00+00:00",
    )

    repo = CourseProgramRepository(
        [date_only_same_day, timed_next_day, timed_same_day]
    )

    assert [record.entity_id for record in repo.all_events()] == [
        "z-timed-same-day",
        "a-date-only-same-day",
        "b-timed-next-day",
    ]

def test_missing_excluded_exact_current_event_and_sparse():
    j=job().model_copy(update={"status":"MISSING"})
    e=event().model_copy(update={"status":"MISSING"})
    repo=CourseProgramRepository([j,e])
    assert repo.find_job_by_entity_id(j.entity_id) is None
    assert repo.current_jobs(5,NOW.date()) == ()
    assert repo.all_events() == ()
    assert LocalBm25Retriever().search("Research", [j,e],top_k=5,min_score=0) == ()

def test_rubric_cannot_use_date_only_contract():
    data=event().model_dump(mode="python")
    data.update(source_id="rubric_unified_search",entity_id="rubric-123",record_id="events:event:rubric-123",canonical_url="https://campus.hellorubric.com/?eid=123")
    data["metadata_json"]["source_event_id"]="123"
    with pytest.raises(ValueError): EventRecord.model_validate(data)
