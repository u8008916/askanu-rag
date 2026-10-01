"""Deterministic, source-grounded Event API and conversational retrieval."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time

from askanu_rag.course_queries import _source_from_record
from askanu_rag.event_time import (
    CANBERRA,
    events_starting_in_window,
    resolve_event_time_window,
    upcoming_events,
)
from askanu_rag.models import (
    AnswerState,
    AskResponse,
    ConstraintSemanticType,
    ConversationState,
    Domain,
    EntityKind,
    EntityResolutionBasis,
    EventRecord,
    InsufficientEvidenceResponse,
    OkResponse,
    PublicResultItem,
    QueryInterpretation,
    ResolvedEntity,
    ResultPage,
    ResultPageRequest,
    ResultSet,
    ResultSetStatus,
    UpcomingEventItem,
)
from askanu_rag.evidence_selection import build_result_set
from askanu_rag.retrieval import EventReader
from askanu_rag.retrieval_planning import build_retrieval_plan
from askanu_rag.result_paging import (
    ResultPageResolutionError,
    resolve_result_page,
    result_page_metadata,
)
from askanu_rag.state_transitions import (
    refine_result_set,
    remember_entity,
    remember_result_page,
    remember_result_set,
)

EVENT_WORD_PATTERN = re.compile(r"\bevents?\b", re.IGNORECASE)
LOCATION_PATTERN = re.compile(r"\b(?:where|venue|location|address)\b", re.IGNORECASE)
ORGANISER_PATTERN = re.compile(r"\b(?:who|organiser|organizer|host)\b", re.IGNORECASE)
PERIOD_PATTERNS = (
    (re.compile(r"\bthis\s+friday\b", re.IGNORECASE), "this Friday"),
    (re.compile(r"\bnext\s+week\b", re.IGNORECASE), "next week"),
    (re.compile(r"\btomorrow\b", re.IGNORECASE), "tomorrow"),
    (re.compile(r"\btoday\b", re.IGNORECASE), "today"),
)


@dataclass(frozen=True)
class EventQueryOutcome:
    response: AskResponse
    state: ConversationState


def canberra_now() -> datetime:
    return datetime.now(CANBERRA)


def event_start(record: EventRecord) -> datetime:
    return datetime.fromisoformat(record.metadata_json.start_at.replace("Z", "+00:00"))


def event_end(record: EventRecord) -> datetime | None:
    value = record.metadata_json.end_at
    return None if value is None else datetime.fromisoformat(value.replace("Z", "+00:00"))


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


def _constraint_value(
    interpretation: QueryInterpretation | None,
    semantic_type: ConstraintSemanticType,
) -> str | None:
    if interpretation is None:
        return None
    return next(
        (
            str(item.value)
            for item in interpretation.constraints.items
            if item.semantic_type == semantic_type
            and item.scope.domain == Domain.EVENTS
        ),
        None,
    )


def _clock_value(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _matches_time_constraint(record: EventRecord, value: str | None) -> bool:
    if value is None:
        return True
    local_time = event_start(record).astimezone(CANBERRA).time().replace(tzinfo=None)
    if value.startswith("after "):
        return local_time > _clock_value(value.removeprefix("after "))
    if value.startswith("before "):
        return local_time < _clock_value(value.removeprefix("before "))
    if value.startswith("between "):
        start, end = value.removeprefix("between ").split(" and ", 1)
        return _clock_value(start) <= local_time <= _clock_value(end)
    if value == "evening":
        return local_time >= time(17, 0)
    return False


def _event_candidates(
    records: tuple[EventRecord, ...],
    *,
    now: datetime,
    interpretation: QueryInterpretation | None,
    question: str,
) -> tuple[EventRecord, ...]:
    date_value = _constraint_value(
        interpretation, ConstraintSemanticType.DATE_WINDOW
    ) or _requested_period(question)
    if date_value is not None:
        supported_period = {
            "today": "today",
            "tomorrow": "tomorrow",
            "this friday": "this Friday",
            "next week": "next week",
        }.get(date_value.casefold())
        window = (
            None
            if supported_period is None
            else resolve_event_time_window(supported_period, now=now)  # type: ignore[arg-type]
        )
        dated = (
            ()
            if window is None
            else events_starting_in_window(
                records,
                window=window,
                start_at=event_start,
                stable_key=lambda record: record.record_id,
            )
        )
    else:
        dated = upcoming_events(
            records,
            now=now,
            start_at=event_start,
            end_at=event_end,
            stable_key=lambda record: record.record_id,
            limit=20,
        )
    time_value = _constraint_value(
        interpretation, ConstraintSemanticType.TIME_OF_DAY_WINDOW
    )
    return tuple(
        record for record in dated if _matches_time_constraint(record, time_value)
    )[:20]


def _event_public_item(
    record: EventRecord, result_set: ResultSet | None
) -> PublicResultItem:
    metadata = record.metadata_json
    ordinal = None
    if result_set is not None and record.entity_id in result_set.ordered_canonical_ids:
        ordinal = result_set.ordered_canonical_ids.index(record.entity_id) + 1
    status = metadata.cancellation_status or metadata.source_status
    fields: dict[str, str | list[str] | None] = {
        "start_at": metadata.start_at,
        "end_at": metadata.end_at,
        "timezone": metadata.timezone,
        "venue": metadata.venue_name,
        "address": metadata.address,
        "organiser": metadata.organiser_name,
        "status": status,
        "category": metadata.category,
        "provenance_class": (
            "official_anu"
            if record.source_id == "events_anu_official"
            else "approved_community"
        ),
    }
    if metadata.tags is not None:
        fields["tags"] = list(metadata.tags)
    if metadata.audience is not None:
        fields["audience"] = (
            list(metadata.audience)
            if isinstance(metadata.audience, list)
            else metadata.audience
        )
    return PublicResultItem(
        record_id=record.record_id,
        source_id=record.source_id,
        canonical_id=record.entity_id,
        title=record.title,
        url=record.canonical_url,
        domain="events",
        result_set_id=result_set.result_set_id if result_set is not None else None,
        ordinal=ordinal,
        fields=fields,
    )


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

    async def answer(
        self,
        question: str,
        request_id: str,
        *,
        interpretation: QueryInterpretation | None = None,
        selected_canonical_ids: tuple[str, ...] = (),
        conversation_state: ConversationState | None = None,
        result_page: ResultPageRequest | None = None,
    ) -> AskResponse:
        now = self._now_provider()
        records = self._repository.all_events()
        by_id = {record.entity_id: record for record in records}
        resolved_page = (
            resolve_result_page(conversation_state, interpretation, result_page)
            if conversation_state is not None and interpretation is not None
            else None
        )
        continuing = bool(
            result_page is not None
            or (
                interpretation is not None
                and interpretation.intent is not None
                and interpretation.intent.operation == "continue_results"
            )
        )
        if continuing:
            if (
                resolved_page is None
                or resolved_page.result_set.domain != Domain.EVENTS
            ):
                raise ResultPageResolutionError(
                    "Event result page is stale or foreign"
                )
            start = resolved_page.start_ordinal - 1
            identities = resolved_page.result_set.ordered_canonical_ids[
                start : start + resolved_page.limit
            ]
            selected = tuple(
                by_id[identity] for identity in identities if identity in by_id
            )
            if len(selected) != len(identities):
                raise ResultPageResolutionError(
                    "Event result identity is not current approved evidence"
                )
        else:
            structured_ids = list(selected_canonical_ids)
            if (
                interpretation is not None
                and interpretation.entity is not None
                and interpretation.entity.domain == Domain.EVENTS
                and interpretation.entity.canonical_id not in structured_ids
            ):
                structured_ids.append(interpretation.entity.canonical_id)
            if structured_ids:
                selected = tuple(
                    by_id[identity]
                    for identity in structured_ids
                    if identity in by_id
                )
                if len(selected) != len(structured_ids):
                    raise ResultPageResolutionError(
                        "Selected Event is not current approved evidence"
                    )
            else:
                selected = _event_candidates(
                    records,
                    now=now,
                    interpretation=interpretation,
                    question=question,
                )[: self._limit]

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

    def integrate_conversation(
        self,
        response: AskResponse,
        *,
        question: str,
        state: ConversationState,
        interpretation: QueryInterpretation,
        result_page: ResultPageRequest | None = None,
    ) -> EventQueryOutcome:
        """Attach Events to stable shared ResultSets and typed public items."""

        records = self._repository.all_events()
        by_id = {record.entity_id: record for record in records}
        by_record_id = {record.record_id: record for record in records}
        selected = tuple(
            by_record_id[source.record_id]
            for source in response.sources
            if source.record_id in by_record_id
        )
        resolved_page = resolve_result_page(state, interpretation, result_page)
        parent = (
            resolved_page.result_set
            if resolved_page is not None
            else next(
                (
                    item
                    for item in reversed(state.result_sets)
                    if item.domain == Domain.EVENTS
                    and (
                        interpretation.referenced_result_set_id is None
                        or item.result_set_id
                        == interpretation.referenced_result_set_id
                    )
                ),
                None,
            )
        )
        listing = bool(
            resolved_page is not None
            or not interpretation.entity
            and not interpretation.requires_clarification
        )
        ordered = selected
        if listing and resolved_page is None:
            ordered = _event_candidates(
                records,
                now=self._now_provider(),
                interpretation=interpretation,
                question=question,
            )

        result_set: ResultSet | None = None
        updated = state
        if listing and resolved_page is None:
            plan = build_retrieval_plan(
                interpretation,
                plan_id=f"plan:events:{state.turn_index}",
            )
            if plan is not None:
                identities = tuple(record.entity_id for record in ordered)
                refining = bool(
                    parent is not None
                    and interpretation.explicit_constraints.items
                )
                if refining:
                    result_set = refine_result_set(
                        parent,
                        result_set_id=f"rs:events:{state.turn_index}",
                        ordered_canonical_ids=identities,
                        constraints=interpretation.constraints,
                        status=(
                            ResultSetStatus.RESULTS
                            if identities
                            else ResultSetStatus.EMPTY
                        ),
                        turn=state.turn_index,
                        originating_query=question,
                    )
                else:
                    result_set = build_result_set(
                        plan,
                        result_set_id=f"rs:events:{state.turn_index}",
                        entity_kind=EntityKind.EVENT,
                        ordered_canonical_ids=identities,
                        originating_query=question,
                        created_turn=state.turn_index,
                        population_complete=True,
                    )
                updated = remember_result_set(updated, result_set)

        active_set = result_set or (resolved_page.result_set if resolved_page else parent)
        if listing and resolved_page is None:
            selected = ordered[: self._limit]
        public_page: ResultPage | None = None
        if active_set is not None and listing and active_set.status == ResultSetStatus.RESULTS:
            start = resolved_page.start_ordinal if resolved_page is not None else 1
            public_page, continuation = result_page_metadata(
                active_set,
                start_ordinal=start,
                returned=len(selected),
            )
            updated = remember_result_page(
                updated,
                result_set_id=active_set.result_set_id,
                next_ordinal=continuation,
            )

        if len(selected) == 1:
            record = selected[0]
            updated = remember_entity(
                updated,
                ResolvedEntity(
                    domain=Domain.EVENTS,
                    kind=EntityKind.EVENT,
                    canonical_id=record.entity_id,
                    canonical_name=record.title,
                    source_record_id=record.record_id,
                    resolution_basis=EntityResolutionBasis.RETAINED_STATE,
                    mentioned_turn=state.turn_index,
                ),
                focus=active_set is None,
            )

        wants_location = LOCATION_PATTERN.search(question) is not None
        wants_organiser = ORGANISER_PATTERN.search(question) is not None
        missing_requested = bool(
            len(selected) == 1
            and (
                wants_location
                and selected[0].metadata_json.venue_name is None
                and selected[0].metadata_json.address is None
                or wants_organiser
                and selected[0].metadata_json.organiser_name is None
            )
        )
        projected = response.model_copy(
            update={
                "items": [_event_public_item(record, active_set) for record in selected],
                "sources": [_source_from_record(record) for record in selected],
                "result_page": public_page,
                "answer_state": (
                    AnswerState.UNKNOWN
                    if response.status != "ok" or missing_requested
                    else AnswerState.CONFIRMED
                ),
            }
        )
        return EventQueryOutcome(response=projected, state=updated)
