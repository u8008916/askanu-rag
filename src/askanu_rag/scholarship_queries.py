"""Deterministic, source-grounded Scholarship retrieval for Day 9."""

import re

from askanu_rag.course_queries import _source_from_record
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
from askanu_rag.synthesis import SynthesisError, UNSAFE_EVIDENCE

SCHOLARSHIP_PATTERN = re.compile(r"\bscholarships?\b", re.IGNORECASE)
ELIGIBILITY_PATTERN = re.compile(
    r"\b(?:am i|eligible|eligibility|qualify|qualification)\b", re.IGNORECASE
)
FILTER_FIELDS = ("study_stage", "student_type", "study_level", "area_of_study")


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_phrase(question: str, value: str) -> bool:
    normalized = _normalize(question)
    phrase = _normalize(value)
    return bool(phrase) and re.search(
        r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", normalized
    ) is not None


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
    question: str, records: tuple[ScholarshipRecord, ...]
) -> dict[str, object]:
    filters: dict[str, object] = {}
    normalized = _normalize(question)
    if re.search(r"\bfeatured\b", normalized):
        filters["featured"] = True
    if re.search(r"\bopen\b", normalized):
        filters["status"] = "open"
    elif re.search(r"\bclosed\b", normalized):
        filters["status"] = "closed"
    if re.search(r"\bapplication required\b", normalized):
        filters["application_required"] = True

    for field in FILTER_FIELDS:
        known_values = {
            value
            for record in records
            for value in getattr(record.metadata_json, field)
            if value.strip()
        }
        selected = tuple(
            sorted(value for value in known_values if _contains_phrase(question, value))
        )
        if selected:
            filters[field] = selected
    return filters


def _matches_filters(record: ScholarshipRecord, filters: dict[str, object]) -> bool:
    metadata = record.metadata_json
    for field, expected in filters.items():
        actual = getattr(metadata, field)
        if field in FILTER_FIELDS:
            actual_values = {_normalize(value) for value in actual}
            if not all(_normalize(value) in actual_values for value in expected):
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

    def __init__(self, repository: ScholarshipReader) -> None:
        self._repository = repository

    async def answer(
        self,
        question: str,
        request_id: str,
        pending: Clarification | None = None,
    ) -> AskResponse | None:
        records = self._repository.all_scholarships()
        identities = _identity_matches(question, records)
        selected_pending = _pending_selection(question, records, pending)
        if (
            not SCHOLARSHIP_PATTERN.search(question)
            and not identities
            and not selected_pending
        ):
            return None

        eligibility = ELIGIBILITY_PATTERN.search(question) is not None
        if len(identities) > 1:
            return _clarification(
                identities,
                request_id,
                "Which scholarship do you mean?",
            )
        if len(identities) == 1:
            selected = identities
        elif selected_pending:
            selected = selected_pending
        else:
            filters = _explicit_filters(question, records)
            if not filters:
                return _clarification(
                    records,
                    request_id,
                    "Which scholarship, study level, or area of study do you mean?",
                )
            matches = tuple(
                record for record in records if _matches_filters(record, filters)
            )
            limit = (
                9
                if filters.get("featured") is True
                and filters.get("status") == "open"
                else 20
            )
            selected = matches[:limit]

        if not selected:
            return InsufficientEvidenceResponse(
                answer=(
                    "I could not find stored Scholarship evidence matching all "
                    "requested source-supported filters."
                ),
                request_id=request_id,
            )
        return OkResponse(
            answer=_answer(selected, eligibility=eligibility),
            sources=[_source_from_record(record) for record in selected],
            request_id=request_id,
        )
