"""Deterministic, source-grounded Scholarship retrieval for Day 9."""

import math
import re

from askanu_rag.course_queries import (
    COURSE_CODE_CANDIDATE_PATTERN,
    _source_from_record,
)
from askanu_rag.models import (
    AskResponse,
    Clarification,
    ClarificationOption,
    InsufficientEvidenceResponse,
    NeedsClarificationResponse,
    OkResponse,
    ScholarshipRecord,
)
from askanu_rag.retrieval import ScholarshipReader
from askanu_rag.retrieval.hybrid import SharedHybridRetriever
from askanu_rag.synthesis import SynthesisError, UNSAFE_EVIDENCE

SCHOLARSHIP_PATTERN = re.compile(r"\bscholarships?\b", re.IGNORECASE)
ELIGIBILITY_PATTERN = re.compile(
    r"\b(?:am i|eligible|eligibility|qualify|qualification)\b", re.IGNORECASE
)
FILTER_FIELDS = ("study_stage", "student_type", "study_level", "area_of_study")
UNDERGRADUATE_STUDY_LEVELS = frozenset({"undergraduate", "bachelor"})
UNDERGRADUATE_QUERY_TERMS = ("undergraduate", "undergraduates", "bachelor")
OTHER_DOMAIN_PATTERN = re.compile(
    r"\b(?:courses?|programs?|prerequisites?|requisites?|jobs?|events?|"
    r"accommodation)\b",
    re.IGNORECASE,
)
SEMANTIC_DISCOVERY_PATTERN = re.compile(
    r"\b(?:related\s+to|interested\s+in|focus(?:ed)?\s+on|about)\b",
    re.IGNORECASE,
)
SCHOLARSHIP_FACT_LABELS = {
    "featured": "Featured",
    "application_required": "Application required",
    "study_stage": "Study stage",
    "student_type": "Student type",
    "study_level": "Study level",
    "area_of_study": "Area of study",
    "value": "Value",
    "selection_basis": "Selection basis",
    "opening_date": "Opening date",
    "closing_date": "Closing date",
    "status": "Official status",
}


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def is_plausible_scholarship_question(
    question: str, pending: Clarification | None = None
) -> bool:
    """Cheap routing guard that performs no repository reads."""

    if SCHOLARSHIP_PATTERN.search(question):
        return True
    pending_scope = pending is not None and (
        pending.id == "clar-scholarship-scope"
        or pending.type == "scholarship_selection"
    )
    return bool(
        pending_scope
        and not COURSE_CODE_CANDIDATE_PATTERN.search(question)
        and not OTHER_DOMAIN_PATTERN.search(question)
    )


def _contains_phrase(question: str, value: str) -> bool:
    normalized = _normalize(question)
    phrase = _normalize(value)
    return bool(phrase) and re.search(
        r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", normalized
    ) is not None


def _requested_fact(question: str) -> str | None:
    """Return one explicit frozen Scholarship fact intent, most specific first."""

    patterns = (
        ("opening_date", r"\bopening date\b|\bwhen\b.+\bopen(?:s)?\b"),
        ("closing_date", r"\bclosing date\b|\bwhen\b.+\bclos(?:e|es)\b"),
        (
            "application_required",
            r"\bapplication required\b|\b(?:require(?:s|d)?|need)\b.+\bapplication\b",
        ),
        ("selection_basis", r"\bselection basis\b|\bselection criteria\b"),
        ("student_type", r"\bstudent type\b|\b(?:international|domestic) students?\b"),
        ("study_stage", r"\bstudy stage\b|\b(?:future|current) students?\b"),
        ("featured", r"\bfeatured\b"),
        ("study_level", r"\bstudy level\b"),
        ("area_of_study", r"\barea of study\b"),
        ("value", r"\b(?:value|worth)\b|\bhow much\b"),
        ("status", r"\bofficial status\b|\bscholarship status\b"),
    )
    return next(
        (field for field, pattern in patterns if re.search(pattern, question, re.I)),
        None,
    )


def _fact_response(
    record: ScholarshipRecord, fact: str, request_id: str
) -> AskResponse:
    """Project exactly one stored fact without substituting unrelated metadata."""

    value = getattr(record.metadata_json, fact)
    label = SCHOLARSHIP_FACT_LABELS[fact]
    if value is None or value == []:
        return InsufficientEvidenceResponse(
            answer=(
                f"The stored Scholarship record does not contain source-backed "
                f"{label.casefold()} information for {record.title}."
            ),
            sources=[_source_from_record(record)],
            request_id=request_id,
        )
    if isinstance(value, bool):
        rendered = "yes" if value else "no"
    elif isinstance(value, list):
        rendered = ", ".join(value)
    else:
        rendered = str(value)
    answer = f"{record.title}. {label}: {rendered}."
    if len(answer) > 3000 or UNSAFE_EVIDENCE.search(answer):
        raise SynthesisError()
    return OkResponse(
        answer=answer,
        sources=[_source_from_record(record)],
        request_id=request_id,
    )


def _filter_value(field: str, value: str) -> str:
    """Normalize only the frozen Undergraduate/Bachelor study-level wording."""

    normalized = _normalize(value)
    if field == "study_level" and normalized in UNDERGRADUATE_STUDY_LEVELS:
        return "undergraduate"
    return normalized


def _filter_value_is_explicit(question: str, field: str, value: str) -> bool:
    if _contains_phrase(question, value):
        return True
    return (
        field == "study_level"
        and _filter_value(field, value) == "undergraduate"
        and any(
            _contains_phrase(question, alias)
            for alias in UNDERGRADUATE_QUERY_TERMS
        )
    )


def _identity_matches(
    question: str, records: tuple[ScholarshipRecord, ...]
) -> tuple[ScholarshipRecord, ...]:
    normalized = _normalize(question)
    matches = []
    for record in records:
        title = _normalize(record.title)
        slug_words = _normalize(record.entity_id.replace("-", " "))
        if title == normalized or _contains_phrase(normalized, title):
            matches.append(record)
        elif record.entity_id.casefold() in question.casefold() or (
            len(slug_words) >= 8 and _contains_phrase(normalized, slug_words)
        ):
            matches.append(record)
    return tuple(matches)


def _explicit_filters(
    question: str,
    records: tuple[ScholarshipRecord, ...],
    *,
    scope_refinement: bool = False,
) -> dict[str, object]:
    filters: dict[str, object] = {}
    normalized = _normalize(question)
    if re.search(r"\bfeatured\b", normalized):
        filters["featured"] = True
    if re.search(r"\bopen\b", normalized):
        filters["status"] = "open"
    elif re.search(r"\bclosed\b", normalized):
        filters["status"] = "closed"
    if not scope_refinement and re.search(r"\bapplication required\b", normalized):
        filters["application_required"] = True

    for field in FILTER_FIELDS:
        known_values = {
            value
            for record in records
            for value in getattr(record.metadata_json, field)
            if value.strip()
        }
        selected = tuple(
            sorted(
                value
                for value in known_values
                if _filter_value_is_explicit(question, field, value)
            )
        )
        if selected:
            filters[field] = selected
    return filters


def _matches_filters(record: ScholarshipRecord, filters: dict[str, object]) -> bool:
    metadata = record.metadata_json
    for field, expected in filters.items():
        actual = getattr(metadata, field)
        if field in FILTER_FIELDS:
            actual_values = {_filter_value(field, value) for value in actual}
            if not all(
                _filter_value(field, value) in actual_values for value in expected
            ):
                return False
        elif field == "status":
            if not isinstance(actual, str) or _normalize(actual) != expected:
                return False
        elif actual is not expected:
            return False
    return True


def _clarification(
    records: tuple[ScholarshipRecord, ...], request_id: str, answer: str
) -> NeedsClarificationResponse:
    return NeedsClarificationResponse(
        answer=answer,
        clarification=Clarification(
            id="clar-scholarship-scope",
            type="scholarship_selection",
            options=[
                ClarificationOption(
                    id=record.record_id,
                    label=f"{record.title} — {record.entity_id}",
                )
                for record in records[:20]
            ],
            allow_multiple=False,
        ),
        request_id=request_id,
    )


def _pending_selection(
    question: str,
    records: tuple[ScholarshipRecord, ...],
    pending: Clarification | None,
) -> tuple[ScholarshipRecord, ...]:
    if pending is None or pending.id != "clar-scholarship-scope":
        return ()
    by_id = {record.record_id: record for record in records}
    normalized = _normalize(question)
    selected_id = None
    if normalized == "first" and pending.options:
        selected_id = pending.options[0].id
    elif normalized == "second" and len(pending.options) > 1:
        selected_id = pending.options[1].id
    else:
        for option in pending.options:
            if normalized in {_normalize(option.label), _normalize(option.id)}:
                selected_id = option.id
                break
    selected = by_id.get(selected_id) if selected_id is not None else None
    return (selected,) if selected is not None else ()


def _answer(records: tuple[ScholarshipRecord, ...], *, eligibility: bool) -> str:
    sections = []
    for record in records:
        metadata = record.metadata_json
        facts = []
        if metadata.status is not None:
            facts.append(f"Official status: {metadata.status}")
        if metadata.study_level:
            facts.append(f"Study level: {', '.join(metadata.study_level)}")
        if metadata.area_of_study:
            facts.append(f"Area of study: {', '.join(metadata.area_of_study)}")
        if metadata.value is not None:
            facts.append(f"Value: {metadata.value}")
        if metadata.closing_date is not None:
            facts.append(f"Closing date: {metadata.closing_date}")
        if eligibility and metadata.eligibility is not None:
            facts.append(f"Official eligibility information: {metadata.eligibility}")
        detail = "; ".join(facts) if facts else "No requested filter facts are stored."
        section = f"{record.title}. {detail}"
        if len(section) > 3000 or UNSAFE_EVIDENCE.search(section):
            raise SynthesisError()
        sections.append(section)
    prefix = ""
    if eligibility:
        prefix = (
            "I can show official requirements, but I cannot determine your personal "
            "eligibility. "
        )
    return prefix + "\n\n".join(sections)


class ScholarshipQueryService:
    """Answer only bounded Scholarship identity and metadata-filter queries."""

    def __init__(
        self,
        repository: ScholarshipReader,
        vector_retriever=None,
        *,
        max_candidates: int = 10,
    ) -> None:
        self._repository = repository
        self._vector = vector_retriever
        self._merger = SharedHybridRetriever(max_candidates=max_candidates)

    async def answer(
        self,
        question: str,
        request_id: str,
        pending: Clarification | None = None,
    ) -> AskResponse | None:
        records = self._repository.all_scholarships()
        selected_pending = _pending_selection(question, records, pending)
        pending_scope = pending is not None and pending.id == "clar-scholarship-scope"
        identities = _identity_matches(question, records)
        filters = _explicit_filters(
            question,
            records,
            scope_refinement=pending_scope,
        )
        if (
            not SCHOLARSHIP_PATTERN.search(question)
            and not identities
            and not selected_pending
            and not pending_scope
        ):
            return None

        if (
            pending_scope
            and not selected_pending
            and not SCHOLARSHIP_PATTERN.search(question)
            and (
                COURSE_CODE_CANDIDATE_PATTERN.search(question)
                or OTHER_DOMAIN_PATTERN.search(question)
            )
        ):
            return None

        eligibility = ELIGIBILITY_PATTERN.search(question) is not None
        requested_fact = _requested_fact(question)
        semantic_intent = SEMANTIC_DISCOVERY_PATTERN.search(question) is not None
        if selected_pending:
            selected = selected_pending
        elif len(identities) > 1:
            return _clarification(
                identities,
                request_id,
                "Which scholarship do you mean?",
            )
        elif len(identities) == 1:
            selected = identities
        else:
            if not filters and not (semantic_intent and self._vector is not None):
                return _clarification(
                    records,
                    request_id,
                    "Which scholarship, study level, or area of study do you mean?",
                )
            matches = tuple(
                record for record in records if _matches_filters(record, filters)
            )
            if semantic_intent and self._vector is not None:
                try:
                    vector_hits = self._vector.search(
                        question,
                        domain="scholarships",
                        allowed_records=matches,
                    )
                except Exception:
                    vector_hits = ()
                by_id = {record.record_id: record for record in matches}
                selected = tuple(
                    candidate.record
                    for candidate in self._merger.merge(
                        semantic=(
                            (
                                by_id[hit.record.record_id],
                                hit.score,
                                hit.retrieval_unit_ids,
                            )
                            for hit in vector_hits
                            if hit.record.record_id in by_id
                            and math.isfinite(hit.score)
                            and 0 < hit.score <= 1
                        )
                    )
                )
                if not selected:
                    return InsufficientEvidenceResponse(
                        answer=(
                            "I could not find sufficiently relevant stored Scholarship "
                            "evidence matching the requested hard filters."
                        ),
                        request_id=request_id,
                    )
            else:
                selected = matches
            limit = (
                9
                if filters.get("featured") is True
                and filters.get("status") == "open"
                else 20
            )
            selected = selected[:limit]

        if not selected:
            return InsufficientEvidenceResponse(
                answer=(
                    "I could not find stored Scholarship evidence matching all "
                    "requested source-supported filters."
                ),
                request_id=request_id,
            )
        if requested_fact is not None and not eligibility and (
            selected_pending or identities
        ):
            return _fact_response(selected[0], requested_fact, request_id)
        return OkResponse(
            answer=_answer(selected, eligibility=eligibility),
            sources=[_source_from_record(record) for record in selected],
            request_id=request_id,
        )
