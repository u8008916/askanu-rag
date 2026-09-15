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
from askanu_rag.retrieval.repository import ResourceRecord, normalize_job_title
from askanu_rag.retrieval.semantic import LocalTfidfRetriever
from askanu_rag.synthesis import SynthesisError, UNSAFE_EVIDENCE

ACCOMMODATION_PATTERN = re.compile(
    r"\b(?:accommodation|residences?|halls?|lodges?|colleges?|rooms?)\b", re.I
)
SUPPORT_PATTERN = re.compile(
    r"\b(?:support|assistance|advocacy|advocate|landlord|rent(?:al)?|"
    r"disciplinary|legal service|ANUSA|mental health|wellbeing|sexual assault|harassment|financial "
    r"difficulty|academic difficulty|enrolment|administrative help)\b",
    re.I,
)
LIVE_AVAILABILITY_PATTERN = re.compile(
    r"\b(?:live availability|available now|vacan(?:cy|cies|t)|guaranteed room)\b",
    re.I,
)
COST_PATTERN = re.compile(r"\b(?:cost|price|rate|rent|fee|how much)\b", re.I)
FACILITIES_PATTERN = re.compile(r"\b(?:facilit(?:y|ies)|feature|amenit(?:y|ies))\b", re.I)
APPLICATION_PATTERN = re.compile(r"\b(?:apply|application)\b", re.I)
HOURS_PATTERN = re.compile(r"\b(?:hours|open|opening times?|when can)\b", re.I)
CONTACT_PATTERN = re.compile(r"\b(?:contact|phone|email|where|location)\b", re.I)
COMPARE_PATTERN = re.compile(r"\b(?:compare|versus|vs[.]?)\b", re.I)
BROAD_DISCOVERY_PATTERN = re.compile(
    r"^\s*(?:what|which|show|list|help me find|are there)\b", re.I
)
OTHER_RESOURCE_DOMAIN_PATTERN = re.compile(
    r"\b(?:courses?|programs?|majors?|minors?|speciali[sz]ations?|"
    r"prerequisites?|scholarships?|jobs?|events?)\b",
    re.I,
)


def is_plausible_resource_question(
    question: str,
    domain: Literal["accommodation", "support"],
    pending: Clarification | None = None,
) -> bool:
    """Cheap routing guard that performs no repository reads."""

    pattern = ACCOMMODATION_PATTERN if domain == "accommodation" else SUPPORT_PATTERN
    if pattern.search(question):
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
    ) -> AskResponse | None:
        pattern = ACCOMMODATION_PATTERN if self.domain == "accommodation" else SUPPORT_PATTERN
        records = self.repository.all_domain_records(self.domain)
        pending_matches = _pending_resource_selection(
            question, pending, records, self.domain
        )
        exact = tuple(record for record in records if _contains_title(question, record))
        pending_active = (
            pending is not None and pending.type == f"{self.domain}_selection"
        )
        if pending_active and not pending_matches and not exact and not pattern.search(question):
            return _resource_clarification(records, request_id, self.domain)
        if not pattern.search(question) and not exact and not pending_matches:
            return None
        if len(exact) > 1 and not COMPARE_PATTERN.search(question):
            return _resource_clarification(exact, request_id, self.domain)

        selected: tuple[ResourceRecord, ...]
        if pending_matches:
            selected = pending_matches
        elif exact:
            selected = exact
        else:
            sparse_hits = self.sparse.search(
                question,
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

        if self.domain == "accommodation":
            return self._accommodation_answer(question, selected, request_id)
        return self._support_answer(question, selected, request_id)

    @staticmethod
    def _safe(answer: str) -> str:
        if len(answer) > 5_000 or UNSAFE_EVIDENCE.search(answer):
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
            details = [
                f"{record.title}: {record.metadata_json.application_information}"
                for record in accommodations
                if record.metadata_json.application_information
            ]
            suffix = " " + " ".join(details) if details else ""
            return InsufficientEvidenceResponse(
                answer=self._safe(
                    "Stored accommodation pages do not establish live vacancy or "
                    "guarantee a room. Check the official source for current "
                    f"application information.{suffix}"
                ),
                sources=sources,
                request_id=request_id,
            )

        sections = []
        missing_fact = False
        for record in accommodations:
            metadata = record.metadata_json
            facts = []
            if COST_PATTERN.search(question):
                if metadata.advertised_rate is None:
                    missing_fact = True
                else:
                    facts.append(
                        f"Published advertised rate wording: {metadata.advertised_rate}"
                    )
                    if metadata.rate_inclusions:
                        facts.append(f"Published inclusions: {', '.join(metadata.rate_inclusions)}")
                    if metadata.rate_exclusions:
                        facts.append(f"Published exclusions: {', '.join(metadata.rate_exclusions)}")
            elif FACILITIES_PATTERN.search(question):
                if metadata.facilities:
                    facts.append(f"Published facilities: {', '.join(metadata.facilities)}")
                else:
                    missing_fact = True
            elif APPLICATION_PATTERN.search(question):
                if metadata.application_information:
                    facts.append(
                        f"Published application information: {metadata.application_information}"
                    )
                else:
                    missing_fact = True
            else:
                for label, value in (
                    ("Type", metadata.accommodation_type),
                    ("Location", metadata.location),
                    ("Catering", metadata.catering),
                    ("Contract/term", metadata.contract_term),
                ):
                    if value:
                        facts.append(f"{label}: {value}")
                if metadata.facilities:
                    facts.append(f"Published facilities: {', '.join(metadata.facilities)}")
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
                "Published accommodation information is not live vacancy or a "
                "guaranteed price. " + "\n\n".join(sections)
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
        sections = []
        missing_requested_fact = False
        for record in services:
            metadata = record.metadata_json
            facts = [record.content]
            if HOURS_PATTERN.search(question):
                if metadata.hours is None:
                    missing_requested_fact = True
                else:
                    facts.append(f"Published hours: {metadata.hours}")
            if CONTACT_PATTERN.search(question):
                if metadata.contact:
                    facts.append(f"Published contact: {metadata.contact}")
                if metadata.location:
                    facts.append(f"Published location: {metadata.location}")
                if metadata.contact is None and metadata.location is None:
                    missing_requested_fact = True
            if metadata.access_instructions:
                facts.append(f"Published access information: {metadata.access_instructions}")
            sections.append(f"{record.title}. " + " ".join(facts))
        if not sections or missing_requested_fact and len(services) == 1:
            return InsufficientEvidenceResponse(
                answer=(
                    "The stored approved service page does not publish the requested "
                    "contact, location, or hours."
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
