"""Deterministic, source-grounded Jobs retrieval and chat handling."""

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
ROLE_REFERENCE_PATTERN = re.compile(
    r"\b(?:this|that)\s+(?:ANU\s+)?(?:job|role)\b", re.I
)
REQUIREMENTS_PATTERN = re.compile(
    r"\b(?:requirements?|qualifications?|selection\s+criteria|essential\s+criteria)\b",
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


class JobQueryService:
    """Answer bounded Jobs questions without Gemini or vector retrieval."""

    def __init__(
        self,
        repository: JobReader,
        today_provider: Callable[[], date] = canberra_today,
    ) -> None:
        self._repository = repository
        self._today_provider = today_provider

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
            return InsufficientEvidenceResponse(
                answer=(
                    "The stored Jobs v1 record does not contain source-backed "
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

        if _is_current_jobs_question(question):
            employment_type = (
                "Fixed Term" if FIXED_TERM_PATTERN.search(question) else None
            )
            records = self._repository.current_jobs(
                20, today, employment_type=employment_type
            )
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
