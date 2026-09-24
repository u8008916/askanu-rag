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
from askanu_rag.database import DatabaseConfigurationError, RepositoryUnavailableError
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
from askanu_rag.resource_queries import (
    DomainResourceQueryService,
    is_plausible_resource_question,
)
from askanu_rag.retrieval.catalog import CatalogReader
from askanu_rag.synthesis import SynthesisClient, SynthesisError
from askanu_rag.models import (
    AskRequest,
    AskResponse,
    Clarification,
    ClarificationOption,
    CurrentJobsResponse,
    ErrorResponse,
    HealthResponse,
    InsufficientEvidenceResponse,
    NeedsClarificationResponse,
    OffTopicResponse,
    UpcomingEventsResponse,
)
from askanu_rag.models.conversation_state import ConversationState
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
    ScholarshipQueryService,
    is_plausible_scholarship_question,
)
from askanu_rag.state_transitions import (
    pending_from_public_clarification,
    set_pending_clarification,
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

    payload = ErrorResponse(
        answer=SAFE_ERROR_ANSWER,
        request_id=request_id or new_request_id(),
        conversation_state=conversation_state or ConversationState(),
    )
    content = payload.model_dump(mode="json")
    if not include_conversation_state:
        content.pop("conversation_state")
    return JSONResponse(status_code=status_code, content=content)


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
    response = response.model_copy(update={"conversation_state": state})
    request.state.response_status = response.status
    return response


def _is_oversized_input(errors: Sequence[dict[str, Any]]) -> bool:
    """Identify only the two frozen size-limit validation failures."""

    for error in errors:
        location = tuple(error.get("loc", ()))
        error_type = error.get("type")
        if location == ("body", "question") and error_type == "string_too_long":
            return True
        if location == ("body", "history") and error_type == "too_long":
            return True
    return False


def create_app(
    repository: CourseProgramReader | None = None,
    synthesis_client: SynthesisClient | None = None,
    *,
    timeout_seconds: float = 30,
    semantic_retriever=None,
    vector_retriever=None,
    semantic_top_k: int = 3,
    semantic_min_score: float = 0.2,
    jobs_today_provider: Callable[[], date] | None = None,
    events_now_provider: Callable[[], datetime] | None = None,
    max_merged_candidates: int = 10,
) -> FastAPI:
    """Inject providers explicitly; omission preserves the deterministic test path."""
    app = FastAPI(title="AskANU RAG", version="0.1.0", debug=False)
    repository = repository if repository is not None else create_default_course_program_repository()
    if isinstance(repository, CatalogReader):
        course_queries = HybridQueryService(repository, synthesis_client, semantic_retriever,
            vector_retriever=vector_retriever, timeout_seconds=timeout_seconds,
            top_k=semantic_top_k, min_score=semantic_min_score,
            max_candidates=max_merged_candidates)
    else:
        course_queries = CourseQueryService(repository, synthesis_client, timeout_seconds)
    scholarship_queries = (
        ScholarshipQueryService(
            repository,
            vector_retriever,
            max_candidates=max_merged_candidates,
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
            max_candidates=max_merged_candidates,
            min_score=semantic_min_score,
        )
        if isinstance(repository, JobReader)
        else None
    )
    accommodation_queries = (
        DomainResourceQueryService(
            repository,
            "accommodation",
            vector_retriever,
            max_candidates=max_merged_candidates,
        )
        if isinstance(repository, ResourceReader)
        else None
    )
    support_queries = (
        DomainResourceQueryService(
            repository,
            "support",
            vector_retriever,
            max_candidates=max_merged_candidates,
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
        return controlled_error_response(
            status_code,
            _request_id(_request),
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
        conversation_turn = orchestrate_turn(
            payload.question,
            payload.history,
            payload.conversation_state,
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
        if isinstance(repository, CatalogReader):
            resolution = resolve_current_session(payload, repository)
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

        pending = payload.conversation_state.pending_clarification
        if job_queries is not None and is_plausible_job_question(
            resolved_question, pending
        ):
            job_response = await job_queries.answer(
                resolved_question,
                request_id,
                payload.conversation_state.pending_clarification,
                payload.history,
            )
            if job_response is not None:
                return _mark_response(request, job_response)

        if scholarship_queries is not None and is_plausible_scholarship_question(
            resolved_question, pending
        ):
            scholarship_response = await scholarship_queries.answer(
                resolved_question,
                request_id,
                payload.conversation_state.pending_clarification,
            )
            if scholarship_response is not None:
                return _mark_response(request, scholarship_response)

        if accommodation_queries is not None and is_plausible_resource_question(
            resolved_question, "accommodation", pending, payload.history
        ):
            accommodation_response = await accommodation_queries.answer(
                resolved_question,
                request_id,
                payload.conversation_state.pending_clarification,
                payload.history,
            )
            if accommodation_response is not None:
                return _mark_response(request, accommodation_response)

        if support_queries is not None and is_plausible_resource_question(
            resolved_question, "support", pending, payload.history
        ):
            support_response = await support_queries.answer(
                resolved_question,
                request_id,
                payload.conversation_state.pending_clarification,
                payload.history,
            )
            if support_response is not None:
                return _mark_response(request, support_response)

        if event_queries is not None and is_plausible_event_question(
            resolved_question
        ):
            return _mark_response(
                request,
                await event_queries.answer(resolved_question, request_id),
            )

        course_response = await course_queries.answer(resolved_question, request_id)
        if course_response is not None:
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
            or payload.conversation_state.pending_clarification is not None
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
    return create_app(
        repository,
        GeminiSynthesisClient(settings),
        timeout_seconds=settings.timeout_seconds,
        semantic_top_k=settings.semantic_top_k,
        semantic_min_score=settings.semantic_min_score,
        max_merged_candidates=settings.max_merged_candidates,
    )


# Legacy deterministic entrypoint. The Day 4 CLI uses create_configured_app.
# Importing this module/tests never reads .env or constructs a real SDK client.
app = create_app()
