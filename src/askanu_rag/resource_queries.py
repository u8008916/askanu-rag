"""Grounded Accommodation and Support retrieval with conservative claims."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from askanu_rag.course_queries import COURSE_CODE_CANDIDATE_PATTERN, _source_from_record
from askanu_rag.models import (
    AnswerState,
    AccommodationRecord,
    AccommodationRoom,
    AskResponse,
    Clarification,
    ClarificationOption,
    ConstraintSemanticType,
    ConversationState,
    Domain,
    EntityKind,
    EntityResolutionBasis,
    EvidenceBundle,
    EvidenceItem,
    InsufficientEvidenceResponse,
    MissingEvidence,
    NeedsClarificationResponse,
    OkResponse,
    QueryInterpretation,
    PublicComparisonField,
    PublicComparisonItem,
    PublicComparisonValue,
    PublicResultItem,
    PublicRoomRateEvidence,
    ResponseAction,
    ResolvedEntity,
    ResultPage,
    ResultPageRequest,
    ResultSet,
    ResultSetStatus,
    RetrievalPlan,
    SupportRecord,
)
from askanu_rag.evidence_selection import (
    build_evidence_bundle,
    build_reasoned_evidence_bundle,
    build_result_set,
    classify_result_set_status,
)
from askanu_rag.retrieval import ResourceReader
from askanu_rag.retrieval.hybrid import SharedHybridRetriever
from askanu_rag.retrieval.repository import ResourceRecord, normalize_job_title
from askanu_rag.retrieval.semantic import (
    LocalBm25Retriever,
    sparse_score_is_usable,
)
from askanu_rag.synthesis import SynthesisError
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

ACCOMMODATION_PATTERN = re.compile(
    r"\b(?:accommodation|housing|residences?|halls?|lodges?|colleges?|rooms?|"
    r"places? to live|somewhere to live)\b",
    re.I,
)
ACCOMMODATION_INTENT_PATTERN = re.compile(
    r"\b(?:located|location|catering|catered|cost|price|rate|rent|fees?|"
    r"contract|include|inclusions?|facilities|features|amenities|overview|"
    r"accessible|accessibility|apply|application|eligible|eligibility|"
    r"who can live|undergraduate|postgraduate|vacan(?:cy|cies|t)|available|"
    r"availability|"
    r"contact|email|phone)\b",
    re.I,
)
NAMED_RESIDENCE_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*)*\s+"
    r"(?:Hall|Lodge|College|House|Residence))\b"
)
NAMED_SUPPORT_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*)*\s+"
    r"(?:Support|Service))(?:\s+service)?\b"
)
SUPPORT_PATTERN = re.compile(
    r"\b(?:support|assistance|advocacy|advocate|landlord|rent(?:al)?|"
    r"disciplinary|legal service|ANUSA|mental health|wellbeing|sexual assault|harassment|financial "
    r"difficulty|academic difficulty|enrolment|administrative help)\b",
    re.I,
)
LIVE_AVAILABILITY_PATTERN = re.compile(
    r"\b(?:live availability|(?:is there )?availability|"
    r"available (?:right )?now|rooms? available|"
    r"any (?:rooms?|spaces?) (?:left|available)|space (?:right now|at the moment)|"
    r"vacan(?:cy|cies|t)|guaranteed room|get a room .* now)\b",
    re.I,
)
COST_PATTERN = re.compile(
    r"\b(?:cost|price|rate|rent|fees?|how much|budget|under|below|less than|"
    r"max(?:imum)?|no more than|up to)\b",
    re.I,
)
FACILITIES_PATTERN = re.compile(r"\b(?:facilit(?:y|ies)|feature|amenit(?:y|ies))\b", re.I)
APPLICATION_PATTERN = re.compile(r"\b(?:apply|application)\b", re.I)
HOURS_PATTERN = re.compile(r"\b(?:hours|open|opening times?|when can)\b", re.I)
CONTACT_PATTERN = re.compile(r"\b(?:contact|phone|email|where|location)\b", re.I)
ROOM_PATTERN = re.compile(r"\b(?:rooms?|studio|apartment|occupancy)\b", re.I)
CONTRACT_PATTERN = re.compile(r"\b(?:contract|term|weeks?)\b", re.I)
INCLUSIONS_PATTERN = re.compile(r"\b(?:include|included|inclusions?)\b", re.I)
OTHER_FEES_PATTERN = re.compile(r"\b(?:other fees?|extra fees?|additional fees?)\b", re.I)
CATERING_PATTERN = re.compile(
    r"\b(?:catered|self[- ]catered|catering|meals?|meal plans?|cook for myself)\b",
    re.I,
)
LOCATION_PATTERN = re.compile(r"\b(?:where is|located|location)\b", re.I)
AUDIENCE_PATTERN = re.compile(
    r"\b(?:audience|who can live|who can use|undergraduate|postgraduate)\b", re.I
)
OVERVIEW_PATTERN = re.compile(r"\b(?:overview|describe|tell me about)\b", re.I)
RETURN_ACCOMMODATION_PATTERN = re.compile(
    r"\b(?:back|return|go back) to (?:the )?(?:accommodation|residences?)\b",
    re.I,
)
ACCESSIBILITY_PATTERN = re.compile(r"\b(?:accessibility|accessible|disability access)\b", re.I)
ELIGIBILITY_PATTERN = re.compile(r"\b(?:eligible|eligibility|who can apply)\b", re.I)
CATEGORY_PATTERN = re.compile(r"\b(?:category|type of)\b", re.I)
GUARANTEED_PRICE_PATTERN = re.compile(r"\b(?:guaranteed|fixed|final) price\b", re.I)
PURPOSE_PATTERN = re.compile(r"\b(?:purpose|what does|what help|who can help)\b", re.I)
ACCESS_PATTERN = re.compile(r"\b(?:access|appointment|book|drop[- ]?in|walk[- ]?in)\b", re.I)
TOPIC_PATTERN = re.compile(r"\b(?:topic|appeal|misconduct|tenancy|assessment)\b", re.I)
REFERRAL_PATTERN = re.compile(
    r"\b(?:referrals?|referred|external|other service)\b", re.I
)
DIAGNOSIS_PATTERN = re.compile(r"\b(?:diagnos(?:e|is)|what condition|medical advice)\b", re.I)
UNSUPPORTED_ASSURANCE_PATTERN = re.compile(
    r"\b(?:24[ /-]?7|emergency coverage|guarantee(?:d)? availability|"
    r"available (?:right )?now|response time|respond within)\b",
    re.I,
)
COMPARE_PATTERN = re.compile(r"\b(?:compare|versus|vs[.]?)\b", re.I)
BROAD_DISCOVERY_PATTERN = re.compile(
    r"^\s*(?:(?:show|list|help me find|are there)\b|"
    r"(?:what|which)\s+(?:accommodation|residences?|support|services?)\b)",
    re.I,
)
ACCOMMODATION_DISCOVERY_PATTERN = re.compile(
    r"\b(?:accommodation|residence)\s+(?:options?|choices?)\b|"
    r"\bhousing(?:\s+(?:options?|choices?))?\b|"
    r"\b(?:places? to live|somewhere to live)\b|"
    r"\boptions? for (?:living|housing)\b",
    re.I,
)
OTHER_RESOURCE_DOMAIN_PATTERN = re.compile(
    r"\b(?:courses?|programs?|majors?|minors?|speciali[sz]ations?|"
    r"prerequisites?|scholarships?|jobs?|events?)\b",
    re.I,
)
RESOURCE_UNSAFE_OUTPUT = re.compile(
    r"[<>]|(?:javascript|data):|"
    r"\b(?:ignore|override|disregard|reveal)\b|"
    r"\b(?:system|developer)\s+prompt\b|"
    r"&(?:lt|gt|#\d+|#x[0-9a-f]+);|[\x00-\x08\x0b-\x1f\x7f]",
    re.IGNORECASE,
)
RESOURCE_REFERENCE_PATTERN = re.compile(
    r"\b(?:it|its|that (?:residence|service)|this (?:residence|service)|"
    r"the same (?:residence|service)|them|their)\b",
    re.I,
)

_ROOM_WEEKLY_AUD_RATE_PATTERN = re.compile(
    r"^\s*(?:A\$\s*|AUD\s+|\$\s*)([0-9][0-9,]*(?:\.\d{1,2})?)"
    r"(?:\s*(?:/\s*week|per\s+week))?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QualifyingRoomEvidence:
    record_id: str
    name: str
    rate: str
    cost_period: str
    contract: str | None
    inclusions: str | None
    other_fees: str | None


@dataclass(frozen=True)
class AccommodationFilterOutcome:
    matched_records: tuple[ResourceRecord, ...]
    population_complete: bool
    unknown_records: tuple[ResourceRecord, ...]
    qualifying_rooms: tuple[QualifyingRoomEvidence, ...] = ()


@dataclass(frozen=True)
class ResourceQueryTrace:
    """Internal, test-visible V7 trace; never added to the public API schema."""

    question: str
    interpretation: QueryInterpretation | None
    retained_state: ConversationState
    retrieval_plan: RetrievalPlan | None
    result_set: ResultSet | None
    evidence_bundle: EvidenceBundle | None
    selected_canonical_ids: tuple[str, ...]
    canonical_sources: tuple[str, ...]
    qualifying_rooms: tuple[QualifyingRoomEvidence, ...] = ()


@dataclass(frozen=True)
class ResourceQueryOutcome:
    response: AskResponse
    state: ConversationState
    trace: ResourceQueryTrace | None = None


def _qualifying_rooms_for_result_set(
    records: tuple[ResourceRecord, ...],
    result_set: ResultSet,
) -> tuple[QualifyingRoomEvidence, ...]:
    price_limit: float | None = None
    inclusive = True
    for constraint in result_set.constraints.items:
        if constraint.semantic_type in {
            ConstraintSemanticType.MAX_PRICE,
            ConstraintSemanticType.MAX_PRICE_EXCLUSIVE,
        }:
            price_limit = float(constraint.value)
            inclusive = constraint.semantic_type == ConstraintSemanticType.MAX_PRICE
            break
    if price_limit is None:
        return ()
    qualifying: list[QualifyingRoomEvidence] = []
    for record in records:
        if not isinstance(record, AccommodationRecord):
            continue
        qualifying.extend(
            evidence
            for evidence, amount in _record_price_evidence(record)
            if (
                amount <= price_limit
                if inclusive
                else amount < price_limit
            )
        )
    return tuple(qualifying)


def _room_weekly_aud_rate(
    room: AccommodationRoom,
    *,
    cost_period: str | None,
) -> float | None:
    """Interpret the approved producer's structured weekly tariff field only."""

    if room.rate is None or cost_period is None:
        return None
    match = _ROOM_WEEKLY_AUD_RATE_PATTERN.fullmatch(room.rate)
    if match is None:
        return None
    return float(match.group(1).replace(",", ""))


def _record_price_evidence(
    record: AccommodationRecord,
) -> tuple[tuple[QualifyingRoomEvidence, float], ...]:
    """Project only named-room AUD weekly evidence; advertised_rate is excluded."""

    evidence: list[tuple[QualifyingRoomEvidence, float]] = []
    for room in record.metadata_json.rooms:
        amount = _room_weekly_aud_rate(
            room,
            cost_period=record.metadata_json.cost_period,
        )
        if amount is None:
            continue
        evidence.append(
            (
                QualifyingRoomEvidence(
                    record_id=record.record_id,
                    name=room.name,
                    rate=room.rate,
                    cost_period=record.metadata_json.cost_period,
                    contract=room.contract,
                    inclusions=room.inclusions,
                    other_fees=room.other_fees,
                ),
                amount,
            )
        )
    return tuple(evidence)


def _requested_catering_preference(question: str) -> str | None:
    normalized = normalize_job_title(question).replace(" ", "-")
    if "self-catered" in normalized or "cook-for-myself" in normalized:
        return "self-catered"
    if re.search(r"(?<!self-)\bcatered\b", normalized) or "meal-plan" in normalized:
        return "catered"
    return None


def _filter_accommodation_population(
    records: tuple[ResourceRecord, ...],
    question: str,
    interpretation: QueryInterpretation | None,
) -> AccommodationFilterOutcome:
    """Apply only hard, source-backed Accommodation filters.

    The returned completeness flag is false when at least one record cannot be
    evaluated. An empty/unknown metadata value is never treated as a negative.
    """

    candidates = tuple(
        record for record in records if isinstance(record, AccommodationRecord)
    )
    unknown: dict[str, ResourceRecord] = {}
    qualifying_rooms: list[QualifyingRoomEvidence] = []
    price_limit: float | None = None
    price_inclusive = True
    if interpretation is not None:
        for constraint in interpretation.constraints.items:
            if (
                constraint.scope.domain == Domain.ACCOMMODATION
                and constraint.semantic_type
                in {
                    ConstraintSemanticType.MAX_PRICE,
                    ConstraintSemanticType.MAX_PRICE_EXCLUSIVE,
                }
            ):
                price_limit = float(constraint.value)
                price_inclusive = (
                    constraint.semantic_type == ConstraintSemanticType.MAX_PRICE
                )
                break
    if price_limit is not None:
        matched: list[ResourceRecord] = []
        for record in candidates:
            room_evidence = _record_price_evidence(record)
            rooms_are_complete = bool(record.metadata_json.rooms) and len(
                room_evidence
            ) == len(record.metadata_json.rooms)
            qualifying = tuple(
                evidence
                for evidence, amount in room_evidence
                if (
                    amount <= price_limit
                    if price_inclusive
                    else amount < price_limit
                )
            )
            if qualifying:
                matched.append(record)
                qualifying_rooms.extend(qualifying)
            elif not rooms_are_complete:
                unknown[record.record_id] = record
        candidates = tuple(matched)

    catering = _requested_catering_preference(question)
    if catering is not None:
        matched = []
        for record in candidates:
            options = tuple(
                normalize_job_title(value).replace(" ", "-")
                for value in record.metadata_json.catering_options
            )
            if not options:
                unknown[record.record_id] = record
                continue
            if catering == "self-catered":
                is_match = any("self-catered" in value for value in options)
            else:
                is_match = any(
                    "catered" in value and "self-catered" not in value
                    for value in options
                )
            if is_match:
                matched.append(record)
        candidates = tuple(matched)

    retained_record_ids = {record.record_id for record in candidates}
    qualifying_rooms = [
        room for room in qualifying_rooms if room.record_id in retained_record_ids
    ]

    return AccommodationFilterOutcome(
        matched_records=candidates,
        population_complete=not unknown,
        unknown_records=tuple(unknown.values()),
        qualifying_rooms=tuple(qualifying_rooms),
    )


def _accommodation_field_value(
    record: AccommodationRecord, field: str
) -> str | None:
    metadata = record.metadata_json
    if field == "category":
        return metadata.category
    if field == "location":
        return metadata.location
    if field == "advertised_rate":
        return metadata.advertised_rate
    if field == "cost_period":
        return metadata.cost_period
    if field == "catering_options":
        return ", ".join(metadata.catering_options) or None
    if field == "audiences":
        return ", ".join(metadata.audiences) or None
    if field == "features":
        return ", ".join(metadata.features) or None
    if field == "overview":
        return metadata.overview
    if field == "application_text":
        return metadata.application_text
    if field == "application_url":
        return metadata.application_url
    if field == "vacancy_status":
        return metadata.vacancy_status
    if field == "rooms":
        values = [_room_context_text(room) for room in metadata.rooms]
        return "; ".join(values) or None
    return None


def _room_context_text(room: AccommodationRoom | QualifyingRoomEvidence) -> str:
    """Keep one named room's rate qualifiers and related cost context together."""

    if isinstance(room, QualifyingRoomEvidence):
        values = [
            f"{room.name} has a published room rate of {room.rate} "
            f"for the {room.cost_period} period"
        ]
        for label, value in (
            ("contract", room.contract),
            ("inclusions", room.inclusions),
            ("other fees", room.other_fees),
        ):
            if value is not None:
                values.append(f"{label}: {value}")
        return "; ".join(values)

    values = [f"Room {room.name}"]
    for label, value in (
        ("published room rate", room.rate),
        ("published cost period", getattr(room, "cost_period", None)),
        ("contract", room.contract),
        ("inclusions", room.inclusions),
        ("other fees", room.other_fees),
    ):
        if value is not None:
            values.append(f"{label}: {value}")
    return "; ".join(values)


def _trace_fields(question: str, *, discovery: bool) -> tuple[str, ...]:
    if LIVE_AVAILABILITY_PATTERN.search(question):
        # The requested fact is vacancy. A safe application action is useful
        # navigation, but it is not evidence for the vacancy answer itself.
        return ("vacancy_status",)
    if COMPARE_PATTERN.search(question):
        return (
            "category",
            "location",
            "advertised_rate",
            "cost_period",
            "catering_options",
            "audiences",
            "features",
        )
    fields: list[str] = []
    for pattern, field in (
        (COST_PATTERN, "advertised_rate"),
        (COST_PATTERN, "cost_period"),
        (COST_PATTERN, "rooms"),
        (ROOM_PATTERN, "rooms"),
        (CATERING_PATTERN, "catering_options"),
        (APPLICATION_PATTERN, "application_text"),
        (APPLICATION_PATTERN, "application_url"),
        (LOCATION_PATTERN, "location"),
        (FACILITIES_PATTERN, "features"),
        (OVERVIEW_PATTERN, "overview"),
    ):
        if pattern.search(question) and field not in fields:
            fields.append(field)
    if discovery:
        for field in ("category", "catering_options", "advertised_rate"):
            if field not in fields:
                fields.append(field)
    return tuple(fields or ("overview",))


def _evidence_item(
    record: AccommodationRecord,
    fields: tuple[str, ...],
    *,
    qualifying_rooms: tuple[QualifyingRoomEvidence, ...] = (),
) -> EvidenceItem:
    room_evidence = tuple(
        room for room in qualifying_rooms if room.record_id == record.record_id
    )
    values: list[tuple[str, str]] = []
    for field in fields:
        value = (
            "; ".join(_room_context_text(room) for room in room_evidence)
            if field == "rooms" and room_evidence
            else _accommodation_field_value(record, field)
        )
        if value is not None:
            values.append((field, value))
    selected = tuple(field for field, _ in values)
    evidence_text = "; ".join(f"{field}: {value}" for field, value in values) or record.content
    return EvidenceItem(
        record_id=record.record_id,
        source_id=record.source_id,
        domain=Domain.ACCOMMODATION,
        canonical_url=record.canonical_url,
        evidence_text=evidence_text[:4_000],
        selected_fields=selected,
    )


_PUBLIC_ACCOMMODATION_FIELDS: tuple[tuple[str, str], ...] = (
    ("category", "Category"),
    ("location", "Location"),
    ("catering_options", "Catering"),
    ("advertised_rate", "Advertised rate"),
    ("cost_period", "Cost period"),
    ("audiences", "Audiences"),
    ("features", "Features"),
)


def _public_accommodation_value(
    record: AccommodationRecord,
    field: str,
) -> str | list[str] | None:
    metadata = record.metadata_json
    if field in {"catering_options", "audiences", "features"}:
        values = list(getattr(metadata, field))
        return values or None
    value = getattr(metadata, field)
    return value


def _public_result_item(
    record: AccommodationRecord,
    result_set: ResultSet | None,
    *,
    include_fields: bool = True,
    qualifying_rooms: tuple[QualifyingRoomEvidence, ...] = (),
) -> PublicResultItem:
    ordinal: int | None = None
    if result_set is not None and record.entity_id in result_set.ordered_canonical_ids:
        ordinal = result_set.ordered_canonical_ids.index(record.entity_id) + 1
    fields = {
        field: value
        for field, _ in _PUBLIC_ACCOMMODATION_FIELDS
        if (value := _public_accommodation_value(record, field)) is not None
    }
    qualifying_room = next(
        (
            room
            for room in qualifying_rooms
            if room.record_id == record.record_id
        ),
        None,
    )
    return PublicResultItem(
        record_id=record.record_id,
        source_id=record.source_id,
        canonical_id=record.entity_id,
        title=record.title,
        url=record.canonical_url,
        domain=record.domain,
        result_set_id=result_set.result_set_id if result_set is not None else None,
        ordinal=ordinal,
        fields=fields if include_fields else {},
        qualifying_evidence=(
            PublicRoomRateEvidence(
                room_name=qualifying_room.name,
                rate=qualifying_room.rate,
                cost_period=qualifying_room.cost_period,
                contract=qualifying_room.contract,
                inclusions=qualifying_room.inclusions,
                other_fees=qualifying_room.other_fees,
            )
            if qualifying_room is not None
            else None
        ),
    )


def _public_comparison_item(
    records: tuple[AccommodationRecord, ...],
    result_set: ResultSet | None,
    *,
    qualifying_rooms: tuple[QualifyingRoomEvidence, ...] = (),
) -> PublicComparisonItem:
    return PublicComparisonItem(
        result_set_id=result_set.result_set_id if result_set is not None else None,
        records=[
            _public_result_item(
                record,
                result_set,
                include_fields=False,
                qualifying_rooms=qualifying_rooms,
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
                        value=_public_accommodation_value(record, field),
                        state=(
                            "published"
                            if _public_accommodation_value(record, field) is not None
                            else "not_published"
                        ),
                    )
                    for record in records
                ],
            )
            for field, label in _PUBLIC_ACCOMMODATION_FIELDS
        ],
    )


def _public_application_actions(
    records: tuple[AccommodationRecord, ...],
) -> list[ResponseAction]:
    return [
        ResponseAction(
            type="application",
            label="Apply now",
            url=record.metadata_json.application_url,
            record_id=record.record_id,
            source_id=record.source_id,
        )
        for record in records
        if record.metadata_json.application_url is not None
    ]


def is_plausible_resource_question(
    question: str,
    domain: Literal["accommodation", "support"],
    pending: Clarification | None = None,
    history=(),
) -> bool:
    """Cheap routing guard that performs no repository reads."""

    pattern = ACCOMMODATION_PATTERN if domain == "accommodation" else SUPPORT_PATTERN
    if domain == "support" and (
        COURSE_CODE_CANDIDATE_PATTERN.search(question)
        or OTHER_RESOURCE_DOMAIN_PATTERN.search(question)
        or ACCOMMODATION_PATTERN.search(question)
        or NAMED_RESIDENCE_PATTERN.search(question)
    ):
        # Generic support/assistance wording must never pre-empt an explicit
        # Course, Job, Scholarship or Accommodation signal.
        return False
    if domain == "support" and TOPIC_PATTERN.search(question):
        # A published Support topic supplies the domain evidence that bare
        # "help" intentionally no longer provides.
        return True
    if pattern.search(question):
        return True
    if (
        domain == "accommodation"
        and ACCOMMODATION_INTENT_PATTERN.search(question)
        and not SUPPORT_PATTERN.search(question)
        and not OTHER_RESOURCE_DOMAIN_PATTERN.search(question)
    ):
        return True
    follow_up = bool(
        CONTACT_PATTERN.search(question)
        or HOURS_PATTERN.search(question)
        or COST_PATTERN.search(question)
        or APPLICATION_PATTERN.search(question)
        or ELIGIBILITY_PATTERN.search(question)
        or ACCESS_PATTERN.search(question)
        or TOPIC_PATTERN.search(question)
        or REFERRAL_PATTERN.search(question)
        or LIVE_AVAILABILITY_PATTERN.search(question)
    )
    if follow_up and RESOURCE_REFERENCE_PATTERN.search(question):
        for turn in reversed(tuple(history)):
            if getattr(turn, "role", None) != "user":
                continue
            content = getattr(turn, "content", "")
            history_pattern = (
                ACCOMMODATION_PATTERN
                if domain == "accommodation"
                else SUPPORT_PATTERN
            )
            if history_pattern.search(content):
                return True
    pending_active = pending is not None and pending.type == f"{domain}_selection"
    if not pending_active:
        return False
    other_resource = SUPPORT_PATTERN if domain == "accommodation" else ACCOMMODATION_PATTERN
    return not bool(
        COURSE_CODE_CANDIDATE_PATTERN.search(question)
        or OTHER_RESOURCE_DOMAIN_PATTERN.search(question)
        or other_resource.search(question)
    )


def _contains_title(question: str, record: ResourceRecord) -> bool:
    return normalize_job_title(record.title) in normalize_job_title(question)


def _is_broad_resource_request(
    question: str, domain: Literal["accommodation", "support"]
) -> bool:
    normalized = normalize_job_title(question).strip(".!?")
    return bool(
        BROAD_DISCOVERY_PATTERN.search(question)
        or (
            domain == "accommodation"
            and ACCOMMODATION_DISCOVERY_PATTERN.search(question)
        )
        or normalized in {f"tell me about {domain}", domain}
    )


def _is_accommodation_discovery_request(
    question: str, interpretation: QueryInterpretation | None
) -> bool:
    normalized = normalize_job_title(question)
    if normalized in {"tell me about accommodation", "accommodation"}:
        return False
    if interpretation is not None and interpretation.intent is not None:
        if interpretation.intent.operation in {"initial_discovery", "refine_results"}:
            return True
    return bool(
        re.search(
            r"\b(?:options?|choices?|places? to live|somewhere to live|housing)\b",
            normalized,
        )
        or re.match(r"^(?:show|list|find|which)\b", normalized)
        or _requested_catering_preference(question) is not None
    )


def _resource_clarification(
    records: tuple[ResourceRecord, ...],
    request_id: str,
    domain: Literal["accommodation", "support"],
) -> NeedsClarificationResponse:
    noun = "residence" if domain == "accommodation" else "support service"
    return NeedsClarificationResponse(
        answer=f"Which {noun} do you mean?",
        clarification=Clarification(
            id=f"clar-{domain}-selection",
            type=f"{domain}_selection",
            options=[
                ClarificationOption(id=record.record_id, label=record.title)
                for record in records[:20]
            ],
            allow_multiple=domain == "accommodation",
        ),
        request_id=request_id,
    )


def _pending_resource_selection(
    question: str,
    pending: Clarification | None,
    records: tuple[ResourceRecord, ...],
    domain: Literal["accommodation", "support"],
    structured_option_ids: tuple[str, ...] = (),
) -> tuple[ResourceRecord, ...]:
    if pending is None or pending.type != f"{domain}_selection":
        return ()
    normalized = normalize_job_title(question).strip(".!?")
    selected_ids: tuple[str, ...] = structured_option_ids
    if not selected_ids:
        if (
            normalized == "both"
            and pending.allow_multiple
            and len(pending.options) == 2
        ):
            selected_ids = tuple(option.id for option in pending.options)
        elif normalized in {"first", "first one", "1"} and pending.options:
            selected_ids = (pending.options[0].id,)
        elif (
            normalized in {"second", "second one", "2"}
            and len(pending.options) > 1
        ):
            selected_ids = (pending.options[1].id,)
        else:
            for option in pending.options[:20]:
                if normalized in {
                    normalize_job_title(option.id),
                    normalize_job_title(option.label),
                }:
                    selected_ids = (option.id,)
                    break
    current_option_ids = {option.id for option in pending.options[:20]}
    if not selected_ids or not set(selected_ids).issubset(current_option_ids):
        return ()
    if len(selected_ids) > 1 and not pending.allow_multiple:
        return ()
    by_id = {record.record_id: record for record in records}
    selected = tuple(
        by_id[identifier]
        for identifier in selected_ids
        if identifier in by_id
    )
    return selected if len(selected) == len(selected_ids) else ()


def _pending_resource_intent(
    history, domain: Literal["accommodation", "support"]
) -> str | None:
    """Recover only the current session's question that created a selection."""

    for turn in reversed(tuple(history)):
        if getattr(turn, "role", None) != "user":
            continue
        content = getattr(turn, "content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        if domain == "accommodation":
            return content if (
                ACCOMMODATION_PATTERN.search(content)
                or ACCOMMODATION_INTENT_PATTERN.search(content)
                or NAMED_RESIDENCE_PATTERN.search(content)
            ) else None
        return content if (
            SUPPORT_PATTERN.search(content) or TOPIC_PATTERN.search(content)
        ) else None
    return None


class DomainResourceQueryService:
    """One domain-parameterized route over the shared resource repository."""

    def __init__(
        self,
        repository: ResourceReader,
        domain: Literal["accommodation", "support"],
        vector_retriever=None,
        *,
        sparse_retriever=None,
        top_k: int = 20,
        min_sparse_score: float = 0.2,
        max_candidates: int = 20,
        reranker=None,
        evidence_top_k: int = 5,
        rrf_k: int = 60,
    ) -> None:
        if not 1 <= top_k <= 20 or not 1 <= evidence_top_k <= 5 or not 0 < min_sparse_score <= 1:
            raise ValueError("Invalid bounded retrieval settings.")
        self.repository = repository
        self.domain = domain
        self.vector = vector_retriever
        self.sparse = sparse_retriever or LocalBm25Retriever()
        self.top_k = top_k
        self.evidence_top_k = evidence_top_k
        self.reranker = reranker
        self.min_sparse_score = min_sparse_score
        self.merger = SharedHybridRetriever(max_candidates=max_candidates, rrf_k=rrf_k)

    async def answer(
        self,
        question: str,
        request_id: str,
        pending: Clarification | None = None,
        history=(),
        *,
        resolved_domain: bool = False,
        interpretation: QueryInterpretation | None = None,
        selected_canonical_ids: tuple[str, ...] = (),
        conversation_state: ConversationState | None = None,
        clarification_option_ids: tuple[str, ...] = (),
        result_page: ResultPageRequest | None = None,
    ) -> AskResponse | None:
        pattern = ACCOMMODATION_PATTERN if self.domain == "accommodation" else SUPPORT_PATTERN
        has_domain_signal = bool(
            resolved_domain
            or pattern.search(question)
            or (self.domain == "support" and TOPIC_PATTERN.search(question))
        )
        records = self.repository.all_domain_records(self.domain)
        resolved_page = (
            resolve_result_page(
                conversation_state or ConversationState(),
                interpretation,
                result_page,
            )
            if interpretation is not None
            else None
        )
        is_continuation = bool(
            result_page is not None
            or (
                interpretation is not None
                and interpretation.intent is not None
                and interpretation.intent.operation == "continue_results"
            )
        )
        if is_continuation:
            if (
                self.domain != "accommodation"
                or resolved_page is None
                or resolved_page.result_set.domain != Domain.ACCOMMODATION
            ):
                raise ResultPageResolutionError("result page is stale or foreign")
            start = resolved_page.start_ordinal - 1
            canonical_ids = resolved_page.result_set.ordered_canonical_ids[
                start : start + resolved_page.limit
            ]
            by_entity_id = {record.entity_id: record for record in records}
            selected = tuple(
                by_entity_id[canonical_id]
                for canonical_id in canonical_ids
                if canonical_id in by_entity_id
            )
            if len(selected) != len(canonical_ids):
                raise ResultPageResolutionError(
                    "result page identity is not current approved evidence"
                )
            if not selected:
                return OkResponse(
                    answer="There are no more results in this result set.",
                    request_id=request_id,
                )
            return self._accommodation_answer(
                "Show accommodation options",
                selected,
                request_id,
                qualifying_rooms=_qualifying_rooms_for_result_set(
                    selected, resolved_page.result_set
                ),
            )
        if (
            self.domain == "accommodation"
            and interpretation is not None
            and interpretation.intent is not None
            and interpretation.intent.operation == "refine_results"
            and interpretation.referenced_result_set_id is not None
        ):
            parent = next(
                (
                    item
                    for item in (conversation_state or ConversationState()).result_sets
                    if item.result_set_id == interpretation.referenced_result_set_id
                ),
                None,
            )
            if parent is not None:
                parent_ids = set(parent.ordered_canonical_ids)
                records = tuple(
                    record for record in records if record.entity_id in parent_ids
                )
        population_complete = True
        unevaluated: tuple[ResourceRecord, ...] = ()
        qualifying_rooms: tuple[QualifyingRoomEvidence, ...] = ()
        discovery_request = bool(
            self.domain == "accommodation"
            and _is_accommodation_discovery_request(question, interpretation)
        )
        if self.domain == "accommodation" and (
            discovery_request
            or (
                interpretation is not None
                and any(
                    item.semantic_type
                    in {
                        ConstraintSemanticType.MAX_PRICE,
                        ConstraintSemanticType.MAX_PRICE_EXCLUSIVE,
                    }
                    for item in interpretation.constraints.items
                )
            )
        ):
            filter_outcome = _filter_accommodation_population(
                records, question, interpretation
            )
            records = filter_outcome.matched_records
            population_complete = filter_outcome.population_complete
            unevaluated = filter_outcome.unknown_records
            qualifying_rooms = filter_outcome.qualifying_rooms
        pending_matches = _pending_resource_selection(
            question,
            pending,
            records,
            self.domain,
            clarification_option_ids,
        )
        resolved_ids = list(selected_canonical_ids)
        if (
            interpretation is not None
            and interpretation.entity is not None
            and interpretation.entity.domain.value == self.domain
            and interpretation.entity.canonical_id not in resolved_ids
        ):
            resolved_ids.append(interpretation.entity.canonical_id)
        by_identity = {
            identity: record
            for record in records
            for identity in (record.entity_id, record.record_id)
        }
        exact = tuple(
            by_identity[identity]
            for identity in resolved_ids
            if identity in by_identity
        )
        if not exact:
            exact = tuple(record for record in records if _contains_title(question, record))
        if not exact and RESOURCE_REFERENCE_PATTERN.search(question):
            for turn in reversed(tuple(history)):
                if getattr(turn, "role", None) != "user":
                    continue
                history_matches = tuple(
                    record
                    for record in records
                    if _contains_title(getattr(turn, "content", ""), record)
                )
                if len(history_matches) == 1:
                    exact = history_matches
                    break
                if len(history_matches) > 1:
                    return _resource_clarification(
                        history_matches, request_id, self.domain
                    )
        if self.domain == "accommodation" and not exact:
            named = NAMED_RESIDENCE_PATTERN.search(question)
            if named:
                wanted = normalize_job_title(named.group(1))
                partial = tuple(
                    record
                    for record in records
                    if wanted in normalize_job_title(record.title)
                )
                if len(partial) > 1:
                    return _resource_clarification(partial, request_id, self.domain)
                if len(partial) == 1:
                    exact = partial
                else:
                    return InsufficientEvidenceResponse(
                        answer="I could not find approved stored accommodation evidence.",
                        request_id=request_id,
                    )
        if (
            self.domain == "support"
            and not exact
            and NAMED_SUPPORT_PATTERN.search(question)
        ):
            return InsufficientEvidenceResponse(
                answer="I could not find approved stored support evidence.",
                request_id=request_id,
            )
        pending_active = (
            pending is not None and pending.type == f"{self.domain}_selection"
        )
        if pending_active and not pending_matches and not exact and not has_domain_signal:
            return _resource_clarification(records, request_id, self.domain)
        if not has_domain_signal and not exact and not pending_matches:
            return None
        if len(exact) > 1 and not COMPARE_PATTERN.search(question):
            return _resource_clarification(exact, request_id, self.domain)
        if (
            not exact
            and not pending_matches
            and len(records) > 1
            and _is_broad_resource_request(question, self.domain)
            and not discovery_request
        ):
            return _resource_clarification(records, request_id, self.domain)

        selected: tuple[ResourceRecord, ...]
        if pending_matches:
            selected = pending_matches
        elif exact:
            selected = exact
        elif discovery_request:
            selected = records[:20]
        else:
            sparse_status = "ok"
            try:
                sparse_hits = self.sparse.search(
                    question,
                    records,
                    top_k=self.top_k,
                    min_score=self.min_sparse_score,
                )
            except Exception:
                sparse_hits = ()
                sparse_status = "failed"
            by_id = {record.record_id: record for record in records}
            sparse = [
                (by_id[hit.record_id], hit.score)
                for hit in sparse_hits
                if hit.record_id in by_id
                and sparse_score_is_usable(
                    self.sparse,
                    hit.score,
                    min_score=self.min_sparse_score,
                )
            ]
            semantic = []
            dense_status = "disabled"
            if self.vector is not None:
                try:
                    vector_hits = self.vector.search(
                        question,
                        domain=self.domain,
                        allowed_records=records,
                        top_k=self.top_k,
                    )
                    semantic = [
                        (by_id[hit.record.record_id], hit.score, hit.retrieval_unit_ids)
                        for hit in vector_hits
                        if hit.record.record_id in by_id
                        and math.isfinite(hit.score)
                        and 0 < hit.score <= 1
                    ]
                    dense_status = "ok"
                except Exception:
                    semantic = []
                    dense_status = "failed"
            selected = tuple(
                candidate.record
                for candidate in self.merger.select(
                    query=question,
                    sparse=sparse,
                    semantic=semantic,
                    reranker=self.reranker,
                    top_n=self.evidence_top_k,
                    sparse_status=sparse_status,
                    dense_status=dense_status,
                ).candidates
            )
        if not selected:
            if self.domain == "accommodation" and discovery_request:
                if population_complete:
                    return InsufficientEvidenceResponse(
                        answer=(
                            "No residences in the completely evaluated approved "
                            "Accommodation population match the active source-backed "
                            "constraints."
                        ),
                        sources=[_source_from_record(record) for record in records[:5]],
                        request_id=request_id,
                    )
                return InsufficientEvidenceResponse(
                    answer=(
                        "I cannot truthfully report no matches because part of the "
                        "approved Accommodation population lacks usable published "
                        "evidence for the active constraints."
                    ),
                    sources=[_source_from_record(record) for record in unevaluated[:5]],
                    request_id=request_id,
                )
            if records and _is_broad_resource_request(question, self.domain):
                return _resource_clarification(records, request_id, self.domain)
            return InsufficientEvidenceResponse(
                answer=f"I could not find approved stored {self.domain} evidence.",
                request_id=request_id,
            )

        if pending_matches:
            original_intent = _pending_resource_intent(history, self.domain)
            if original_intent is not None:
                question = original_intent
            else:
                noun = (
                    "accommodation" if self.domain == "accommodation" else "support"
                )
                question = (
                    "Tell me about "
                    + " and ".join(record.title for record in pending_matches)
                    + f" {noun}"
                )
        if self.domain == "accommodation":
            return self._accommodation_answer(
                question,
                selected[: self.evidence_top_k],
                request_id,
                qualifying_rooms=qualifying_rooms,
            )
        return self._support_answer(question, selected, request_id)

    def integrate_conversation(
        self,
        response: AskResponse,
        question: str,
        state: ConversationState,
        interpretation: QueryInterpretation,
        result_page: ResultPageRequest | None = None,
    ) -> ResourceQueryOutcome:
        """Attach Accommodation retrieval to the shared V7 state/evidence path."""

        if self.domain != "accommodation":
            return ResourceQueryOutcome(response=response, state=state)

        all_records = tuple(
            record
            for record in self.repository.all_domain_records("accommodation")
            if isinstance(record, AccommodationRecord)
        )
        by_entity_id = {record.entity_id: record for record in all_records}
        by_record_id = {record.record_id: record for record in all_records}
        resolved_page = resolve_result_page(state, interpretation, result_page)
        parent = resolved_page.result_set if resolved_page is not None else next(
            (
                item
                for item in state.result_sets
                if item.result_set_id == interpretation.referenced_result_set_id
                and item.domain == Domain.ACCOMMODATION
            ),
            None,
        )
        population = all_records
        if resolved_page is not None:
            start = resolved_page.start_ordinal - 1
            page_ids = resolved_page.result_set.ordered_canonical_ids[
                start : start + resolved_page.limit
            ]
            population = tuple(
                by_entity_id[canonical_id]
                for canonical_id in page_ids
                if canonical_id in by_entity_id
            )
        elif (
            interpretation.intent is not None
            and interpretation.intent.operation == "refine_results"
            and parent is not None
        ):
            population = tuple(
                by_entity_id[canonical_id]
                for canonical_id in parent.ordered_canonical_ids
                if canonical_id in by_entity_id
            )
        discovery = _is_accommodation_discovery_request(question, interpretation)
        if resolved_page is not None:
            matched = population
            population_complete = True
            unknown = ()
            qualifying_rooms = _qualifying_rooms_for_result_set(
                population, resolved_page.result_set
            )
        else:
            filter_outcome = _filter_accommodation_population(
                population, question, interpretation
            )
            matched = filter_outcome.matched_records
            population_complete = filter_outcome.population_complete
            unknown = filter_outcome.unknown_records
            qualifying_rooms = filter_outcome.qualifying_rooms
        price_constraint_active = any(
            item.semantic_type
            in {
                ConstraintSemanticType.MAX_PRICE,
                ConstraintSemanticType.MAX_PRICE_EXCLUSIVE,
            }
            for item in interpretation.constraints.items
        )
        response_record_ids = [source.record_id for source in response.sources]
        selected = tuple(
            by_record_id[record_id]
            for record_id in response_record_ids
            if record_id in by_record_id
        )

        plan = build_retrieval_plan(
            interpretation,
            plan_id=f"plan:accommodation:{state.turn_index}",
        )
        result_set: ResultSet | None = None
        updated = state
        if discovery and resolved_page is None and plan is not None:
            result_ids = tuple(record.entity_id for record in matched[:20])
            status = classify_result_set_status(
                result_ids, population_complete=population_complete
            )
            if (
                interpretation.intent is not None
                and interpretation.intent.operation == "refine_results"
                and parent is not None
            ):
                result_set = refine_result_set(
                    parent,
                    result_set_id=f"rs:accommodation:{state.turn_index}",
                    ordered_canonical_ids=result_ids,
                    constraints=interpretation.constraints,
                    status=status,
                    turn=state.turn_index,
                    originating_query=question,
                )
            else:
                result_set = build_result_set(
                    plan,
                    result_set_id=f"rs:accommodation:{state.turn_index}",
                    entity_kind=EntityKind.RESIDENCE,
                    ordered_canonical_ids=result_ids,
                    originating_query=question,
                    created_turn=state.turn_index,
                    population_complete=population_complete,
                )
            updated = remember_result_set(updated, result_set)

        public_page: ResultPage | None = None
        if result_set is not None and result_set.status == ResultSetStatus.RESULTS:
            public_page, continuation_ordinal = result_page_metadata(
                result_set,
                start_ordinal=1,
                returned=len(selected),
            )
            updated = remember_result_page(
                updated,
                result_set_id=result_set.result_set_id,
                next_ordinal=continuation_ordinal,
            )
        elif resolved_page is not None:
            public_page, continuation_ordinal = result_page_metadata(
                resolved_page.result_set,
                start_ordinal=resolved_page.start_ordinal,
                returned=len(selected),
            )
            updated = remember_result_page(
                updated,
                result_set_id=resolved_page.result_set.result_set_id,
                next_ordinal=continuation_ordinal,
            )

        if len(selected) == 1:
            record = selected[0]
            entity = ResolvedEntity(
                domain=Domain.ACCOMMODATION,
                kind=EntityKind.RESIDENCE,
                canonical_id=record.entity_id,
                canonical_name=record.title,
                source_record_id=record.record_id,
                resolution_basis=EntityResolutionBasis.RETAINED_STATE,
                mentioned_turn=state.turn_index,
            )
            updated = remember_entity(
                updated,
                entity,
                focus=updated.selected_result is None and result_set is None,
            )

        fields = _trace_fields(
            question, discovery=discovery or resolved_page is not None
        )
        if price_constraint_active:
            # A numeric bound is established only by named-room rate evidence.
            # Residence-level advertised wording remains available to the answer
            # for display/comparison, but cannot enter the derivation bundle.
            fields = tuple(
                field
                for field in fields
                if field not in {"advertised_rate", "cost_period"}
            )
        evidence_records = selected
        if discovery and not matched:
            evidence_records = tuple(
                record for record in population if record.record_id not in {
                    item.record_id for item in unknown
                }
            )[:20]
        evidence = tuple(
            _evidence_item(
                record,
                fields,
                qualifying_rooms=qualifying_rooms,
            )
            for record in evidence_records
        )
        if LIVE_AVAILABILITY_PATTERN.search(question):
            evidence = tuple(item for item in evidence if item.selected_fields)
        missing: list[MissingEvidence] = []
        for record in selected:
            for field in fields:
                if _accommodation_field_value(record, field) is None:
                    missing.append(MissingEvidence(field=field, reason="null"))
        if discovery and not population_complete:
            missing.append(
                MissingEvidence(
                    field="constraint_evidence", reason="incomplete_population"
                )
            )

        derived = bool(discovery or COMPARE_PATTERN.search(question))
        if plan is None:
            evidence_bundle = None
        elif evidence or missing:
            evidence_bundle = build_reasoned_evidence_bundle(
                plan,
                bundle_id=f"evidence:accommodation:{state.turn_index}",
                selected_evidence=evidence,
                missing_evidence=tuple(missing),
                derived=derived,
                result_set_id=result_set.result_set_id if result_set else None,
            )
        else:
            evidence_bundle = build_evidence_bundle(
                plan,
                bundle_id=f"evidence:accommodation:{state.turn_index}",
                missing_evidence=(
                    MissingEvidence(field="requested_fact", reason="absent"),
                ),
                answer_state=AnswerState.UNKNOWN,
                result_set_id=result_set.result_set_id if result_set else None,
            )
        trace_records = evidence_records or unknown[:20]
        trace = ResourceQueryTrace(
            question=question,
            interpretation=interpretation,
            retained_state=updated,
            retrieval_plan=plan,
            result_set=result_set,
            evidence_bundle=evidence_bundle,
            selected_canonical_ids=tuple(record.entity_id for record in selected),
            canonical_sources=tuple(str(record.canonical_url) for record in trace_records),
            qualifying_rooms=qualifying_rooms,
        )
        public_result_set = result_set or parent
        public_records = tuple(
            record
            for record in selected
            if isinstance(record, AccommodationRecord)
            and (not discovery or record in matched)
        )
        if COMPARE_PATTERN.search(question) and public_records:
            public_items = [
                _public_comparison_item(
                    public_records,
                    public_result_set,
                    qualifying_rooms=qualifying_rooms,
                )
            ]
        else:
            public_items = [
                _public_result_item(
                    record,
                    public_result_set,
                    qualifying_rooms=qualifying_rooms,
                )
                for record in public_records
            ]
        actions = (
            _public_application_actions(public_records)
            if APPLICATION_PATTERN.search(question)
            or LIVE_AVAILABILITY_PATTERN.search(question)
            else []
        )
        response = response.model_copy(
            update={
                "items": public_items,
                "actions": actions,
                "result_page": public_page,
                "answer_state": (
                    evidence_bundle.answer_state
                    if evidence_bundle is not None
                    else AnswerState.UNKNOWN
                ),
            }
        )
        return ResourceQueryOutcome(response=response, state=updated, trace=trace)

    @staticmethod
    def _safe(answer: str) -> str:
        # Resource URLs in these deterministic answers come only from already
        # validated stored fields. Continue rejecting markup, control bytes and
        # instruction-like source content without rejecting those safe links.
        if len(answer) > 5_000 or RESOURCE_UNSAFE_OUTPUT.search(answer):
            raise SynthesisError()
        return answer

    def _accommodation_answer(
        self,
        question: str,
        records: tuple[ResourceRecord, ...],
        request_id: str,
        *,
        qualifying_rooms: tuple[QualifyingRoomEvidence, ...] = (),
    ) -> AskResponse:
        accommodations = tuple(
            record for record in records if isinstance(record, AccommodationRecord)
        )
        sources = [_source_from_record(record) for record in accommodations]
        if LIVE_AVAILABILITY_PATTERN.search(question):
            known = [
                record for record in accommodations
                if record.metadata_json.vacancy_status is not None
            ]
            if len(known) != len(accommodations):
                details = []
                for record in accommodations:
                    metadata = record.metadata_json
                    if metadata.vacancy_status is not None:
                        details.append(
                            f"{record.title}: published vacancy status: "
                            f"{metadata.vacancy_status}."
                        )
                    else:
                        application = metadata.application_text
                        if metadata.application_url:
                            application = (
                                f"{application + ' ' if application else ''}"
                                f"Published application link: {metadata.application_url}."
                            )
                        details.append(
                            f"{record.title}: current live vacancy is not present in "
                            f"stored approved evidence. {application or ''}".strip()
                        )
                return InsufficientEvidenceResponse(
                    answer=self._safe(
                        "A null vacancy status means unknown, not available or "
                        "unavailable. " + " ".join(details)
                    ),
                    sources=sources,
                    request_id=request_id,
                )
            return OkResponse(
                answer=self._safe(
                    "Only explicitly published vacancy wording is reported; it is "
                    "not inferred from applications, rooms, rates, or dates. "
                    + " ".join(
                        f"{record.title}: published vacancy status: "
                        f"{record.metadata_json.vacancy_status}."
                        for record in known
                    )
                ),
                sources=sources,
                request_id=request_id,
            )

        sections: list[str] = []
        missing_fact = False
        has_specific_intent = any(
            pattern.search(question)
            for pattern in (
                COST_PATTERN,
                ROOM_PATTERN,
                CONTRACT_PATTERN,
                INCLUSIONS_PATTERN,
                OTHER_FEES_PATTERN,
                CATERING_PATTERN,
                LOCATION_PATTERN,
                AUDIENCE_PATTERN,
                FACILITIES_PATTERN,
                OVERVIEW_PATTERN,
                ACCESSIBILITY_PATTERN,
                APPLICATION_PATTERN,
                ELIGIBILITY_PATTERN,
                CATEGORY_PATTERN,
                CONTACT_PATTERN,
            )
        )
        for record in accommodations:
            metadata = record.metadata_json
            facts: list[str] = []
            if COST_PATTERN.search(question):
                if metadata.advertised_rate is None and not qualifying_rooms:
                    missing_fact = True
                elif metadata.advertised_rate is not None:
                    facts.append(
                        f"Published advertised rate wording: {metadata.advertised_rate}"
                    )
                if metadata.cost_period:
                    facts.append(f"Published cost period: {metadata.cost_period}")
            if (
                ROOM_PATTERN.search(question)
                or COST_PATTERN.search(question)
                or CONTRACT_PATTERN.search(question)
                or INCLUSIONS_PATTERN.search(question)
                or OTHER_FEES_PATTERN.search(question)
            ):
                filtered_rooms = tuple(
                    room
                    for room in qualifying_rooms
                    if room.record_id == record.record_id
                )
                matching_rooms = [
                    room for room in metadata.rooms
                    if normalize_job_title(room.name) in normalize_job_title(question)
                ]
                rooms = filtered_rooms or tuple(matching_rooms) or metadata.rooms
                if not rooms:
                    missing_fact = True
                for room in rooms:
                    if filtered_rooms:
                        # The qualifying room is the numeric evidence. Keep all
                        # related published context paired to that room even if
                        # the user only stated the price constraint.
                        facts.append(_room_context_text(room))
                        continue
                    room_facts = [f"Room {room.name}"]
                    requested_room_fact_found = False
                    for requested, label, value in (
                        (COST_PATTERN.search(question), "published rate", room.rate),
                        (CONTRACT_PATTERN.search(question), "contract", room.contract),
                        (INCLUSIONS_PATTERN.search(question), "inclusions", room.inclusions),
                        (OTHER_FEES_PATTERN.search(question), "other fees", room.other_fees),
                    ):
                        if requested:
                            if value is None:
                                missing_fact = True
                            else:
                                requested_room_fact_found = True
                                room_facts.append(f"{label}: {value}")
                    if ROOM_PATTERN.search(question) and not any(
                        pattern.search(question)
                        for pattern in (
                            COST_PATTERN,
                            CONTRACT_PATTERN,
                            INCLUSIONS_PATTERN,
                            OTHER_FEES_PATTERN,
                        )
                    ):
                        for label, value in (
                            ("published rate", room.rate),
                            ("contract", room.contract),
                            ("inclusions", room.inclusions),
                            ("other fees", room.other_fees),
                        ):
                            if value:
                                room_facts.append(f"{label}: {value}")
                    if requested_room_fact_found or len(room_facts) > 1 or ROOM_PATTERN.search(question):
                        facts.append("; ".join(room_facts))
            if FACILITIES_PATTERN.search(question):
                if metadata.features:
                    facts.append(f"Published features: {', '.join(metadata.features)}")
                else:
                    missing_fact = True
            if APPLICATION_PATTERN.search(question):
                application_facts = []
                if metadata.application_text:
                    application_facts.append(metadata.application_text)
                if metadata.application_url:
                    application_facts.append(f"Published application link: {metadata.application_url}")
                if application_facts:
                    facts.append("Published application information: " + " ".join(application_facts))
                else:
                    missing_fact = True
            if ELIGIBILITY_PATTERN.search(question):
                if metadata.eligibility:
                    facts.append(f"Published eligibility: {metadata.eligibility}")
                else:
                    missing_fact = True
            if CATEGORY_PATTERN.search(question):
                if metadata.category:
                    facts.append(f"Category: {metadata.category}")
                else:
                    missing_fact = True
            if LOCATION_PATTERN.search(question):
                if metadata.location:
                    facts.append(f"Published residence location: {metadata.location}")
                else:
                    missing_fact = True
            if CATERING_PATTERN.search(question):
                if metadata.catering_options:
                    facts.append(f"Published catering options: {', '.join(metadata.catering_options)}")
                else:
                    missing_fact = True
            if AUDIENCE_PATTERN.search(question):
                if metadata.audiences:
                    facts.append(f"Published audiences: {', '.join(metadata.audiences)}")
                else:
                    missing_fact = True
            if OVERVIEW_PATTERN.search(question):
                if metadata.overview:
                    facts.append(f"Published overview: {metadata.overview}")
                else:
                    missing_fact = True
            if ACCESSIBILITY_PATTERN.search(question):
                if metadata.accessibility:
                    facts.append(f"Published accessibility: {metadata.accessibility}")
                else:
                    missing_fact = True
            if CONTACT_PATTERN.search(question) and not LOCATION_PATTERN.search(question):
                contact_facts = [
                    f"{label}: {value}"
                    for label, value in (
                        ("email", metadata.contact.email),
                        ("phone", metadata.contact.phone),
                        ("contact location", metadata.contact.location),
                        ("contact hours", metadata.contact.hours),
                    )
                    if value
                ]
                if contact_facts:
                    facts.append("Published contact: " + "; ".join(contact_facts))
                else:
                    missing_fact = True
            if COMPARE_PATTERN.search(question):
                for label, value in (
                    ("Category", metadata.category),
                    ("Residence location", metadata.location),
                    ("Published advertised rate wording", metadata.advertised_rate),
                    ("Published cost period", metadata.cost_period),
                    (
                        "Catering",
                        ", ".join(metadata.catering_options) or None,
                    ),
                    ("Audiences", ", ".join(metadata.audiences) or None),
                    (
                        "Published features",
                        ", ".join(metadata.features) or None,
                    ),
                ):
                    facts.append(f"{label}: {value or 'not published'}")
            elif (
                OVERVIEW_PATTERN.search(question)
                or RETURN_ACCOMMODATION_PATTERN.search(question)
                or _is_broad_resource_request(question, self.domain)
            ):
                for label, value in (
                    ("Category", metadata.category),
                    ("Residence location", metadata.location),
                    ("Published advertised rate wording", metadata.advertised_rate),
                    ("Published cost period", metadata.cost_period),
                    ("Overview", metadata.overview),
                ):
                    if value:
                        facts.append(f"{label}: {value}")
                if metadata.catering_options:
                    facts.append(f"Catering: {', '.join(metadata.catering_options)}")
                if metadata.audiences:
                    facts.append(f"Audiences: {', '.join(metadata.audiences)}")
                if metadata.features:
                    facts.append(f"Published features: {', '.join(metadata.features)}")
            if facts:
                sections.append(f"{record.title}. " + "; ".join(facts) + ".")
        if not sections or missing_fact and len(accommodations) == 1:
            return InsufficientEvidenceResponse(
                answer="The stored official page does not publish the requested accommodation fact.",
                sources=sources,
                request_id=request_id,
            )
        return OkResponse(
            answer=self._safe(
                "Published rates are source wording, not a guaranteed final price, "
                "and no vacancy is inferred. " + "\n\n".join(sections)
            ),
            sources=sources,
            request_id=request_id,
        )

    def _support_answer(
        self,
        question: str,
        records: tuple[ResourceRecord, ...],
        request_id: str,
    ) -> AskResponse:
        services = tuple(record for record in records if isinstance(record, SupportRecord))
        sources = [_source_from_record(record) for record in services]
        if DIAGNOSIS_PATTERN.search(question):
            return InsufficientEvidenceResponse(
                answer=(
                    "Stored service information can route you to published support, "
                    "but it cannot diagnose a medical or mental health condition or "
                    "provide personal medical or legal advice."
                ),
                sources=sources,
                request_id=request_id,
            )

        sections: list[str] = []
        missing_requested_fact = False
        for record in services:
            metadata = record.metadata_json
            facts: list[str] = []
            if PURPOSE_PATTERN.search(question):
                if metadata.purpose:
                    facts.append(f"Published purpose: {metadata.purpose}")
                else:
                    missing_requested_fact = True
            if CATEGORY_PATTERN.search(question):
                if metadata.category:
                    facts.append(f"Category: {metadata.category}")
                else:
                    missing_requested_fact = True
            if AUDIENCE_PATTERN.search(question):
                if metadata.audiences:
                    facts.append(f"Published audiences: {', '.join(metadata.audiences)}")
                else:
                    missing_requested_fact = True
            if HOURS_PATTERN.search(question):
                if metadata.hours is None:
                    missing_requested_fact = True
                else:
                    facts.append(f"Published hours: {metadata.hours}")
            if CONTACT_PATTERN.search(question):
                contact_facts = [
                    f"{label}: {value}"
                    for label, value in (
                        ("email", metadata.contact.email),
                        ("phone", metadata.contact.phone),
                        ("location", metadata.contact.location),
                    )
                    if value
                ]
                if contact_facts:
                    facts.append("Published contact: " + "; ".join(contact_facts))
                else:
                    missing_requested_fact = True
            if ACCESS_PATTERN.search(question):
                if metadata.access:
                    facts.append(f"Published access information: {metadata.access}")
                else:
                    missing_requested_fact = True
            if COST_PATTERN.search(question):
                if metadata.cost:
                    facts.append(f"Published cost: {metadata.cost}")
                else:
                    missing_requested_fact = True
            if TOPIC_PATTERN.search(question):
                matching_topics = [
                    topic for topic in metadata.topics
                    if normalize_job_title(topic.title) in normalize_job_title(question)
                ]
                topics = matching_topics or metadata.topics
                if topics:
                    facts.extend(
                        "Published topic "
                        f"{topic.title}: {topic.description or 'no description published'} "
                        f"({topic.url})"
                        for topic in topics
                    )
                else:
                    missing_requested_fact = True
            if REFERRAL_PATTERN.search(question):
                if metadata.referrals:
                    facts.extend(
                        "Published referral navigation (not a separate support "
                        f"service): {referral.label} — {referral.url}"
                        for referral in metadata.referrals
                    )
                else:
                    missing_requested_fact = True
            if not facts and not UNSUPPORTED_ASSURANCE_PATTERN.search(question):
                for label, value in (
                    ("Category", metadata.category),
                    ("Published purpose", metadata.purpose),
                    ("Published cost", metadata.cost),
                ):
                    if value:
                        facts.append(f"{label}: {value}")
            sections.append(f"{record.title}. " + " ".join(facts))
        if UNSUPPORTED_ASSURANCE_PATTERN.search(question):
            return InsufficientEvidenceResponse(
                answer=(
                    "The stored approved service evidence does not establish 24/7 "
                    "or emergency coverage, current availability, or a response-time "
                    "guarantee. Use the published service details without assuming "
                    "those assurances."
                ),
                sources=sources,
                request_id=request_id,
            )
        if not sections or missing_requested_fact and len(services) == 1:
            return InsufficientEvidenceResponse(
                answer=(
                    "The stored approved service page does not publish the requested "
                    "fact. Missing hours, access, availability, or response details "
                    "remain unknown."
                ),
                sources=sources,
                request_id=request_id,
            )
        return OkResponse(
            answer=self._safe(
                "I can route you to published services but cannot diagnose a condition "
                "or promise professional availability. " + "\n\n".join(sections)
            ),
            sources=sources,
            request_id=request_id,
        )
