"""Grounded Accommodation and Support retrieval with conservative claims."""

from __future__ import annotations

import math
import re
from typing import Literal

from askanu_rag.course_queries import COURSE_CODE_CANDIDATE_PATTERN, _source_from_record
from askanu_rag.models import (
    AccommodationRecord,
    AskResponse,
    Clarification,
    ClarificationOption,
    InsufficientEvidenceResponse,
    NeedsClarificationResponse,
    OkResponse,
    SupportRecord,
)
from askanu_rag.retrieval import ResourceReader
from askanu_rag.retrieval.hybrid import SharedHybridRetriever
from askanu_rag.retrieval.query_expansion import expand_support_problem_query
from askanu_rag.retrieval.repository import ResourceRecord, normalize_job_title
from askanu_rag.retrieval.semantic import LocalTfidfRetriever
from askanu_rag.synthesis import SynthesisError

ACCOMMODATION_PATTERN = re.compile(
    r"\b(?:accommodation|residences?|halls?|lodges?|colleges?|rooms?)\b", re.I
)
ACCOMMODATION_INTENT_PATTERN = re.compile(
    r"\b(?:located|location|catering|catered|cost|price|rate|rent|fees?|"
    r"contract|include|inclusions?|facilities|features|amenities|overview|"
    r"accessible|accessibility|apply|application|eligible|eligibility|"
    r"who can live|undergraduate|postgraduate|vacan(?:cy|cies|t)|available|"
    r"contact|email|phone)\b",
    re.I,
)
NAMED_RESIDENCE_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*)*\s+"
    r"(?:Hall|Lodge|College|House|Residence))\b"
)
SUPPORT_PATTERN = re.compile(
    r"\b(?:support|assistance|advocacy|advocate|landlord|rent(?:al)?|"
    r"disciplinary|legal service|ANUSA|mental health|wellbeing|sexual assault|harassment|financial "
    r"difficulty|academic difficulty|enrolment|administrative help)\b",
    re.I,
)
LIVE_AVAILABILITY_PATTERN = re.compile(
    r"\b(?:live availability|available (?:right )?now|rooms? available|"
    r"vacan(?:cy|cies|t)|guaranteed room|get a room .* now)\b",
    re.I,
)
COST_PATTERN = re.compile(r"\b(?:cost|price|rate|rent|fee|how much)\b", re.I)
FACILITIES_PATTERN = re.compile(r"\b(?:facilit(?:y|ies)|feature|amenit(?:y|ies))\b", re.I)
APPLICATION_PATTERN = re.compile(r"\b(?:apply|application)\b", re.I)
HOURS_PATTERN = re.compile(r"\b(?:hours|open|opening times?|when can)\b", re.I)
CONTACT_PATTERN = re.compile(r"\b(?:contact|phone|email|where|location)\b", re.I)
ROOM_PATTERN = re.compile(r"\b(?:rooms?|studio|apartment|occupancy)\b", re.I)
CONTRACT_PATTERN = re.compile(r"\b(?:contract|term|weeks?)\b", re.I)
INCLUSIONS_PATTERN = re.compile(r"\b(?:include|included|inclusions?)\b", re.I)
OTHER_FEES_PATTERN = re.compile(r"\b(?:other fees?|extra fees?|additional fees?)\b", re.I)
CATERING_PATTERN = re.compile(r"\b(?:catered|self-catered|catering|meals?)\b", re.I)
LOCATION_PATTERN = re.compile(r"\b(?:where is|located|location)\b", re.I)
AUDIENCE_PATTERN = re.compile(
    r"\b(?:audience|who can live|who can use|undergraduate|postgraduate)\b", re.I
)
OVERVIEW_PATTERN = re.compile(r"\b(?:overview|describe|tell me about)\b", re.I)
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
        or normalized in {f"tell me about {domain}", domain}
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
) -> tuple[ResourceRecord, ...]:
    if pending is None or pending.type != f"{domain}_selection":
        return ()
    normalized = normalize_job_title(question).strip(".!?")
    selected_id = None
    if normalized in {"first", "first one", "1"} and pending.options:
        selected_id = pending.options[0].id
    elif normalized in {"second", "second one", "2"} and len(pending.options) > 1:
        selected_id = pending.options[1].id
    else:
        for option in pending.options[:20]:
            if normalized in {
                normalize_job_title(option.id),
                normalize_job_title(option.label),
            }:
                selected_id = option.id
                break
    by_id = {record.record_id: record for record in records}
    selected = by_id.get(selected_id) if selected_id else None
    return (selected,) if selected is not None else ()


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
        top_k: int = 5,
        min_sparse_score: float = 0.2,
        max_candidates: int = 10,
    ) -> None:
        self.repository = repository
        self.domain = domain
        self.vector = vector_retriever
        self.sparse = sparse_retriever or LocalTfidfRetriever()
        self.top_k = top_k
        self.min_sparse_score = min_sparse_score
        self.merger = SharedHybridRetriever(max_candidates=max_candidates)

    async def answer(
        self,
        question: str,
        request_id: str,
        pending: Clarification | None = None,
        history=(),
        *,
        resolved_domain: bool = False,
    ) -> AskResponse | None:
        pattern = ACCOMMODATION_PATTERN if self.domain == "accommodation" else SUPPORT_PATTERN
        has_domain_signal = bool(
            resolved_domain
            or pattern.search(question)
            or (self.domain == "support" and TOPIC_PATTERN.search(question))
        )
        records = self.repository.all_domain_records(self.domain)
        pending_matches = _pending_resource_selection(
            question, pending, records, self.domain
        )
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
        ):
            return _resource_clarification(records, request_id, self.domain)

        selected: tuple[ResourceRecord, ...]
        if pending_matches:
            selected = pending_matches
        elif exact:
            selected = exact
        else:
            ranking_query = (
                expand_support_problem_query(question)
                if self.domain == "support"
                else question
            )
            sparse_hits = self.sparse.search(
                ranking_query,
                records,
                top_k=self.top_k,
                min_score=self.min_sparse_score,
            )
            by_id = {record.record_id: record for record in records}
            sparse = [
                (by_id[hit.record_id], hit.score)
                for hit in sparse_hits
                if hit.record_id in by_id
            ]
            semantic = []
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
                except Exception:
                    semantic = []
            selected = tuple(
                candidate.record
                for candidate in self.merger.merge(sparse=sparse, semantic=semantic)
            )
        if not selected:
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
            return self._accommodation_answer(question, selected, request_id)
        return self._support_answer(question, selected, request_id)

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
                if metadata.advertised_rate is None:
                    missing_fact = True
                else:
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
                matching_rooms = [
                    room for room in metadata.rooms
                    if normalize_job_title(room.name) in normalize_job_title(question)
                ]
                rooms = matching_rooms or metadata.rooms
                if not rooms:
                    missing_fact = True
                for room in rooms:
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
            if (
                COMPARE_PATTERN.search(question)
                or OVERVIEW_PATTERN.search(question)
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
