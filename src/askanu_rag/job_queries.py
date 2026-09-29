"""Deterministic, source-grounded Jobs retrieval and chat handling."""

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from askanu_rag.course_queries import _source_from_record
from askanu_rag.models import (
    AskResponse,
    AnswerState,
    Clarification,
    ClarificationOption,
    ConversationState,
    ConstraintSemanticType,
    CurrentJobItem,
    Domain,
    EntityKind,
    EntityResolutionBasis,
    HistoryTurn,
    InsufficientEvidenceResponse,
    JobRecord,
    NeedsClarificationResponse,
    OkResponse,
    PublicJobItem,
    QueryInterpretation,
    ResolvedEntity,
    ResultPage,
    ResultPageRequest,
    ResultSet,
    ResultSetStatus,
)
from askanu_rag.evidence_selection import build_result_set, classify_result_set_status
from askanu_rag.retrieval import JobReader
from askanu_rag.retrieval.hybrid import SharedHybridRetriever
from askanu_rag.retrieval.semantic import (
    LocalBm25Retriever,
    sparse_score_is_usable,
)
from askanu_rag.synthesis import SynthesisError, UNSAFE_EVIDENCE
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
    set_pending_clarification,
)

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
TECHNICAL_DISCOVERY_PATTERN = re.compile(
    r"\b(?:technical|software)\s*(?:/|or|and)?\s*(?:jobs?|roles?)\b|"
    r"\b(?:jobs?|roles?)\b[^?.!]{0,40}\b(?:technical|software)\b",
    re.I,
)
CLOSE_THIS_WEEK_PATTERN = re.compile(
    r"\bclos(?:e|es|ing)\s+(?:by\s+)?this\s+week\b", re.I
)
JOB_TITLE_SHAPE_PATTERN = re.compile(
    r"\b(?:officer|fellow|manager|director|coordinator|assistant|lead|"
    r"analyst|engineer|developer|researcher|administrator|role)\b",
    re.I,
)
TITLE_PATTERNS = (
    re.compile(
        r"^\s*(?:tell me(?: more)? about|give me(?: more)? information about)"
        r"\s+(.+?)\s*[?.!]*\s*$",
        re.I,
    ),
    re.compile(r"^\s*when does\s+(.+?)\s+close\s*[?.!]*\s*$", re.I),
    re.compile(
        r"^\s*is\s+(.+?)\s+(?:still\s+)?(?:current|open)\s*[?.!]*\s*$",
        re.I,
    ),
)


@dataclass(frozen=True)
class JobQueryOutcome:
    response: AskResponse
    state: ConversationState


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
    question: str,
    records: Sequence[JobRecord],
    interpretation: QueryInterpretation | None = None,
) -> tuple[dict[str, tuple[str, ...]], bool]:
    """Extract only explicit values already present in current stored Jobs."""

    filters: dict[str, tuple[str, ...]] = {}
    normalized = _normalize(question)
    constraints = (
        tuple(
            item
            for item in interpretation.constraints.items
            if item.scope.domain == Domain.JOBS
        )
        if interpretation is not None
        else ()
    )

    def values(semantic_type: ConstraintSemanticType) -> set[str]:
        return {
            str(item.value)
            for item in constraints
            if item.semantic_type == semantic_type
        }

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
    requested_employment_types.update(
        values(ConstraintSemanticType.EMPLOYMENT_TYPE)
    )
    employment_types.update(requested_employment_types)
    if employment_types:
        filters["employment_types"] = tuple(sorted(employment_types))

    locations = values(ConstraintSemanticType.LOCATION)
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
    classifications.update(
        value
        for value in values(ConstraintSemanticType.CATEGORY)
        if re.fullmatch(r"ANU\d{1,4}", value, re.I)
    )
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
        elif field == "location":
            actual_value = metadata.location
            actual = (
                set()
                if actual_value is None
                else {
                    _normalize(part)
                    for part in re.split(r"\s*(?:/|,|;|\|)\s*", actual_value)
                    if part.strip()
                }
                | {_normalize(actual_value)}
            )
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
        *,
        interpretation: QueryInterpretation | None = None,
        selected_canonical_ids: tuple[str, ...] = (),
        conversation_state: ConversationState | None = None,
        result_page: ResultPageRequest | None = None,
    ) -> AskResponse | None:
        today = self._today_provider()
        if interpretation is not None and conversation_state is not None:
            resolved_page = resolve_result_page(
                conversation_state, interpretation, result_page
            )
            continuing = bool(
                result_page is not None
                or (
                    interpretation.intent is not None
                    and interpretation.intent.operation == "continue_results"
                )
            )
            if continuing:
                if (
                    resolved_page is None
                    or resolved_page.result_set.domain != Domain.JOBS
                ):
                    raise ResultPageResolutionError(
                        "Jobs result page is stale or foreign"
                    )
                start = resolved_page.start_ordinal - 1
                identities = resolved_page.result_set.ordered_canonical_ids[
                    start : start + resolved_page.limit
                ]
                page_records = tuple(
                    record
                    for identity in identities
                    if (
                        record := self._repository.find_job_by_entity_id(identity)
                    )
                    is not None
                    and _is_current(record, today)
                )
                if len(page_records) != len(identities):
                    raise ResultPageResolutionError(
                        "Jobs result identity is not current approved evidence"
                    )
                if not page_records:
                    return OkResponse(
                        answer="There are no more verified results in this retained Job result set.",
                        request_id=request_id,
                    )
                return OkResponse(
                    answer=(
                        "The current supported Jobs population is incomplete; "
                        "these are verified available results from the supported data.\n"
                        + "\n".join(
                            _job_answer(record, today) for record in page_records
                        )
                    ),
                    items=[
                        PublicJobItem(
                            **current_job_item(record).model_dump(mode="python"),
                            canonical_id=record.entity_id,
                        )
                        for record in page_records
                    ],
                    sources=[
                        _source_from_record(record) for record in page_records
                    ],
                    request_id=request_id,
                )

        selected = _pending_job(question, pending, self._repository)
        structured_ids = list(selected_canonical_ids)
        if (
            interpretation is not None
            and interpretation.entity is not None
            and interpretation.entity.domain == Domain.JOBS
            and interpretation.entity.canonical_id not in structured_ids
        ):
            structured_ids.append(interpretation.entity.canonical_id)
        if selected is None and structured_ids:
            structured = tuple(
                record
                for identity in structured_ids
                if (record := self._repository.find_job_by_entity_id(identity))
                is not None
            )
            if len(structured) != len(structured_ids):
                raise ResultPageResolutionError(
                    "Selected Job is not current approved evidence"
                )
            if len(structured) == 1:
                selected = structured[0]
        candidate = _title_candidate(question)
        title_matches = (
            self._repository.find_jobs_by_title(candidate)
            if candidate is not None
            else ()
        )
        if len(title_matches) > 1:
            return _job_clarification(title_matches, request_id)
        if len(title_matches) == 1:
            # An exact stored title is stronger than a number embedded inside
            # that title (for example "Verified Role 2").  A real Job ID still
            # resolves below when the complete title did not match.
            selected = title_matches[0]

        numeric = JOB_ID_PATTERN.search(question)
        if numeric is not None and not title_matches:
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

        semantic_intent = bool(
            candidate is None
            and (
                SEMANTIC_JOB_PATTERN.search(question)
                or TECHNICAL_DISCOVERY_PATTERN.search(question)
            )
        )
        current_records = self._repository.current_job_candidates(today)
        if (
            semantic_intent
            and conversation_state is not None
            and any(item.domain == Domain.JOBS for item in conversation_state.result_sets)
        ):
            parent = next(
                item
                for item in reversed(conversation_state.result_sets)
                if item.domain == Domain.JOBS
            )
            parent_ids = set(parent.ordered_canonical_ids)
            current_records = tuple(
                record
                for record in current_records
                if record.entity_id in parent_ids
            )
        filters, unmatched_explicit = _job_filters(
            question, current_records, interpretation
        )
        closing_this_week = CLOSE_THIS_WEEK_PATTERN.search(question) is not None
        if (
            _is_current_jobs_question(question)
            or semantic_intent
            or filters
            or unmatched_explicit
            or closing_this_week
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
            if closing_this_week and not unmatched_explicit:
                days_until_sunday = 6 - today.weekday()
                week_end = date.fromordinal(today.toordinal() + days_until_sunday)
                records = tuple(
                    record
                    for record in records
                    if record.metadata_json.closing_date is not None
                    and today
                    <= date.fromisoformat(record.metadata_json.closing_date)
                    <= week_end
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
                    answer=(
                        "The current supported Jobs population is incomplete. "
                        "I could not find a verified match in the supported data, "
                        "so this does not establish that no such ANU jobs exist."
                    ),
                    request_id=request_id,
                )
            return OkResponse(
                answer=(
                    "The current supported Jobs population is incomplete; these "
                    "are verified available results from the supported data.\n"
                    + "\n".join(_job_answer(record, today) for record in records)
                ),
                items=[
                    PublicJobItem(
                        **current_job_item(record).model_dump(mode="python"),
                        canonical_id=record.entity_id,
                    )
                    for record in records
                ],
                sources=[_source_from_record(record) for record in records],
                request_id=request_id,
            )
        return None

    def integrate_conversation(
        self,
        response: AskResponse,
        *,
        question: str,
        state: ConversationState,
        interpretation: QueryInterpretation,
        result_page: ResultPageRequest | None = None,
    ) -> JobQueryOutcome:
        """Project Jobs through the shared ResultSet and selection contracts."""

        today = self._today_provider()
        current = self._repository.current_job_candidates(today)
        by_id = {record.entity_id: record for record in current}
        by_record_id = {record.record_id: record for record in current}
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
                    if item.domain == Domain.JOBS
                    and (
                        interpretation.referenced_result_set_id is None
                        or item.result_set_id
                        == interpretation.referenced_result_set_id
                    )
                ),
                None,
            )
        )
        semantic = bool(
            SEMANTIC_JOB_PATTERN.search(question)
            or TECHNICAL_DISCOVERY_PATTERN.search(question)
        )
        filters, unmatched = _job_filters(question, current, interpretation)
        closing_this_week = CLOSE_THIS_WEEK_PATTERN.search(question) is not None
        listing = bool(
            resolved_page is not None
            or interpretation.entity is None
            and (
                _is_current_jobs_question(question)
                or semantic
                or filters
                or unmatched
                or closing_this_week
            )
        )

        ordered = selected
        if listing and resolved_page is None:
            if semantic:
                # Retrieval already established this ranked order; do not rerank
                # during state/presentation projection.
                ordered = selected
            else:
                ordered = tuple(
                    record
                    for record in current
                    if not unmatched and _matches_job_filters(record, filters)
                )
                if closing_this_week:
                    week_end = date.fromordinal(
                        today.toordinal() + 6 - today.weekday()
                    )
                    ordered = tuple(
                        record
                        for record in ordered
                        if record.metadata_json.closing_date is not None
                        and today
                        <= date.fromisoformat(record.metadata_json.closing_date)
                        <= week_end
                    )
            ordered = ordered[:20]

        result_set: ResultSet | None = None
        updated = state
        if listing and resolved_page is None:
            plan = build_retrieval_plan(
                interpretation,
                plan_id=f"plan:jobs:{state.turn_index}",
            )
            if plan is not None:
                identities = tuple(record.entity_id for record in ordered)
                if parent is not None and (
                    semantic
                    or closing_this_week
                    or bool(filters)
                    or unmatched
                    or (
                        interpretation.intent is not None
                        and interpretation.intent.operation == "refine_results"
                    )
                ):
                    result_set = refine_result_set(
                        parent,
                        result_set_id=f"rs:jobs:{state.turn_index}",
                        ordered_canonical_ids=identities,
                        constraints=interpretation.constraints,
                        status=classify_result_set_status(
                            identities, population_complete=False
                        ),
                        turn=state.turn_index,
                        originating_query=question,
                    )
                else:
                    result_set = build_result_set(
                        plan,
                        result_set_id=f"rs:jobs:{state.turn_index}",
                        entity_kind=EntityKind.JOB,
                        ordered_canonical_ids=identities,
                        originating_query=question,
                        created_turn=state.turn_index,
                        population_complete=False,
                    )
                updated = remember_result_set(updated, result_set)
                updated = set_pending_clarification(updated, None)

        active_set = result_set or (resolved_page.result_set if resolved_page else parent)
        if listing and resolved_page is None:
            selected = ordered[:5]
        public_page: ResultPage | None = None
        if active_set is not None and listing and active_set.status == ResultSetStatus.RESULTS:
            start_ordinal = (
                resolved_page.start_ordinal if resolved_page is not None else 1
            )
            public_page, continuation = result_page_metadata(
                active_set,
                start_ordinal=start_ordinal,
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
                    domain=Domain.JOBS,
                    kind=EntityKind.JOB,
                    canonical_id=record.entity_id,
                    canonical_name=record.title,
                    source_record_id=record.record_id,
                    resolution_basis=EntityResolutionBasis.RETAINED_STATE,
                    mentioned_turn=state.turn_index,
                ),
                focus=active_set is None,
            )

        public_items = []
        for record in selected:
            ordinal = None
            if active_set is not None and record.entity_id in active_set.ordered_canonical_ids:
                ordinal = active_set.ordered_canonical_ids.index(record.entity_id) + 1
            public_items.append(
                PublicJobItem(
                    **current_job_item(record).model_dump(mode="python"),
                    canonical_id=record.entity_id,
                    result_set_id=(
                        active_set.result_set_id if active_set is not None else None
                    ),
                    ordinal=ordinal,
                )
            )

        if listing and selected:
            answer = (
                "The current supported Jobs population is incomplete; these "
                "are verified available results from the supported data.\n"
                + "\n".join(_job_answer(record, today) for record in selected)
            )
            sources = [_source_from_record(record) for record in selected]
        else:
            answer = response.answer
            sources = response.sources
        updates: dict[str, object] = {
            "answer": answer,
            "items": public_items,
            "sources": sources,
            "answer_state": (
                AnswerState.PARTIAL
                if listing
                else AnswerState.CONFIRMED
                if response.status == "ok"
                else AnswerState.UNKNOWN
            ),
        }
        if public_page is not None and (
            public_page.has_more or resolved_page is not None
        ):
            updates["result_page"] = public_page
        projected = response.model_copy(update=updates)
        return JobQueryOutcome(response=projected, state=updated)
