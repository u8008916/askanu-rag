"""Deterministic, source-grounded Scholarship retrieval for Day 9."""

import math
import re
from dataclasses import dataclass

from askanu_rag.course_queries import (
    COURSE_CODE_CANDIDATE_PATTERN,
    _source_from_record,
)
from askanu_rag.models import (
    AnswerState,
    AskResponse,
    Clarification,
    ClarificationOption,
    ConversationState,
    Domain,
    EntityKind,
    EntityResolutionBasis,
    InsufficientEvidenceResponse,
    NeedsClarificationResponse,
    OkResponse,
    QueryInterpretation,
    ResolvedEntity,
    ResultPage,
    ResultPageRequest,
    ResultSet,
    ResultSetStatus,
    ScholarshipRecord,
)
from askanu_rag.evidence_selection import build_result_set, classify_result_set_status
from askanu_rag.journey_presentation import (
    SCHOLARSHIP_PUBLIC_FIELDS,
    comparison_has_missing_values,
    public_comparison_item,
    public_result_item,
    scholarship_field,
)
from askanu_rag.result_paging import (
    ResolvedResultPage,
    ResultPageResolutionError,
    resolve_result_page,
    result_page_metadata,
)
from askanu_rag.retrieval_planning import build_retrieval_plan
from askanu_rag.state_transitions import (
    refine_result_set,
    remember_entity,
    remember_result_page,
    remember_result_set,
    set_pending_clarification,
)
from askanu_rag.retrieval import ScholarshipReader
from askanu_rag.retrieval.hybrid import SharedHybridRetriever
from askanu_rag.retrieval.semantic import (
    LocalBm25Retriever,
    sparse_score_is_usable,
)
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
COMPARE_PATTERN = re.compile(r"\b(?:compare|versus|vs[.]?)\b", re.IGNORECASE)
OPEN_APPLICATION_PATTERN = re.compile(
    r"\b(?:still open|currently open|can still apply|still apply|open now)\b",
    re.IGNORECASE,
)
SCHOLARSHIP_FOLLOW_UP_PATTERN = re.compile(
    r"\b(?:it|one|close|closes|closing|eligible|eligibility|qualify|"
    r"apply|application|required|value|worth|status)\b",
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


@dataclass(frozen=True)
class ScholarshipAnswerOutcome:
    response: AskResponse
    ordered_records: tuple[ScholarshipRecord, ...] = ()
    presented_records: tuple[ScholarshipRecord, ...] = ()
    unknown_records: tuple[ScholarshipRecord, ...] = ()
    population_complete: bool = True
    discovery: bool = False
    comparison: bool = False
    eligibility: bool = False
    resolved_page: ResolvedResultPage | None = None


@dataclass(frozen=True)
class ScholarshipConversationOutcome:
    response: AskResponse
    state: ConversationState


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
    if re.search(r"\bopen\b", normalized) or OPEN_APPLICATION_PATTERN.search(
        question
    ):
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


def _lacks_filter_evidence(
    record: ScholarshipRecord, filters: dict[str, object]
) -> bool:
    """Return true when a requested structured dimension is not published.

    A missing value cannot prove a mismatch.  It stays outside the confirmed
    matches while keeping the population/answer explicitly incomplete.
    """

    metadata = record.metadata_json
    for field in filters:
        actual = getattr(metadata, field)
        if field in FILTER_FIELDS and not actual:
            return True
        if field not in FILTER_FIELDS and actual is None:
            return True
    return False


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
        sparse_retriever=None,
        top_k: int = 20,
        min_score: float = 0.2,
        max_candidates: int = 20,
        reranker=None,
        evidence_top_k: int = 5,
        rrf_k: int = 60,
    ) -> None:
        if not 1 <= top_k <= 20 or not 1 <= evidence_top_k <= 5 or not 0 < min_score <= 1:
            raise ValueError("Invalid bounded retrieval settings.")
        self._repository = repository
        self._vector = vector_retriever
        self._sparse = sparse_retriever or LocalBm25Retriever()
        self._top_k = top_k
        self._evidence_top_k = evidence_top_k
        self._reranker = reranker
        self._min_score = min_score
        self._merger = SharedHybridRetriever(max_candidates=max_candidates, rrf_k=rrf_k)

    async def _legacy_answer(
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
        elif len(identities) > 1 and not COMPARE_PATTERN.search(question):
            return _clarification(
                identities,
                request_id,
                "Which scholarship do you mean?",
            )
        elif identities:
            selected = identities
        else:
            if not filters and not semantic_intent:
                return _clarification(
                    records,
                    request_id,
                    "Which scholarship, study level, or area of study do you mean?",
                )
            matches = tuple(
                record for record in records if _matches_filters(record, filters)
            )
            if semantic_intent:
                by_id = {record.record_id: record for record in matches}
                sparse_status = "ok"
                try:
                    sparse_hits = self._sparse.search(
                        question,
                        matches,
                        top_k=self._top_k,
                        min_score=self._min_score,
                    )
                except Exception:
                    sparse_hits = ()
                    sparse_status = "failed"
                sparse = (
                    (by_id[hit.record_id], hit.score)
                    for hit in sparse_hits
                    if hit.record_id in by_id
                    and sparse_score_is_usable(
                        self._sparse,
                        hit.score,
                        min_score=self._min_score,
                    )
                )
                semantic = ()
                dense_status = "disabled"
                if self._vector is not None:
                    try:
                        vector_hits = self._vector.search(
                            question,
                            domain="scholarships",
                            allowed_records=matches,
                            top_k=self._top_k,
                            min_score=self._min_score,
                        )
                        dense_status = "ok"
                    except Exception:
                        vector_hits = ()
                        dense_status = "failed"
                    semantic = (
                        (
                            by_id[hit.record.record_id],
                            hit.score,
                            hit.retrieval_unit_ids,
                        )
                        for hit in vector_hits
                        if hit.record.record_id in by_id
                        and math.isfinite(hit.score)
                        and self._min_score <= hit.score <= 1
                    )
                selected = tuple(
                    candidate.record
                    for candidate in self._merger.select(
                        query=question,
                        sparse=sparse,
                        semantic=semantic,
                        reranker=self._reranker,
                        top_n=self._evidence_top_k,
                        sparse_status=sparse_status,
                        dense_status=dense_status,
                    ).candidates
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

    async def answer(
        self,
        question: str,
        request_id: str,
        pending: Clarification | None = None,
    ) -> AskResponse | None:
        """Backwards-compatible single-turn Scholarship response."""

        return await self._legacy_answer(question, request_id, pending)

    async def answer_with_context(
        self,
        question: str,
        request_id: str,
        pending: Clarification | None = None,
        *,
        interpretation: QueryInterpretation,
        selected_canonical_ids: tuple[str, ...] = (),
        conversation_state: ConversationState,
        result_page: ResultPageRequest | None = None,
    ) -> ScholarshipAnswerOutcome:
        """Resolve shared ResultSet references before any new retrieval/ranking."""

        records = self._repository.all_scholarships()
        by_entity_id = {record.entity_id: record for record in records}
        by_record_id = {record.record_id: record for record in records}

        resolved_page = resolve_result_page(
            conversation_state,
            interpretation,
            result_page,
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
                or resolved_page.result_set.domain != Domain.SCHOLARSHIPS
            ):
                raise ResultPageResolutionError(
                    "Scholarship continuation is stale or foreign"
                )
            start = resolved_page.start_ordinal - 1
            page_ids = resolved_page.result_set.ordered_canonical_ids[
                start : start + resolved_page.limit
            ]
            selected = tuple(
                by_entity_id[canonical_id]
                for canonical_id in page_ids
                if canonical_id in by_entity_id
            )
            if len(selected) != len(page_ids):
                raise ResultPageResolutionError(
                    "Scholarship ResultSet identity is not current evidence"
                )
            response = OkResponse(
                answer=(
                    _answer(selected, eligibility=False)
                    if selected
                    else "There are no more Scholarships in this result set."
                ),
                sources=[_source_from_record(record) for record in selected],
                request_id=request_id,
            )
            return ScholarshipAnswerOutcome(
                response=response,
                ordered_records=selected,
                presented_records=selected,
                resolved_page=resolved_page,
            )

        parent = next(
            (
                item
                for item in conversation_state.result_sets
                if item.domain == Domain.SCHOLARSHIPS
                and (
                    item.result_set_id == interpretation.referenced_result_set_id
                    or (
                        conversation_state.focus is not None
                        and item.result_set_id
                        == conversation_state.focus.result_set_id
                    )
                )
            ),
            None,
        )
        if OPEN_APPLICATION_PATTERN.search(question) and parent is not None:
            parent_records = tuple(
                by_entity_id[canonical_id]
                for canonical_id in parent.ordered_canonical_ids
                if canonical_id in by_entity_id
            )
            selected = tuple(
                record
                for record in parent_records
                if isinstance(record.metadata_json.status, str)
                and _normalize(record.metadata_json.status) == "open"
            )
            unknown = tuple(
                record
                for record in parent_records
                if record.metadata_json.status is None
            )
            if selected:
                response = OkResponse(
                    answer=(
                        "These Scholarships have an explicitly published open "
                        "status. "
                        + _answer(selected[:5], eligibility=False)
                        + (
                            " Some retained Scholarships have no published status, "
                            "so this refinement is incomplete."
                            if unknown
                            else ""
                        )
                    ),
                    sources=[
                        _source_from_record(record) for record in selected[:5]
                    ],
                    request_id=request_id,
                )
            else:
                response = InsufficientEvidenceResponse(
                    answer=(
                        "I cannot establish a complete still-open result because "
                        "the retained Scholarships lack sufficient published status "
                        "evidence."
                        if unknown
                        else "No retained Scholarship has an explicitly published "
                        "open status."
                    ),
                    sources=[_source_from_record(record) for record in unknown[:5]],
                    request_id=request_id,
                )
            return ScholarshipAnswerOutcome(
                response=response,
                ordered_records=selected,
                presented_records=selected[:5],
                unknown_records=unknown,
                population_complete=not unknown,
                discovery=True,
            )

        resolved_ids = list(selected_canonical_ids)
        if (
            interpretation.entity is not None
            and interpretation.entity.domain == Domain.SCHOLARSHIPS
            and interpretation.entity.canonical_id not in resolved_ids
        ):
            resolved_ids.append(interpretation.entity.canonical_id)
        if not resolved_ids and SCHOLARSHIP_FOLLOW_UP_PATTERN.search(question):
            selection = conversation_state.selected_result
            if selection is not None:
                result_set = next(
                    (
                        item
                        for item in conversation_state.result_sets
                        if item.result_set_id == selection.result_set_id
                        and item.domain == Domain.SCHOLARSHIPS
                    ),
                    None,
                )
                if result_set is not None:
                    resolved_ids.append(selection.canonical_id)
            if not resolved_ids:
                retained = next(
                    (
                        entity
                        for entity in conversation_state.recent_entities
                        if entity.domain == Domain.SCHOLARSHIPS
                        and entity.kind == EntityKind.SCHOLARSHIP
                    ),
                    None,
                )
                if retained is not None:
                    resolved_ids.append(retained.canonical_id)

        selected = tuple(
            by_entity_id[identity]
            if identity in by_entity_id
            else by_record_id[identity]
            for identity in resolved_ids
            if identity in by_entity_id or identity in by_record_id
        )
        eligibility = ELIGIBILITY_PATTERN.search(question) is not None
        requested_fact = _requested_fact(question)
        comparing = COMPARE_PATTERN.search(question) is not None
        if selected:
            if requested_fact is not None and not eligibility and len(selected) == 1:
                response = _fact_response(selected[0], requested_fact, request_id)
            else:
                response = OkResponse(
                    answer=_answer(selected, eligibility=eligibility),
                    sources=[_source_from_record(record) for record in selected],
                    request_id=request_id,
                )
            return ScholarshipAnswerOutcome(
                response=response,
                ordered_records=selected,
                presented_records=selected,
                comparison=comparing and len(selected) > 1,
                eligibility=eligibility,
            )

        response = await self._legacy_answer(question, request_id, pending)
        if response is None:
            return ScholarshipAnswerOutcome(response=InsufficientEvidenceResponse(
                answer="I could not resolve a current Scholarship reference.",
                request_id=request_id,
            ))
        ordered = tuple(
            by_record_id[source.record_id]
            for source in response.sources
            if source.record_id in by_record_id
        )
        filters = _explicit_filters(
            question,
            records,
            scope_refinement=(
                pending is not None and pending.id == "clar-scholarship-scope"
            ),
        )
        discovery = bool(
            response.status == "ok"
            and not _identity_matches(question, records)
            and (filters or SEMANTIC_DISCOVERY_PATTERN.search(question))
        )
        comparing = COMPARE_PATTERN.search(question) is not None and len(ordered) > 1
        unknown = tuple(
            record
            for record in records
            if filters
            and record not in ordered
            and _lacks_filter_evidence(record, filters)
        )
        presented = ordered[:5] if discovery and not comparing else ordered
        if presented != ordered:
            response = response.model_copy(
                update={
                    "answer": _answer(presented, eligibility=eligibility),
                    "sources": [
                        _source_from_record(record) for record in presented
                    ],
                }
            )
        return ScholarshipAnswerOutcome(
            response=response,
            ordered_records=ordered,
            presented_records=presented,
            unknown_records=unknown,
            population_complete=not unknown,
            discovery=discovery,
            comparison=comparing,
            eligibility=eligibility,
        )

    def integrate_conversation(
        self,
        outcome: ScholarshipAnswerOutcome,
        *,
        question: str,
        state: ConversationState,
        interpretation: QueryInterpretation,
    ) -> ScholarshipConversationOutcome:
        """Project Scholarship retrieval into shared state and public contracts."""

        updated = state
        result_set: ResultSet | None = None
        parent = next(
            (
                item
                for item in state.result_sets
                if item.domain == Domain.SCHOLARSHIPS
                and (
                    item.result_set_id == interpretation.referenced_result_set_id
                    or (
                        state.focus is not None
                        and item.result_set_id == state.focus.result_set_id
                    )
                )
            ),
            None,
        )
        if outcome.discovery and outcome.resolved_page is None:
            plan = build_retrieval_plan(
                interpretation,
                plan_id=f"plan:scholarships:{state.turn_index}",
            )
            if plan is not None:
                identities = tuple(
                    record.entity_id for record in outcome.ordered_records
                )
                status = classify_result_set_status(
                    identities,
                    population_complete=outcome.population_complete,
                )
                if parent is not None and OPEN_APPLICATION_PATTERN.search(question):
                    result_set = refine_result_set(
                        parent,
                        result_set_id=f"rs:scholarships:{state.turn_index}",
                        ordered_canonical_ids=identities,
                        constraints=interpretation.constraints,
                        status=status,
                        turn=state.turn_index,
                        originating_query=question,
                    )
                else:
                    result_set = build_result_set(
                        plan,
                        result_set_id=f"rs:scholarships:{state.turn_index}",
                        entity_kind=EntityKind.SCHOLARSHIP,
                        ordered_canonical_ids=identities,
                        originating_query=question,
                        created_turn=state.turn_index,
                        population_complete=outcome.population_complete,
                    )
                updated = remember_result_set(updated, result_set)

        public_page: ResultPage | None = None
        active_set = result_set
        if outcome.resolved_page is not None:
            active_set = outcome.resolved_page.result_set
            public_page, next_ordinal = result_page_metadata(
                active_set,
                start_ordinal=outcome.resolved_page.start_ordinal,
                returned=len(outcome.presented_records),
            )
            updated = remember_result_page(
                updated,
                result_set_id=active_set.result_set_id,
                next_ordinal=next_ordinal,
            )
        elif result_set is not None and result_set.status == ResultSetStatus.RESULTS:
            public_page, next_ordinal = result_page_metadata(
                result_set,
                start_ordinal=1,
                returned=len(outcome.presented_records),
            )
            updated = remember_result_page(
                updated,
                result_set_id=result_set.result_set_id,
                next_ordinal=next_ordinal,
            )

        if len(outcome.presented_records) == 1:
            record = outcome.presented_records[0]
            entity = ResolvedEntity(
                domain=Domain.SCHOLARSHIPS,
                kind=EntityKind.SCHOLARSHIP,
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

        if outcome.comparison:
            items = [
                public_comparison_item(
                    outcome.presented_records,
                    active_set or parent,
                    fields=SCHOLARSHIP_PUBLIC_FIELDS,
                    projector=scholarship_field,
                )
            ]
        else:
            items = [
                public_result_item(
                    record,
                    active_set or parent,
                    fields=SCHOLARSHIP_PUBLIC_FIELDS,
                    projector=scholarship_field,
                )
                for record in outcome.presented_records
            ]

        if outcome.eligibility:
            has_criteria = any(
                record.metadata_json.eligibility is not None
                for record in outcome.presented_records
            )
            answer_state = AnswerState.PARTIAL if has_criteria else AnswerState.UNKNOWN
        elif not outcome.population_complete:
            answer_state = (
                AnswerState.PARTIAL
                if outcome.presented_records
                else AnswerState.UNKNOWN
            )
        elif outcome.comparison and comparison_has_missing_values(
            outcome.presented_records,
            fields=SCHOLARSHIP_PUBLIC_FIELDS,
            projector=scholarship_field,
        ):
            answer_state = AnswerState.PARTIAL
        elif outcome.presented_records:
            answer_state = AnswerState.CONFIRMED
        else:
            answer_state = AnswerState.UNKNOWN

        if outcome.presented_records:
            updated = set_pending_clarification(updated, None)
        response = outcome.response.model_copy(
            update={
                "items": items,
                "answer_state": answer_state,
                "result_page": public_page,
            }
        )
        return ScholarshipConversationOutcome(response=response, state=updated)
