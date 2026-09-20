"""Deterministic, source-grounded Event API and conversational retrieval."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

from askanu_rag.course_queries import _source_from_record
from askanu_rag.event_time import (
    CANBERRA,
    events_starting_in_window,
    resolve_event_time_window,
    upcoming_events,
)
from askanu_rag.models import (
    AskResponse,
    EventRecord,
    InsufficientEvidenceResponse,
    OkResponse,
    UpcomingEventItem,
)
from askanu_rag.retrieval import EventReader

EVENT_WORD_PATTERN = re.compile(r"\bevents?\b", re.IGNORECASE)
LOCATION_PATTERN = re.compile(r"\b(?:where|venue|location|address)\b", re.IGNORECASE)
ORGANISER_PATTERN = re.compile(r"\b(?:who|organiser|organizer|host)\b", re.IGNORECASE)
PERIOD_PATTERNS = (
    (re.compile(r"\bthis\s+friday\b", re.IGNORECASE), "this Friday"),
    (re.compile(r"\bnext\s+week\b", re.IGNORECASE), "next week"),
    (re.compile(r"\btomorrow\b", re.IGNORECASE), "tomorrow"),
    (re.compile(r"\btoday\b", re.IGNORECASE), "today"),
)


def canberra_now() -> datetime:
    return datetime.now(CANBERRA)


def event_start(record: EventRecord) -> datetime:
    return datetime.fromisoformat(record.metadata_json.start_at.replace("Z", "+00:00"))


def upcoming_event_item(record: EventRecord) -> UpcomingEventItem:
    if record.source_id != "events_anu_official":
        raise ValueError("Upcoming Events accepts official ANU records only")
    metadata = record.metadata_json
    return UpcomingEventItem(
        record_id=record.record_id,
        source_id=record.source_id,
        title=record.title,
        start_at=metadata.start_at,
        end_at=metadata.end_at,
        venue=metadata.venue_name,
        organiser=metadata.organiser_name,
        status=metadata.cancellation_status or metadata.source_status,
        url=record.canonical_url,
        domain="events",
    )


def is_plausible_event_question(question: str) -> bool:
    return EVENT_WORD_PATTERN.search(question) is not None


def _requested_period(question: str):
    for pattern, period in PERIOD_PATTERNS:
        if pattern.search(question):
            return period
    return None


class EventQueryService:
    """Answer basic Event questions from persisted official and Rubric records."""

    def __init__(
        self,
        repository: EventReader,
        now_provider: Callable[[], datetime] = canberra_now,
        *,
        limit: int = 5,
    ) -> None:
        self._repository = repository
        self._now_provider = now_provider
        self._limit = limit

    async def answer(self, question: str, request_id: str) -> AskResponse:
        now = self._now_provider()
        records = self._repository.all_events()
        period = _requested_period(question)
        if period is not None:
            window = resolve_event_time_window(period, now=now)
            selected = () if window is None else events_starting_in_window(
                records,
                window=window,
                start_at=event_start,
                stable_key=lambda record: record.record_id,
            )[: self._limit]
        else:
            selected = upcoming_events(
                records,
                now=now,
                start_at=event_start,
                stable_key=lambda record: record.record_id,
                limit=self._limit,
            )

        if not selected:
            return InsufficientEvidenceResponse(
                answer="I could not find persisted Event evidence for that time period.",
                request_id=request_id,
            )

        wants_location = LOCATION_PATTERN.search(question) is not None
        wants_organiser = ORGANISER_PATTERN.search(question) is not None
        sections: list[str] = []
        for record in selected:
            metadata = record.metadata_json
            facts = [f"Starts: {metadata.start_at}."]
            if metadata.end_at is not None:
                facts.append(f"Ends: {metadata.end_at}.")
            if metadata.venue_name is not None:
                facts.append(f"Venue: {metadata.venue_name}.")
            elif wants_location:
                facts.append("Venue: not published in the stored source record.")
            if metadata.address is not None:
                facts.append(f"Address: {metadata.address}.")
            if metadata.organiser_name is not None:
                facts.append(f"Organiser: {metadata.organiser_name}.")
            elif wants_organiser:
                facts.append("Organiser: not published in the stored source record.")
            if metadata.source_status is not None:
                facts.append(f"Source status: {metadata.source_status}.")
            if metadata.cancellation_status is not None:
                facts.append(
                    f"Cancellation status: {metadata.cancellation_status}."
                )
            sections.append(f"{record.title}. " + " ".join(facts))

        return OkResponse(
            answer="\n\n".join(sections),
            sources=[_source_from_record(record) for record in selected],
            request_id=request_id,
        )
