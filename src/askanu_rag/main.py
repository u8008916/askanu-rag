"""AskANU HTTP service with exact-first, grounded Day 4 synthesis."""

from collections.abc import Callable, Sequence
from datetime import date, datetime
import logging
import re
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from askanu_rag.course_queries import COURSE_CODE_CANDIDATE_PATTERN, CourseQueryService
from askanu_rag.config import Settings
from askanu_rag.conversation_orchestrator import orchestrate_turn
from askanu_rag.conversation import resolve_current_session
from askanu_rag.domain_resolution import (
    DEFAULT_PROBLEM_DOMAIN_RESOLVER,
    ProblemDomainResolver,
)
from askanu_rag.entity_resolution import (
    DEFAULT_ENTITY_CATALOGUE,
    DEFAULT_SAFE_ENTITY_ALIASES,
    EntityCatalogue,
    SafeEntityAlias,
)
from askanu_rag.database import DatabaseConfigurationError, DatabaseConnectionConfig, RepositoryUnavailableError
from askanu_rag.gemini import GeminiSynthesisClient
from askanu_rag.event_queries import (
    EventQueryService,
    canberra_now,
    is_plausible_event_question,
    upcoming_event_item,
)
from askanu_rag.hybrid_queries import HybridQueryService
from askanu_rag.job_queries import (
    JobQueryService,
    canberra_today,
    current_job_item,
    is_plausible_job_question,
)
from askanu_rag.journey_presentation import integrate_course_presentation
from askanu_rag.resource_queries import (
    DomainResourceQueryService,
    is_plausible_resource_question,
)
from askanu_rag.result_paging import ResultPageResolutionError
from askanu_rag.retrieval.catalog import CatalogReader, record_code
from askanu_rag.retrieval.semantic import LocalBm25Retriever
from askanu_rag.retrieval.embeddings import GeminiEmbeddingProvider
from askanu_rag.retrieval.reranking import CohereReranker
from askanu_rag.retrieval.vector import PersistedSemanticRetriever, PostgresVectorRepository
from askanu_rag.synthesis import SynthesisClient, SynthesisError
from askanu_rag.models import (
    AskRequest,
    AskResponse,
    Clarification,
    ClarificationOption,
    CurrentJobsResponse,
    Domain,
    EntityKind,
    EntityResolutionBasis,
    ErrorResponse,
    HealthResponse,
    InsufficientEvidenceResponse,
    NeedsClarificationResponse,
    OffTopicResponse,
    QueryInterpretation,
    ResolvedIntent,
    SemanticFocus,
    UpcomingEventsResponse,
)
from askanu_rag.models.conversation_state import ConversationState, ResolvedEntity
from askanu_rag.retrieval import (
    CourseProgramReader,
    CourseProgramRepository,
    EventReader,
    JobReader,
    PostgresCourseProgramRepository,
    ResourceReader,
    ScholarshipReader,
    UnavailableCourseProgramRepository,
    create_default_course_program_repository,
    load_common_record_file,
    load_common_records_directory,
)
from askanu_rag.scholarship_queries import (
    OPEN_APPLICATION_PATTERN,
    SCHOLARSHIP_FOLLOW_UP_PATTERN,
    ScholarshipQueryService,
    is_plausible_scholarship_question,
)
from askanu_rag.state_transitions import (
    ResultReferenceResolution,
    pending_from_public_clarification,
    remember_entity,
    select_result,
    set_semantic_focus,
    set_pending_clarification,
)
from askanu_rag.transport_limits import (
    ASK_REQUEST_MAX_BYTES,
    state_fits_transport,
)

MOCK_CLARIFICATION_TRIGGER = "mock:needs_clarification"
SAFE_ERROR_ANSWER = "The request could not be completed."
# Child of Uvicorn's configured operational logger; access logging stays disabled.
REQUEST_LOGGER = logging.getLogger("uvicorn.error.askanu_rag.requests")
UPSTREAM_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def new_request_id() -> str:
    """Return an opaque request identifier with no internal state."""

    return f"req_{uuid4().hex}"


def controlled_error_response(
    status_code: int,
    request_id: str | None = None,
    conversation_state: ConversationState | None = None,
    *,
    include_conversation_state: bool = False,
) -> JSONResponse:
    """Build the frozen error envelope for controlled HTTP failures."""

    safe_state = conversation_state or ConversationState()
    if not state_fits_transport(safe_state):
        safe_state = ConversationState()
    payload = ErrorResponse(
        answer=SAFE_ERROR_ANSWER,
        request_id=request_id or new_request_id(),
        conversation_state=safe_state,
    )
    content = payload.model_dump(mode="json")
    if content.get("result_page") is None:
        content.pop("result_page", None)
    if not include_conversation_state:
        content.pop("conversation_state")
    return JSONResponse(status_code=status_code, content=content)


def _valid_inbound_state_from_validation_error(
    exc: RequestValidationError,
) -> ConversationState | None:
    """Recover only a separately valid, bounded state from a rejected Ask body."""

    body = exc.body
    if not isinstance(body, dict) or "conversation_state" not in body:
        return None
    try:
        state = ConversationState.model_validate(body["conversation_state"])
    except (TypeError, ValueError):
        return None
    return state if state_fits_transport(state) else None


def _course_record_for_source_id(
    repository,
    record_id: str,
    *,
    expected_code: str | None = None,
):
    """Resolve one canonical Course source record without a catalogue scan."""

    prefix = "courses:course:"
    finder = getattr(repository, "find_course_by_code", None)

    if finder is not None and record_id.startswith(prefix):
        identity = record_id[len(prefix):]
        code, separator, year = identity.rpartition("_")

        if (
            separator
            and code
            and len(year) == 4
            and year.isdigit()
            and (
                expected_code is None
                or code == expected_code
            )
        ):
            result = finder(code, year)

            candidates = (
                ()
                if result is None
                else result
                if isinstance(result, tuple)
                else (result,)
            )

            exact = next(
                (
                    record
                    for record in candidates
                    if record.record_id == record_id
                    and record.metadata_json.entity_type == "course"
                    and (
                        expected_code is None
                        or record_code(record) == expected_code
                    )
                ),
                None,
            )

            if exact is not None:
                return exact

    # Compatibility fallback for non-standard source IDs / repositories.
    return next(
        (
            record
            for record in repository.all_records()
            if record.record_id == record_id
            and record.metadata_json.entity_type == "course"
            and (
                expected_code is None
                or record_code(record) == expected_code
            )
        ),
        None,
    )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


def _validated_upstream_request_id(request: Request) -> str:
    """Return a safe log value without trusting or echoing an invalid header."""

    value = request.headers.get("x-request-id")
    if value is None:
        return "none"
    if UPSTREAM_REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return "invalid"


def _state_with_verified_result_selection(
    payload: AskRequest,
    repository: CourseProgramReader,
) -> ConversationState:
    """Re-resolve untrusted clicked-result context against approved records."""

    selection = payload.selected_result
    state = payload.conversation_state
    if selection is None:
        return state
    result_set = next(
        item
        for item in state.result_sets
        if item.result_set_id == selection.result_set_id
    )
    if result_set.domain == Domain.SCHOLARSHIPS and isinstance(
        repository, ScholarshipReader
    ):
        records = repository.all_scholarships()
    elif result_set.domain == Domain.JOBS and isinstance(repository, JobReader):
        current = repository.find_job_by_entity_id(selection.canonical_id)
        records = () if current is None else (current,)
    elif result_set.domain == Domain.EVENTS and isinstance(repository, EventReader):
        records = repository.all_events()
    elif (
        result_set.domain in {Domain.ACCOMMODATION, Domain.SUPPORT}
        and isinstance(repository, ResourceReader)
    ):
        records = repository.all_domain_records(result_set.domain.value)
    else:
        raise StarletteHTTPException(status_code=400)
    record = next(
        (
            item
            for item in records
            if item.entity_id == selection.canonical_id
        ),
        None,
    )
    if record is None:
        raise StarletteHTTPException(status_code=400)
    entity = ResolvedEntity(
        domain=result_set.domain,
        kind=result_set.entity_kind,
        canonical_id=record.entity_id,
        canonical_name=record.title,
        source_record_id=record.record_id,
        resolution_basis=EntityResolutionBasis.RETAINED_STATE,
        mentioned_turn=state.turn_index,
    )
    state = remember_entity(state, entity, focus=False)
    state = select_result(
        state,
        ResultReferenceResolution(
            result_set=result_set,
            canonical_ids=(record.entity_id,),
            clarification_required=False,
        ),
    )
    return set_semantic_focus(
        state,
        SemanticFocus(
            domain=result_set.domain,
            entity_kind=result_set.entity_kind,
            canonical_entity_id=record.entity_id,
            result_set_id=result_set.result_set_id,
            intent_name=result_set.intent.name,
        ),
    )


def _verify_structured_result_page(
    payload: AskRequest,
    repository: CourseProgramReader,
) -> None:
    """Re-resolve the requested slice; client state never supplies records."""

    page = payload.result_page
    if page is None:
        return
    result_set = next(
        item
        for item in payload.conversation_state.result_sets
        if item.result_set_id == page.result_set_id
    )
    if result_set.domain == Domain.SCHOLARSHIPS and isinstance(
        repository, ScholarshipReader
    ):
        records = repository.all_scholarships()
    elif result_set.domain == Domain.JOBS and isinstance(repository, JobReader):
        records = tuple(
            record
            for canonical_id in result_set.ordered_canonical_ids
            if (record := repository.find_job_by_entity_id(canonical_id)) is not None
        )
    elif result_set.domain == Domain.EVENTS and isinstance(repository, EventReader):
        records = repository.all_events()
    elif result_set.domain in {Domain.ACCOMMODATION, Domain.SUPPORT} and isinstance(
        repository, ResourceReader
    ):
        records = repository.all_domain_records(result_set.domain.value)
    else:
        raise StarletteHTTPException(status_code=400)
    start = page.start_ordinal - 1
    requested_ids = result_set.ordered_canonical_ids[
        start : start + page.limit
    ]
    current_ids = {record.entity_id for record in records}
    if any(canonical_id not in current_ids for canonical_id in requested_ids):
        raise StarletteHTTPException(status_code=400)


def _mark_response(request: Request, response: AskResponse) -> AskResponse:
    state = getattr(request.state, "conversation_state", ConversationState())
    if response.clarification is not None:
        clarification = response.clarification
        state = set_pending_clarification(
            state,
            pending_from_public_clarification(
                clarification_id=clarification.id,
                clarification_type=clarification.type,
                options=tuple(
                    (option.id, option.label) for option in clarification.options
                ),
                allow_multiple=clarification.allow_multiple,
                turn=state.turn_index,
            ),
        )
    # Without a public clarification, preserve the orchestrator-owned pending
    # lifecycle.  It has already completed, superseded, or retained the
    # operation deterministically for this turn.
    if not state_fits_transport(state):
        raise RuntimeError("authoritative conversation_state exceeds transport limit")
    response = response.model_copy(update={"conversation_state": state})
    request.state.response_status = response.status
    return response


def _is_oversized_input(errors: Sequence[dict[str, Any]]) -> bool:
    """Identify frozen component size-limit validation failures."""

    for error in errors:
        location = tuple(error.get("loc", ()))
        error_type = error.get("type")
        if error_type == "bytes_too_long" and location[:1] == ("body",):
            return True
        if location == ("body", "question") and error_type == "string_too_long":
            return True
        if location[:2] == ("body", "history") and error_type in {
            "string_too_long",
            "too_long",
        }:
            return True
    return False


def create_app(
    repository: CourseProgramReader | None = None,
    synthesis_client: SynthesisClient | None = None,
    *,
    timeout_seconds: float = 30,
    semantic_retriever=None,
    vector_retriever=None,
    reranker=None,
    semantic_top_k: int = 20,
    semantic_min_score: float = 0.2,
    jobs_today_provider: Callable[[], date] | None = None,
    events_now_provider: Callable[[], datetime] | None = None,
    max_merged_candidates: int = 20,
    evidence_top_k: int = 5,
    rrf_k: int = 60,
    entity_catalogue: EntityCatalogue = DEFAULT_ENTITY_CATALOGUE,
    entity_aliases: Sequence[SafeEntityAlias] = DEFAULT_SAFE_ENTITY_ALIASES,
    problem_domain_resolver: ProblemDomainResolver = DEFAULT_PROBLEM_DOMAIN_RESOLVER,
    resource_trace_sink: Callable[[Any], None] | None = None,
) -> FastAPI:
    """Inject providers explicitly; omission preserves the deterministic test path."""
    app = FastAPI(title="AskANU RAG", version="0.1.0", debug=False)
    repository = repository if repository is not None else create_default_course_program_repository()
    candidate_retriever = semantic_retriever or LocalBm25Retriever()
    if isinstance(repository, CatalogReader):
        course_queries = HybridQueryService(repository, synthesis_client, candidate_retriever,
            vector_retriever=vector_retriever, timeout_seconds=timeout_seconds,
            top_k=semantic_top_k, min_score=semantic_min_score,
            max_candidates=max_merged_candidates, reranker=reranker,
            evidence_top_k=evidence_top_k, rrf_k=rrf_k)
    else:
        course_queries = CourseQueryService(repository, synthesis_client, timeout_seconds)
    scholarship_queries = (
        ScholarshipQueryService(
            repository,
            vector_retriever,
            sparse_retriever=candidate_retriever,
            top_k=semantic_top_k,
            min_score=semantic_min_score,
            max_candidates=max_merged_candidates,
            reranker=reranker,
            evidence_top_k=evidence_top_k,
            rrf_k=rrf_k,
        )
        if isinstance(repository, ScholarshipReader)
        else None
    )
    jobs_today_provider = jobs_today_provider or canberra_today
    events_now_provider = events_now_provider or canberra_now
    job_queries = (
        JobQueryService(
            repository,
            jobs_today_provider,
            vector_retriever,
            sparse_retriever=candidate_retriever,
            top_k=semantic_top_k,
            max_candidates=max_merged_candidates,
            min_score=semantic_min_score,
            reranker=reranker,
            evidence_top_k=evidence_top_k,
            rrf_k=rrf_k,
        )
        if isinstance(repository, JobReader)
        else None
    )
    accommodation_queries = (
        DomainResourceQueryService(
            repository,
            "accommodation",
            vector_retriever,
            sparse_retriever=candidate_retriever,
            top_k=semantic_top_k,
            min_sparse_score=semantic_min_score,
            max_candidates=max_merged_candidates,
            reranker=reranker,
            evidence_top_k=evidence_top_k,
            rrf_k=rrf_k,
        )
        if isinstance(repository, ResourceReader)
        else None
    )
    support_queries = (
        DomainResourceQueryService(
            repository,
            "support",
            vector_retriever,
            sparse_retriever=candidate_retriever,
            top_k=semantic_top_k,
            min_sparse_score=semantic_min_score,
            max_candidates=max_merged_candidates,
            reranker=reranker,
            evidence_top_k=evidence_top_k,
            rrf_k=rrf_k,
        )
        if isinstance(repository, ResourceReader)
        else None
    )
    event_queries = (
        EventQueryService(repository, events_now_provider)
        if isinstance(repository, EventReader)
        else None
    )

    @app.middleware("http")
    async def request_metrics(request: Request, call_next):
        request.state.request_id = new_request_id()
        request.state.upstream_request_id = _validated_upstream_request_id(request)
        started = perf_counter()
        status_code = 500
        try:
            if request.method == "POST" and request.url.path == "/api/v1/ask":
                body = await request.body()
                if len(body) > ASK_REQUEST_MAX_BYTES:
                    status_code = 413
                    request.state.response_status = "error"
                    return controlled_error_response(
                        413,
                        request.state.request_id,
                        include_conversation_state=True,
                    )
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            latency_ms = (perf_counter() - started) * 1000
            REQUEST_LOGGER.info(
                "request_complete request_id=%s upstream_request_id=%s "
                "method=%s path=%s "
                "http_status=%s response_status=%s latency_ms=%.2f",
                request.state.request_id,
                request.state.upstream_request_id,
                request.method,
                request.url.path,
                status_code,
                getattr(
                    request.state,
                    "response_status",
                    "error" if status_code >= 400 else "not_applicable",
                ),
                latency_ms,
            )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        status_code = 413 if _is_oversized_input(exc.errors()) else 400
        _request.state.response_status = "error"
        validated_state = (
            _valid_inbound_state_from_validation_error(exc)
            if _request.url.path == "/api/v1/ask"
            else None
        )
        return controlled_error_response(
            status_code,
            _request_id(_request),
            validated_state,
            include_conversation_state=_request.url.path == "/api/v1/ask",
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        _request.state.response_status = "error"
        return controlled_error_response(
            exc.status_code,
            _request_id(_request),
            getattr(
                _request.state,
                "validated_inbound_conversation_state",
                None,
            ),
            include_conversation_state=_request.url.path == "/api/v1/ask",
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        _request.state.response_status = "error"
        return controlled_error_response(
            500,
            _request_id(_request),
            getattr(_request.state, "conversation_state", None),
            include_conversation_state=_request.url.path == "/api/v1/ask",
        )

    @app.exception_handler(SynthesisError)
    async def synthesis_error_handler(
        _request: Request, _exc: SynthesisError
    ) -> JSONResponse:
        # Handled explicitly so ASGI does not log provider exception tracebacks.
        _request.state.response_status = "error"
        return controlled_error_response(
            502,
            _request_id(_request),
            getattr(_request.state, "conversation_state", None),
            include_conversation_state=True,
        )

    @app.exception_handler(RepositoryUnavailableError)
    async def repository_error_handler(
        _request: Request, _exc: RepositoryUnavailableError
    ) -> JSONResponse:
        # A known dependency failure is handled below ServerErrorMiddleware so
        # Uvicorn does not print a redundant exception traceback.
        _request.state.response_status = "error"
        return controlled_error_response(
            500,
            _request_id(_request),
            getattr(_request.state, "conversation_state", None),
            include_conversation_state=_request.url.path == "/api/v1/ask",
        )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/api/v1/jobs/current", response_model=CurrentJobsResponse)
    async def current_jobs(
        request: Request,
        limit: int = Query(default=5, ge=1, le=20),
    ) -> CurrentJobsResponse:
        if job_queries is None:
            raise RepositoryUnavailableError()
        records = repository.current_jobs(limit, jobs_today_provider())
        response = CurrentJobsResponse(
            items=[current_job_item(record) for record in records],
            request_id=_request_id(request),
        )
        request.state.response_status = response.status
        return response

    @app.get("/api/v1/events/upcoming", response_model=UpcomingEventsResponse)
    async def upcoming_event_list(
        request: Request,
        limit: int = Query(default=5, ge=1, le=20),
    ) -> UpcomingEventsResponse:
        if event_queries is None:
            raise RepositoryUnavailableError()
        records = repository.upcoming_official_events(limit, events_now_provider())
        response = UpcomingEventsResponse(
            items=[upcoming_event_item(record) for record in records],
            request_id=_request_id(request),
        )
        request.state.response_status = response.status
        return response

    @app.post("/api/v1/ask", response_model=AskResponse)
    async def ask(payload: AskRequest, request: Request) -> AskResponse:
        # The client carries this bounded, untrusted structure between turns.
        # RAG validates it and returns the authoritative next state; no server
        # session or factual evidence is created from it.
        # Once the request model has validated, keep its inbound state solely
        # for controlled semantic-rejection envelopes.  Such a rejected
        # operation must not behave like Clear Chat or expose a half-applied
        # turn transition.
        request.state.validated_inbound_conversation_state = (
            payload.conversation_state
        )
        request_state = _state_with_verified_result_selection(payload, repository)
        _verify_structured_result_page(payload, repository)
        clarification_option_ids = (
            tuple(payload.clarification_selection.option_ids)
            if payload.clarification_selection is not None
            else ()
        )
        conversation_turn = orchestrate_turn(
            payload.question,
            payload.history,
            request_state,
            entity_catalogue=entity_catalogue,
            entity_aliases=entity_aliases,
            problem_domain_resolver=problem_domain_resolver,
            clarification_option_ids=clarification_option_ids,
            prefer_selected_result=payload.selected_result is not None,
        )
        request.state.conversation_state = conversation_turn.state
        request.state.query_interpretation = conversation_turn.interpretation
        # Temporary Day 1 mock hook. It is not query-planning behaviour.
        if payload.question == MOCK_CLARIFICATION_TRIGGER:
            return _mark_response(
                request,
                NeedsClarificationResponse(
                    answer="Do you mean COMP1110 or COMP1600? (mock response)",
                    clarification=Clarification(
                        id="clar-42",
                        type="entity_selection",
                        options=[
                            ClarificationOption(
                                id="course:COMP1110", label="COMP1110"
                            ),
                            ClarificationOption(
                                id="course:COMP1600", label="COMP1600"
                            ),
                        ],
                        allow_multiple=True,
                    ),
                    request_id=_request_id(request),
                ),
            )

        request_id = _request_id(request)
        if isinstance(repository, CatalogReader) and (
            conversation_turn.interpretation.domain in {None, Domain.COURSES}
        ):
            resolved_entity = conversation_turn.interpretation.entity
            resolved_course_code = (
                resolved_entity.canonical_id
                if (
                    resolved_entity is not None
                    and resolved_entity.domain == Domain.COURSES
                    and resolved_entity.kind == EntityKind.COURSE
                    and not conversation_turn.interpretation.requires_clarification
                )
                else None
            )
            resolved_course_record_id = (
                resolved_entity.source_record_id
                if resolved_course_code is not None
                and resolved_entity is not None
                else None
            )
            if (
                resolved_course_code is not None
                and resolved_course_record_id is None
                and conversation_turn.interpretation.intent is not None
                and conversation_turn.interpretation.intent.operation
                == "return_topic"
            ):
                retained_course = next(
                    (
                        entity
                        for entity in request_state.recent_entities
                        if entity.domain == Domain.COURSES
                        and entity.kind == EntityKind.COURSE
                        and entity.canonical_id == resolved_course_code
                        and entity.source_record_id is not None
                    ),
                    None,
                )
                if retained_course is not None:
                    resolved_course_record_id = retained_course.source_record_id
            resolution = resolve_current_session(
                payload,
                repository,
                resolved_course_code=resolved_course_code,
                resolved_course_record_id=resolved_course_record_id,
            )

            # A completed entity-selection clarification may identify one exact
            # stored Course record. Persist that source identity in semantic
            # state so later references keep the selected academic year.
            if resolution.selected_record_id is not None:
                selected_record = _course_record_for_source_id(
                    repository,
                    resolution.selected_record_id,
                )
                if selected_record is not None:
                    selected_entity = ResolvedEntity(
                        domain=Domain.COURSES,
                        kind=EntityKind.COURSE,
                        canonical_id=record_code(selected_record),
                        canonical_name=selected_record.title,
                        source_record_id=selected_record.record_id,
                        resolution_basis=(
                            resolved_entity.resolution_basis
                            if resolved_entity is not None
                            and resolved_entity.canonical_id
                            == record_code(selected_record)
                            else EntityResolutionBasis.RETAINED_STATE
                        ),
                        mentioned_turn=conversation_turn.state.turn_index,
                    )
                    request.state.conversation_state = remember_entity(
                        request.state.conversation_state,
                        selected_entity,
                    )
            if resolution.clarification is not None:
                return _mark_response(
                    request,
                    NeedsClarificationResponse(
                        answer=resolution.clarification_answer
                        or "Please choose a current option.",
                        clarification=resolution.clarification,
                        request_id=request_id,
                    ),
                )
            resolved_question = resolution.question
        else:
            resolved_question = payload.question

        pending = request_state.pending_clarification
        structured_job_page = bool(
            payload.result_page is not None
            and any(
                item.result_set_id == payload.result_page.result_set_id
                and item.domain == Domain.JOBS
                for item in conversation_turn.state.result_sets
            )
        )
        job_domain_resolved = structured_job_page or (
            conversation_turn.interpretation.domain == Domain.JOBS
            and not conversation_turn.interpretation.requires_clarification
        )
        if job_queries is not None and (
            job_domain_resolved
            or is_plausible_job_question(resolved_question, pending)
        ):
            try:
                job_response = await job_queries.answer(
                    resolved_question,
                    request_id,
                    request_state.pending_clarification,
                    payload.history,
                    interpretation=conversation_turn.interpretation,
                    selected_canonical_ids=conversation_turn.selected_canonical_ids,
                    conversation_state=conversation_turn.state,
                    result_page=payload.result_page,
                )
            except ResultPageResolutionError as exc:
                raise StarletteHTTPException(status_code=400) from exc
            if job_response is not None:
                outcome = job_queries.integrate_conversation(
                    job_response,
                    question=resolved_question,
                    state=conversation_turn.state,
                    interpretation=conversation_turn.interpretation,
                    result_page=payload.result_page,
                )
                request.state.conversation_state = outcome.state
                return _mark_response(request, outcome.response)

        scholarship_focus_active = bool(
            conversation_turn.state.focus is not None
            and conversation_turn.state.focus.domain == Domain.SCHOLARSHIPS
            and SCHOLARSHIP_FOLLOW_UP_PATTERN.search(resolved_question)
            and conversation_turn.interpretation.domain in {
                None,
                Domain.SCHOLARSHIPS,
            }
        )
        structured_scholarship_page = bool(
            payload.result_page is not None
            and any(
                item.result_set_id == payload.result_page.result_set_id
                and item.domain == Domain.SCHOLARSHIPS
                for item in conversation_turn.state.result_sets
            )
        )
        scholarship_domain_resolved = structured_scholarship_page or (
            conversation_turn.interpretation.domain == Domain.SCHOLARSHIPS
            and not conversation_turn.interpretation.requires_clarification
        ) or scholarship_focus_active
        if scholarship_queries is not None and (
            scholarship_domain_resolved
            or is_plausible_scholarship_question(resolved_question, pending)
        ):
            scholarship_interpretation = conversation_turn.interpretation
            interpretation_updates: dict[str, object] = {}
            if scholarship_interpretation.domain is None:
                interpretation_updates["domain"] = Domain.SCHOLARSHIPS
            if OPEN_APPLICATION_PATTERN.search(resolved_question):
                interpretation_updates["intent"] = ResolvedIntent(
                    name="discover",
                    operation="refine_results",
                )
            elif scholarship_interpretation.intent is None:
                interpretation_updates["intent"] = ResolvedIntent(
                    name="fact_lookup",
                    operation="lookup",
                )
            if interpretation_updates:
                scholarship_interpretation = QueryInterpretation.model_validate(
                    scholarship_interpretation.model_dump(mode="python")
                    | interpretation_updates
                )
            try:
                scholarship_answer = await scholarship_queries.answer_with_context(
                    resolved_question,
                    request_id,
                    request_state.pending_clarification,
                    interpretation=scholarship_interpretation,
                    selected_canonical_ids=conversation_turn.selected_canonical_ids,
                    conversation_state=conversation_turn.state,
                    result_page=payload.result_page,
                )
            except ResultPageResolutionError as exc:
                raise StarletteHTTPException(status_code=400) from exc
            scholarship_outcome = scholarship_queries.integrate_conversation(
                scholarship_answer,
                question=resolved_question,
                state=conversation_turn.state,
                interpretation=scholarship_interpretation,
            )
            request.state.conversation_state = scholarship_outcome.state
            return _mark_response(request, scholarship_outcome.response)

        structured_accommodation_page = bool(
            payload.result_page is not None
            and any(
                item.result_set_id == payload.result_page.result_set_id
                and item.domain == Domain.ACCOMMODATION
                for item in conversation_turn.state.result_sets
            )
        )
        accommodation_domain_resolved = structured_accommodation_page or (
            conversation_turn.interpretation.domain == Domain.ACCOMMODATION
            and not conversation_turn.interpretation.requires_clarification
            and (
                conversation_turn.interpretation.entity is not None
                or conversation_turn.interpretation.referenced_result_set_id is not None
            )
        )
        if accommodation_queries is not None and (
            accommodation_domain_resolved
            or is_plausible_resource_question(
                resolved_question, "accommodation", pending, payload.history
            )
        ):
            try:
                accommodation_response = await accommodation_queries.answer(
                    resolved_question,
                    request_id,
                    request_state.pending_clarification,
                    payload.history,
                    resolved_domain=accommodation_domain_resolved,
                    interpretation=conversation_turn.interpretation,
                    selected_canonical_ids=conversation_turn.selected_canonical_ids,
                    conversation_state=conversation_turn.state,
                    clarification_option_ids=clarification_option_ids,
                    result_page=payload.result_page,
                )
            except ResultPageResolutionError as exc:
                raise StarletteHTTPException(status_code=400) from exc
            if accommodation_response is not None:
                outcome = accommodation_queries.integrate_conversation(
                    accommodation_response,
                    resolved_question,
                    conversation_turn.state,
                    conversation_turn.interpretation,
                    payload.result_page,
                )
                request.state.conversation_state = outcome.state
                request.state.resource_query_trace = outcome.trace
                if resource_trace_sink is not None and outcome.trace is not None:
                    resource_trace_sink(outcome.trace)
                return _mark_response(request, outcome.response)

        support_domain_resolved = (
            conversation_turn.interpretation.domain == Domain.SUPPORT
            and (
                not conversation_turn.interpretation.requires_clarification
                or conversation_turn.interpretation.entity is None
            )
        )
        if support_queries is not None and (
            support_domain_resolved
            or is_plausible_resource_question(
                resolved_question, "support", pending, payload.history
            )
        ):
            support_response = await support_queries.answer(
                resolved_question,
                request_id,
                request_state.pending_clarification,
                payload.history,
                resolved_domain=support_domain_resolved,
                interpretation=conversation_turn.interpretation,
                selected_canonical_ids=conversation_turn.selected_canonical_ids,
                conversation_state=conversation_turn.state,
                clarification_option_ids=clarification_option_ids,
            )
            if support_response is not None:
                outcome = support_queries.integrate_conversation(
                    support_response,
                    resolved_question,
                    conversation_turn.state,
                    conversation_turn.interpretation,
                )
                request.state.conversation_state = outcome.state
                return _mark_response(request, outcome.response)

        structured_event_page = bool(
            payload.result_page is not None
            and any(
                item.result_set_id == payload.result_page.result_set_id
                and item.domain == Domain.EVENTS
                for item in conversation_turn.state.result_sets
            )
        )
        event_domain_resolved = structured_event_page or (
            conversation_turn.interpretation.domain == Domain.EVENTS
            and not conversation_turn.interpretation.requires_clarification
        )
        if event_queries is not None and (
            event_domain_resolved
            or is_plausible_event_question(resolved_question)
        ):
            try:
                event_response = await event_queries.answer(
                    resolved_question,
                    request_id,
                    interpretation=conversation_turn.interpretation,
                    selected_canonical_ids=conversation_turn.selected_canonical_ids,
                    conversation_state=conversation_turn.state,
                    result_page=payload.result_page,
                )
            except ResultPageResolutionError as exc:
                raise StarletteHTTPException(status_code=400) from exc
            outcome = event_queries.integrate_conversation(
                event_response,
                question=resolved_question,
                state=conversation_turn.state,
                interpretation=conversation_turn.interpretation,
                result_page=payload.result_page,
            )
            request.state.conversation_state = outcome.state
            return _mark_response(request, outcome.response)

        # Safe aliases are resolved only by the bounded V7 understanding
        # catalogue. Retrieval must consume that canonical identity on the same
        # turn rather than trying to independently fuzzy-match the user's text.
        #
        # Preserve the original wording so fact intent (for example
        # "prerequisites") is still planned normally; append only the approved
        # canonical course identifier.
        course_question = resolved_question
        course_entity = conversation_turn.interpretation.entity
        if (
            course_entity is not None
            and course_entity.domain == Domain.COURSES
            and course_entity.kind == EntityKind.COURSE
            and course_entity.resolution_basis == EntityResolutionBasis.SAFE_ALIAS
            and not conversation_turn.interpretation.requires_clarification
            and COURSE_CODE_CANDIDATE_PATTERN.search(course_question) is None
        ):
            course_question = (
                f"{course_question.rstrip()} {course_entity.canonical_id}"
            )

        course_response = await course_queries.answer(course_question, request_id)
        if course_response is not None:
            # When retrieval itself proves that this Course lookup resolved to
            # exactly one approved source record, preserve that record identity
            # for later conversational references. State remembers identity
            # only; institutional facts continue to come from repository data.
            response_sources = tuple(
                getattr(course_response, "sources", ()) or ()
            )
            if (
                isinstance(repository, CatalogReader)
                and course_entity is not None
                and course_entity.domain == Domain.COURSES
                and course_entity.kind == EntityKind.COURSE
                and len(response_sources) == 1
            ):
                source_record_id = getattr(
                    response_sources[0],
                    "record_id",
                    None,
                )
                if source_record_id is not None:
                    exact_record = _course_record_for_source_id(
                        repository,
                        source_record_id,
                        expected_code=course_entity.canonical_id,
                    )
                    if exact_record is not None:
                        exact_entity = course_entity.model_copy(
                            update={
                                "canonical_name": exact_record.title,
                                "source_record_id": exact_record.record_id,
                                "mentioned_turn": (
                                    request.state.conversation_state.turn_index
                                ),
                            }
                        )
                        request.state.conversation_state = remember_entity(
                            request.state.conversation_state,
                            exact_entity,
                        )

            course_records = (
                tuple(
                    record
                    for source in response_sources
                    if (
                        record := _course_record_for_source_id(
                            repository,
                            source.record_id,
                        )
                    )
                    is not None
                )
                if isinstance(repository, CatalogReader)
                else ()
            )
            if course_records:
                course_interpretation = conversation_turn.interpretation
                if (
                    len(course_records) > 1
                    and course_interpretation.intent is not None
                    and course_interpretation.intent.name == "compare"
                    and course_interpretation.domain is None
                ):
                    course_interpretation = course_interpretation.model_copy(
                        update={"domain": Domain.COURSES}
                    )
                presentation = integrate_course_presentation(
                    course_response,
                    course_records,
                    question=course_question,
                    state=request.state.conversation_state,
                    interpretation=course_interpretation,
                )
                request.state.conversation_state = presentation.state
                course_response = presentation.response

            return _mark_response(request, course_response)

        # Unsupported ANU/follow-up questions abstain rather than claiming facts.
        # The resolver may identify a referent, but never supplies factual evidence.
        if (
            COURSE_CODE_CANDIDATE_PATTERN.search(payload.question)
            or re.search(
                r"\b(?:ANU|course|courses|program|major|minor|speciali[sz]ation|"
                r"prerequisites?|requisites?|"
                r"scholarships?|accommodation|jobs?|events?|support)\b",
                payload.question,
                re.IGNORECASE,
            )
            or request_state.pending_clarification is not None
        ):
            return _mark_response(
                request,
                InsufficientEvidenceResponse(
                    answer="I do not have retrieved evidence to answer that question. "
                    "Please ask a standalone course prerequisite question with a course code.",
                    request_id=request_id,
                ),
            )
        return _mark_response(
            request,
            OffTopicResponse(
                answer="I can help with ANU course prerequisite questions. "
                "Please include a course code.",
                request_id=request_id,
            ),
        )

    return app


def create_configured_repository(settings: Settings) -> CourseProgramReader:
    """Select Cloud SQL for production without silently using fixture evidence."""

    if settings.environment == "production":
        try:
            return PostgresCourseProgramRepository.from_settings(settings)
        except DatabaseConfigurationError:
            return UnavailableCourseProgramRepository()

    if settings.course_records_path is not None:
        path = settings.course_records_path
        records = (
            load_common_records_directory(path)
            if path.is_dir()
            else (load_common_record_file(path),)
        )
        return CourseProgramRepository(records)
    return create_default_course_program_repository()


def create_configured_app() -> FastAPI:
    """Runtime entrypoint: explicit local data path and environment-based Gemini."""
    settings = Settings.from_environment()
    repository = create_configured_repository(settings)
    vector_retriever = None
    if settings.environment == "production" and settings.api_key.get_secret_value():
        try:
            connection = DatabaseConnectionConfig.from_settings(settings)
            embedder = GeminiEmbeddingProvider(
                settings.api_key.get_secret_value(),
                model=settings.embedding_model,
                dimension=settings.embedding_dimension,
                format_version=settings.retrieval_format_version,
                timeout_seconds=settings.timeout_seconds,
            )
            vector_retriever = PersistedSemanticRetriever(
                PostgresVectorRepository(connection.connect),
                embedder,
                top_k=settings.vector_top_k,
                min_score=settings.vector_min_score,
                max_units_per_record=settings.max_vector_units_per_record,
                dimension=settings.embedding_dimension,
                target_version=settings.embedding_version,
            )
        except (DatabaseConfigurationError, ValueError):
            vector_retriever = None
    reranker = None
    if settings.cohere_api_key.get_secret_value():
        reranker = CohereReranker(
            settings.cohere_api_key.get_secret_value(),
            model=settings.rerank_model,
            timeout_seconds=settings.rerank_timeout_seconds,
        )
    return create_app(
        repository,
        GeminiSynthesisClient(settings),
        timeout_seconds=settings.timeout_seconds,
        vector_retriever=vector_retriever,
        reranker=reranker,
        semantic_top_k=settings.semantic_top_k,
        semantic_min_score=settings.semantic_min_score,
        max_merged_candidates=settings.max_merged_candidates,
        evidence_top_k=settings.rerank_top_n,
        rrf_k=settings.rrf_k,
    )


# Legacy deterministic entrypoint. The Day 4 CLI uses create_configured_app.
# Importing this module/tests never reads .env or constructs a real SDK client.
app = create_app()
