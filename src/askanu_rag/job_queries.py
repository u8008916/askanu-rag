"""Deterministic, source-grounded Jobs retrieval and chat handling."""

import math
import re
from collections.abc import Callable, Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from askanu_rag.course_queries import _source_from_record
from askanu_rag.models import (
    AskResponse,
    Clarification,
    ClarificationOption,
    CurrentJobItem,
    HistoryTurn,
    InsufficientEvidenceResponse,
    JobRecord,
    NeedsClarificationResponse,
    OkResponse,
)
from askanu_rag.retrieval import JobReader
from askanu_rag.retrieval.hybrid import SharedHybridRetriever
from askanu_rag.retrieval.semantic import (
    LocalBm25Retriever,
    sparse_score_is_usable,
)
from askanu_rag.synthesis import SynthesisError, UNSAFE_EVIDENCE

CANBERRA = ZoneInfo("Australia/Canberra")
JOB_ID_PATTERN = re.compile(
    r"\b(?:job|role|requisition)(?:\s+(?:id|number|no[.]?))?\s*[:#]?\s*(\d+)\b",
    re.IGNORECASE,
)
LIST_REQUEST_PATTERN = re.compile(
    r"^\s*(?:what|which|show|list|are there)\b", re.IGNORECASE
)
JOB_WORD_PATTERN = re.compile(r"\b(?:jobs?|roles?)\b", re.IGNORECASE)
CURRENT_WORD_PATTERN = re.compile(
    r"\b(?:current|currently|open|available|closing soon|fixed[-\s]term)\b",
    re.IGNORECASE,
)
FIXED_TERM_PATTERN = re.compile(r"\bfixed[-\s]term\b", re.IGNORECASE)
EMPLOYMENT_TYPE_PATTERN = re.compile(
    r"\b(fixed[-\s]term|continuing|casual)\b", re.IGNORECASE
)
ROLE_REFERENCE_PATTERN = re.compile(
    r"\b(?:this|that)\s+(?:ANU\s+)?(?:job|role)\b", re.I
)
REQUIREMENTS_PATTERN = re.compile(
    r"\b(?:requirements?|qualifications?|selection\s+criteria|essential\s+criteria)\b",
    re.I,
)
SEMANTIC_JOB_PATTERN = re.compile(
    r"\b(?:related\s+to|interested\s+in|focus(?:ed)?\s+on|about|"
    r"involv(?:e|es|ing))\b",
    re.I,
)
JOB_TITLE_SHAPE_PATTERN = re.compile(
    r"\b(?:officer|fellow|manager|director|coordinator|assistant|lead|"
    r"analyst|engineer|developer|researcher|administrator|role)\b",
    re.I,
)
TITLE_PATTERNS = (
    re.compile(r"^\s*tell me about\s+(.+?)\s*[?.!]*\s*$", re.I),
    re.compile(r"^\s*when does\s+(.+?)\s+close\s*[?.!]*\s*$", re.I),
    re.compile(
        r"^\s*is\s+(.+?)\s+(?:still\s+)?(?:current|open)\s*[?.!]*\s*$",
        re.I,
    ),
)


def canberra_today() -> date:
    """Return the current Canberra calendar date at one injectable boundary."""

    return datetime.now(CANBERRA).date()


def current_job_item(record: JobRecord) -> CurrentJobItem:
    """Map only approved persisted fields into the public Current Jobs DTO."""

    metadata = record.metadata_json
    return CurrentJobItem(
        record_id=record.record_id,
        source_id=record.source_id,
        job_id=record.entity_id,
        title=record.title,
        employment_types=metadata.employment_types,
        location=metadata.location,
        classification=metadata.classification,
        salary=metadata.salary,
        closing_text=metadata.closing_text,
        closing_date=metadata.closing_date,
        closing_at=metadata.closing_at,
        status="current",
        url=record.canonical_url,
        domain="jobs",
    )


def _is_current(record: JobRecord, today: date) -> bool:
    metadata = record.metadata_json
    return metadata.status == "current" and (
        metadata.closing_date is None
        or date.fromisoformat(metadata.closing_date) >= today
    )


def _title_candidate(question: str) -> str | None:
    for pattern in TITLE_PATTERNS:
        match = pattern.fullmatch(question)
        if match is not None:
            candidate = re.sub(
                r"^(?:the\s+)?(?:job|role)\s+", "", match.group(1), flags=re.I
            ).strip(" \"'")
            return candidate or None
    return None


def _is_current_jobs_question(question: str) -> bool:
    return bool(
        LIST_REQUEST_PATTERN.search(question)
        and JOB_WORD_PATTERN.search(question)
        and CURRENT_WORD_PATTERN.search(question)
    )


def _history_job_id(history: Sequence[HistoryTurn]) -> str | None:
    if not history:
        return None
    matches = {
        match.group(1) for match in JOB_ID_PATTERN.finditer(history[-1].content)
    }
    if len(matches) == 1:
        return next(iter(matches))
    return None


def _pending_job(
    question: str,
    pending: Clarification | None,
    repository: JobReader,
) -> JobRecord | None:
    if pending is None or pending.type != "job_selection":
        return None
    normalized = " ".join(question.casefold().split()).strip(".!?")
    selected_id = None
    if normalized in {"first", "first one", "1"} and pending.options:
        selected_id = pending.options[0].id
    elif normalized in {"second", "second one", "2"} and len(pending.options) > 1:
        selected_id = pending.options[1].id
    else:
        for option in pending.options[:20]:
            if normalized in {
                " ".join(option.id.casefold().split()),
                " ".join(option.label.casefold().split()),
            }:
                selected_id = option.id
                break
    if selected_id is None or not selected_id.startswith("jobs:job:"):
        return None
    return repository.find_job_by_entity_id(selected_id.removeprefix("jobs:job:"))


def _job_clarification(
    records: tuple[JobRecord, ...], request_id: str
) -> NeedsClarificationResponse:
    return NeedsClarificationResponse(
        answer="Which job role do you mean?",
        clarification=Clarification(
            id="clar-job-exact-title",
            type="job_selection",
            options=[
                ClarificationOption(
                    id=record.record_id,
                    label=" — ".join(
                        part
                        for part in (
                            record.title,
                            f"Job ID {record.entity_id}",
                            record.metadata_json.location,
                            record.metadata_json.classification,
                        )
                        if part
                    ),
                )
                for record in records[:20]
            ],
            allow_multiple=False,
        ),
        request_id=request_id,
    )


def _job_answer(record: JobRecord, today: date) -> str:
    metadata = record.metadata_json
    facts = [f"{record.title}. Job ID: {record.entity_id}."]
    facts.append(f"Stored status: {metadata.status or 'not provided'}.")
    if metadata.employment_types:
        facts.append(f"Employment types: {', '.join(metadata.employment_types)}.")
    if metadata.location is not None:
        facts.append(f"Location: {metadata.location}.")
    if metadata.classification is not None:
        facts.append(f"Classification: {metadata.classification}.")
    if metadata.salary is not None:
        facts.append(f"Salary: {metadata.salary}.")
    if metadata.closing_text is not None:
        facts.append(f"Closing information: {metadata.closing_text}.")
    elif metadata.closing_date is not None:
        facts.append(f"Closing date: {metadata.closing_date}.")
    if not _is_current(record, today):
        facts.append("This role is not current under the stored status and closing-date rule.")
    answer = " ".join(facts)
    if len(answer) > 3000 or UNSAFE_EVIDENCE.search(answer):
        raise SynthesisError()
    return answer


def _requirements_answer(record: JobRecord) -> str | None:
    requirements = record.metadata_json.role_requirements
    if not requirements:
        return None
    answer = (
        f"Official requirements published for {record.title} "
        f"(Job ID {record.entity_id}):\n- " + "\n- ".join(requirements)
    )
    if len(answer) > 3000 or UNSAFE_EVIDENCE.search(answer):
        raise SynthesisError()
    return answer


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_phrase(question: str, value: str) -> bool:
    normalized = _normalize(question)
    phrase = _normalize(value)
    return bool(phrase) and re.search(
        r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])",
        normalized,
    ) is not None


def _job_filters(
    question: str, records: Sequence[JobRecord]
) -> tuple[dict[str, tuple[str, ...]], bool]:
    """Extract only explicit values already present in current stored Jobs."""

    filters: dict[str, tuple[str, ...]] = {}
    normalized = _normalize(question)

    employment_types = {
        value
        for record in records
        for value in record.metadata_json.employment_types
        if value.strip() and _contains_phrase(question, value.replace("-", " "))
    }
    if FIXED_TERM_PATTERN.search(question):
        employment_types.update(
            value
            for record in records
            for value in record.metadata_json.employment_types
            if _normalize(value).replace("-", " ") == "fixed term"
        )
    requested_employment_types = {
        _normalize(match.group(1)).replace("-", " ").title()
        for match in EMPLOYMENT_TYPE_PATTERN.finditer(question)
    }
    employment_types.update(requested_employment_types)
    if employment_types:
        filters["employment_types"] = tuple(sorted(employment_types))

    locations = set()
    for record in records:
        value = record.metadata_json.location
        if value is None:
            continue
        aliases = {value, *re.split(r"\s*(?:/|,|;|\|)\s*", value)}
        if any(
            alias.strip()
            and re.search(
                r"\b(?:in|at|location(?:\s+is)?)\s+(?:the\s+)?"
                + re.escape(_normalize(alias))
                + r"(?![a-z0-9])",
                normalized,
            )
            for alias in aliases
        ):
            locations.add(value)
    if locations:
        filters["location"] = tuple(sorted(locations))

    categories = {
        record.metadata_json.category
        for record in records
        if record.metadata_json.category is not None
        and _contains_phrase(question, record.metadata_json.category)
        and (
            re.search(r"\bcategory\b", question, re.I)
            or re.search(
                r"\b(?:jobs?|roles?)\s+in\s+"
                + re.escape(_normalize(record.metadata_json.category))
                + r"(?![a-z0-9])",
                normalized,
            )
        )
    }
    if categories:
        filters["category"] = tuple(sorted(categories))

    classifications = {
        record.metadata_json.classification
        for record in records
        if record.metadata_json.classification is not None
        and _contains_phrase(question, record.metadata_json.classification)
        and re.search(r"\bclassification\b", question, re.I)
    }
    if classifications:
        filters["classification"] = tuple(sorted(classifications))

    salaries = {
        record.metadata_json.salary
        for record in records
        if record.metadata_json.salary is not None
        and _normalize(record.metadata_json.salary) in normalized
        and re.search(r"\bsalary\b", question, re.I)
    }
    if salaries:
        filters["salary"] = tuple(sorted(salaries))

    closing_values = set()
    if re.search(r"\bclos(?:e|es|ing)\b", question, re.I):
        for record in records:
            metadata = record.metadata_json
            if metadata.closing_date and _contains_phrase(question, metadata.closing_date):
                closing_values.add(metadata.closing_date)
            if metadata.closing_text and _normalize(metadata.closing_text) in normalized:
                closing_values.add(metadata.closing_text)
    if closing_values:
        filters["closing"] = tuple(sorted(closing_values))

    requirements = {
        item
        for record in records
        for item in (record.metadata_json.role_requirements or ())
        if _normalize(item) in normalized
        and re.search(r"\brequir(?:e|es|ed|ing|ements?)\b", question, re.I)
    }
    if requirements:
        filters["role_requirements"] = tuple(sorted(requirements))

    unmatched_explicit = bool(
        (re.search(r"\bclassification\b", question, re.I) and not classifications)
        or (re.search(r"\bcategory\b", question, re.I) and not categories)
        or (re.search(r"\bsalary\b", question, re.I) and not salaries)
        or (
            re.search(r"\bclos(?:e|es|ing)\b.+\b\d{4}-\d{2}-\d{2}\b", question, re.I)
            and not closing_values
        )
        or (
            re.search(r"\b(?:jobs?|roles?)\s+in\s+[^?.!]+", question, re.I)
            and not locations
            and not categories
        )
        or (
            re.search(r"\brequir(?:e|es|ed|ing)\b", question, re.I)
            and not requirements
        )
    )
    return filters, unmatched_explicit


def _matches_job_filters(
    record: JobRecord, filters: dict[str, tuple[str, ...]]
) -> bool:
    metadata = record.metadata_json
    for field, expected in filters.items():
        if field == "employment_types":
            actual = {
                _normalize(value).replace("-", " ")
                for value in metadata.employment_types
            }
            if not all(
                _normalize(value).replace("-", " ") in actual
                for value in expected
            ):
                return False
        elif field == "closing":
            actual = {
                value
                for value in (metadata.closing_date, metadata.closing_text)
                if value is not None
            }
            if not all(value in actual for value in expected):
                return False
        elif field == "role_requirements":
            actual = {_normalize(value) for value in metadata.role_requirements or ()}
            if not all(_normalize(value) in actual for value in expected):
                return False
        else:
            actual_value = getattr(metadata, field)
            if actual_value is None or not all(
                _normalize(value) == _normalize(actual_value) for value in expected
            ):
                return False
    return True


def is_plausible_job_question(
    question: str, pending: Clarification | None = None
) -> bool:
    """Cheap routing guard that performs no repository reads."""

    pending_job = pending is not None and pending.type == "job_selection"
    return bool(
        pending_job
        or JOB_ID_PATTERN.search(question)
        or JOB_WORD_PATTERN.search(question)
        or ROLE_REFERENCE_PATTERN.search(question)
        or (_title_candidate(question) and JOB_TITLE_SHAPE_PATTERN.search(question))
    )


class JobQueryService:
    """Answer Jobs with exact/current retrieval and optional bounded vectors."""

    def __init__(
        self,
        repository: JobReader,
        today_provider: Callable[[], date] = canberra_today,
        vector_retriever=None,
        *,
        sparse_retriever=None,
        top_k: int = 20,
        max_candidates: int = 20,
        min_score: float = 0.2,
        reranker=None,
        evidence_top_k: int = 5,
        rrf_k: int = 60,
    ) -> None:
        if not 1 <= top_k <= 20 or not 1 <= evidence_top_k <= 5 or not 0 < min_score <= 1:
            raise ValueError("min_score must be in (0, 1]")
        self._repository = repository
        self._today_provider = today_provider
        self._vector = vector_retriever
        self._sparse = sparse_retriever or LocalBm25Retriever()
        self._reranker = reranker
        self._merger = SharedHybridRetriever(max_candidates=max_candidates, rrf_k=rrf_k)
        self._top_k = top_k
        self._evidence_top_k = evidence_top_k
        self._min_score = min_score

    async def answer(
        self,
        question: str,
        request_id: str,
        pending: Clarification | None = None,
        history: Sequence[HistoryTurn] = (),
    ) -> AskResponse | None:
        today = self._today_provider()
        selected = _pending_job(question, pending, self._repository)
        numeric = JOB_ID_PATTERN.search(question)
        if numeric is not None:
            selected = self._repository.find_job_by_entity_id(numeric.group(1))
            if selected is None:
                return InsufficientEvidenceResponse(
                    answer=f"I could not find stored evidence for job {numeric.group(1)}.",
                    request_id=request_id,
                )

        if selected is None and ROLE_REFERENCE_PATTERN.search(question):
            history_id = _history_job_id(history)
            if history_id is not None:
                selected = self._repository.find_job_by_entity_id(history_id)
            if selected is None:
                return NeedsClarificationResponse(
                    answer="Which job role do you mean?",
                    clarification=Clarification(
                        id="clar-job-missing-role",
                        type="job_selection",
                        options=[],
                        allow_multiple=False,
                    ),
                    request_id=request_id,
                )

        if selected is not None and REQUIREMENTS_PATTERN.search(question):
            requirements_answer = _requirements_answer(selected)
            if requirements_answer is not None:
                return OkResponse(
                    answer=requirements_answer,
                    sources=[_source_from_record(selected)],
                    request_id=request_id,
                )
            return InsufficientEvidenceResponse(
                answer=(
                    "The stored Jobs record does not contain direct-page, "
                    "source-backed "
                    f"requirements for {selected.title} (Job ID {selected.entity_id}). "
                    "Please check the official job listing for the authoritative "
                    "requirements."
                ),
                sources=[_source_from_record(selected)],
                request_id=request_id,
            )

        if selected is not None:
            return OkResponse(
                answer=_job_answer(selected, today),
                sources=[_source_from_record(selected)],
                request_id=request_id,
            )

        candidate = _title_candidate(question)
        if candidate is not None:
            matches = self._repository.find_jobs_by_title(candidate)
            if len(matches) > 1:
                return _job_clarification(matches, request_id)
            if len(matches) == 1:
                return OkResponse(
                    answer=_job_answer(matches[0], today),
                    sources=[_source_from_record(matches[0])],
                    request_id=request_id,
                )

        semantic_intent = bool(
            candidate is None and SEMANTIC_JOB_PATTERN.search(question)
        )
        current_records = self._repository.current_job_candidates(today)
        filters, unmatched_explicit = _job_filters(question, current_records)
        if (
            _is_current_jobs_question(question)
            or semantic_intent
            or filters
            or unmatched_explicit
        ):
            records = (
                ()
                if unmatched_explicit
                else tuple(
                    record
                    for record in current_records
                    if _matches_job_filters(record, filters)
                )
            )
            if semantic_intent:
                if not records:
                    return InsufficientEvidenceResponse(
                        answer=(
                            "I could not establish sufficiently relevant current "
                            "Jobs evidence for that topic."
                        ),
                        request_id=request_id,
                    )
                by_id = {record.record_id: record for record in records}
                sparse_status = "ok"
                try:
                    sparse_hits = self._sparse.search(
                        question,
                        records,
                        top_k=self._top_k,
                        min_score=self._min_score,
                    )
                except Exception:
                    sparse_hits = ()
                    sparse_status = "failed"
                sparse = [
                    (by_id[hit.record_id], hit.score)
                    for hit in sparse_hits
                    if hit.record_id in by_id
                    and sparse_score_is_usable(
                        self._sparse, hit.score, min_score=self._min_score
                    )
                ]
                semantic = []
                dense_status = "disabled"
                if self._vector is not None:
                    try:
                        vector_hits = self._vector.search(
                            question,
                            domain="jobs",
                            allowed_records=records,
                            top_k=self._top_k,
                            min_score=self._min_score,
                        )
                        dense_status = "ok"
                    except Exception:
                        vector_hits = ()
                        dense_status = "failed"
                    semantic = [
                        (
                            by_id[hit.record.record_id],
                            hit.score,
                            hit.retrieval_unit_ids,
                        )
                        for hit in vector_hits
                        if hit.record.record_id in by_id
                        and math.isfinite(hit.score)
                        and self._min_score <= hit.score <= 1
                    ]
                records = tuple(
                    ranked.record
                    for ranked in self._merger.select(
                        query=question,
                        sparse=sparse,
                        semantic=semantic,
                        reranker=self._reranker,
                        top_n=self._evidence_top_k,
                        sparse_status=sparse_status,
                        dense_status=dense_status,
                    ).candidates
                )
            else:
                records = records[:20]
            if not records:
                return InsufficientEvidenceResponse(
                    answer="I could not find stored current Jobs evidence.",
                    request_id=request_id,
                )
            return OkResponse(
                answer="\n".join(_job_answer(record, today) for record in records),
                items=[
                    current_job_item(record).model_dump(mode="json")
                    for record in records
                ],
                sources=[_source_from_record(record) for record in records],
                request_id=request_id,
            )
        return None
