"""Shared typed presentation for Course and Scholarship student journeys.

Retrieval services select approved records.  This module only projects those
records into the existing public ResultSet/result/comparison contracts; it does
not rank candidates or treat client state as evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from askanu_rag.models import (
    AnswerState,
    AskResponse,
    ConversationState,
    CourseProgramRecord,
    Domain,
    EntityKind,
    EntityResolutionBasis,
    PublicComparisonField,
    PublicComparisonItem,
    PublicComparisonValue,
    PublicResultItem,
    QueryInterpretation,
    ResolvedEntity,
    ResultSet,
    ScholarshipRecord,
)
from askanu_rag.evidence_selection import build_result_set
from askanu_rag.retrieval.catalog import record_code
from askanu_rag.retrieval_planning import build_retrieval_plan
from askanu_rag.state_transitions import (
    remember_entity,
    remember_result_set,
    set_pending_clarification,
)

JourneyRecord = CourseProgramRecord | ScholarshipRecord
PublicValue = str | list[str] | None
FieldProjector = Callable[[JourneyRecord, str], PublicValue]

COURSE_PUBLIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("entity_type", "Entity type"),
    ("code", "Code"),
    ("academic_year", "Academic year"),
    ("units", "Units"),
    ("description", "Description"),
    ("prerequisites", "Prerequisites"),
    ("corequisites", "Corequisites"),
    ("incompatibilities", "Incompatibilities"),
    ("assumed_knowledge", "Assumed knowledge"),
    ("offerings", "Offerings"),
)

SCHOLARSHIP_PUBLIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("status", "Official status"),
    ("featured", "Featured"),
    ("application_required", "Application required"),
    ("study_stage", "Study stage"),
    ("student_type", "Student type"),
    ("study_level", "Study level"),
    ("area_of_study", "Area of study"),
    ("value", "Value"),
    ("selection_basis", "Selection basis"),
    ("opening_date", "Opening date"),
    ("closing_date", "Closing date"),
    ("eligibility", "Published eligibility criteria"),
)


def canonical_id(record: JourneyRecord) -> str:
    if isinstance(record, ScholarshipRecord):
        return record.entity_id
    return record_code(record)


def course_field(record: JourneyRecord, field: str) -> PublicValue:
    if not isinstance(record, CourseProgramRecord):
        raise TypeError("Course projection requires a Course-family record")
    metadata = record.metadata_json
    if field == "entity_type":
        return metadata.entity_type
    if field == "code":
        return record_code(record)
    if field == "description":
        return metadata.description or record.content
    if field == "offerings":
        offerings = getattr(metadata, "offerings", None)
        if not offerings:
            return None
        rendered = [
            "; ".join(
                value
                for value in (
                    item.get("session"),
                    item.get("mode"),
                )
                if isinstance(value, str) and value.strip()
            )
            for item in offerings
        ]
        clean = [value for value in rendered if value]
        return clean or None
    value = getattr(metadata, field, None)
    if isinstance(value, tuple):
        return list(value) or None
    return value


def scholarship_field(record: JourneyRecord, field: str) -> PublicValue:
    if not isinstance(record, ScholarshipRecord):
        raise TypeError("Scholarship projection requires a Scholarship record")
    value = getattr(record.metadata_json, field)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, tuple):
        return list(value) or None
    if isinstance(value, list):
        return value or None
    return value


def public_result_item(
    record: JourneyRecord,
    result_set: ResultSet | None,
    *,
    fields: Sequence[tuple[str, str]],
    projector: FieldProjector,
    include_fields: bool = True,
) -> PublicResultItem:
    identity = canonical_id(record)
    ordinal = None
    if result_set is not None and identity in result_set.ordered_canonical_ids:
        ordinal = result_set.ordered_canonical_ids.index(identity) + 1
    projected = {
        field: value
        for field, _label in fields
        if (value := projector(record, field)) is not None
    }
    return PublicResultItem(
        record_id=record.record_id,
        source_id=record.source_id,
        canonical_id=identity,
        title=record.title,
        url=record.canonical_url,
        domain=record.domain,
        result_set_id=result_set.result_set_id if result_set is not None else None,
        ordinal=ordinal,
        fields=projected if include_fields else {},
    )


def public_comparison_item(
    records: Sequence[JourneyRecord],
    result_set: ResultSet | None,
    *,
    fields: Sequence[tuple[str, str]],
    projector: FieldProjector,
) -> PublicComparisonItem:
    return PublicComparisonItem(
        result_set_id=result_set.result_set_id if result_set is not None else None,
        records=[
            public_result_item(
                record,
                result_set,
                fields=fields,
                projector=projector,
                include_fields=False,
            )
            for record in records
        ],
        fields=[
            PublicComparisonField(
                name=field,
                label=label,
                values=[
                    PublicComparisonValue(
                        record_id=record.record_id,
                        value=projector(record, field),
                        state=(
                            "published"
                            if projector(record, field) is not None
                            else "not_published"
                        ),
                    )
                    for record in records
                ],
            )
            for field, label in fields
        ],
    )


def comparison_has_missing_values(
    records: Sequence[JourneyRecord],
    *,
    fields: Sequence[tuple[str, str]],
    projector: FieldProjector,
) -> bool:
    return any(
        projector(record, field) is None
        for record in records
        for field, _label in fields
    )


@dataclass(frozen=True)
class JourneyPresentationOutcome:
    response: AskResponse
    state: ConversationState


def integrate_course_presentation(
    response: AskResponse,
    records: Sequence[CourseProgramRecord],
    *,
    question: str,
    state: ConversationState,
    interpretation: QueryInterpretation,
) -> JourneyPresentationOutcome:
    """Attach approved Course records to shared state and typed public items."""

    selected = tuple(records)
    if not selected:
        return JourneyPresentationOutcome(response=response, state=state)

    updated = state
    comparing = bool(
        interpretation.intent is not None
        and interpretation.intent.name == "compare"
        and len(selected) > 1
    )
    result_set = None
    if comparing:
        plan = build_retrieval_plan(
            interpretation,
            plan_id=f"plan:courses:{state.turn_index}",
        )
        if plan is not None:
            result_set = build_result_set(
                plan,
                result_set_id=f"rs:courses:{state.turn_index}",
                entity_kind=EntityKind.COURSE,
                ordered_canonical_ids=tuple(record_code(record) for record in selected),
                originating_query=question,
                created_turn=state.turn_index,
                population_complete=True,
            )
            updated = remember_result_set(updated, result_set)
            # Multiple explicit comparison targets are not an unresolved
            # singular reference; a successful backend-authored comparison
            # completes the orchestrator's temporary ambiguity.
            updated = set_pending_clarification(updated, None)

    for record in selected:
        retained = next(
            (
                entity
                for entity in updated.recent_entities
                if entity.kind == EntityKind.COURSE
                and entity.canonical_id == record_code(record)
            ),
            None,
        )
        entity = ResolvedEntity(
            domain=Domain.COURSES,
            kind=EntityKind.COURSE,
            canonical_id=record_code(record),
            canonical_name=record.title,
            source_record_id=record.record_id,
            resolution_basis=(
                retained.resolution_basis
                if retained is not None
                else EntityResolutionBasis.RETAINED_STATE
            ),
            mentioned_turn=state.turn_index,
        )
        updated = remember_entity(
            updated,
            entity,
            focus=not comparing and len(selected) == 1,
        )

    if comparing:
        items = [
            public_comparison_item(
                selected,
                result_set,
                fields=COURSE_PUBLIC_FIELDS,
                projector=course_field,
            )
        ]
    else:
        items = [
            public_result_item(
                record,
                result_set,
                fields=COURSE_PUBLIC_FIELDS,
                projector=course_field,
            )
            for record in selected
        ]

    answer_state = (
        AnswerState.PARTIAL
        if comparing
        and comparison_has_missing_values(
            selected,
            fields=COURSE_PUBLIC_FIELDS,
            projector=course_field,
        )
        else AnswerState.CONFIRMED
        if response.status == "ok"
        else AnswerState.UNKNOWN
    )
    return JourneyPresentationOutcome(
        response=response.model_copy(
            update={"items": items, "answer_state": answer_state}
        ),
        state=updated,
    )
