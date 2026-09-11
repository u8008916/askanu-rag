"""AskANU HTTP service with exact-first, grounded Day 4 synthesis."""

from collections.abc import Sequence
import logging
import re
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from askanu_rag.course_queries import COURSE_CODE_CANDIDATE_PATTERN, CourseQueryService
from askanu_rag.config import Settings
from askanu_rag.database import DatabaseConfigurationError
from askanu_rag.gemini import GeminiSynthesisClient
from askanu_rag.hybrid_queries import HybridQueryService
from askanu_rag.retrieval.catalog import CatalogReader
from askanu_rag.synthesis import SynthesisClient, SynthesisError
from askanu_rag.models import (
    AskRequest,
    AskResponse,
    Clarification,
    ClarificationOption,
    ErrorResponse,
    HealthResponse,
    NeedsClarificationResponse,
    InsufficientEvidenceResponse,
    OffTopicResponse,
)
from askanu_rag.retrieval import (
    CourseProgramReader,
    create_default_course_program_repository,
    CourseProgramRepository,
    PostgresCourseProgramRepository,
    UnavailableCourseProgramRepository,
    load_course_program_record_file,
    load_course_program_records_directory,
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
    status_code: int, request_id: str | None = None
) -> JSONResponse:
    """Build the frozen error envelope for controlled HTTP failures."""

    payload = ErrorResponse(
        answer=SAFE_ERROR_ANSWER, request_id=request_id or new_request_id()
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


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
    semantic_top_k: int = 3,
    semantic_min_score: float = 0.2,
) -> FastAPI:
    """Inject providers explicitly; omission preserves the deterministic test path."""
    app = FastAPI(title="AskANU RAG", version="0.1.0", debug=False)
    repository = repository if repository is not None else create_default_course_program_repository()
    if isinstance(repository, CatalogReader):
        course_queries = HybridQueryService(repository, synthesis_client, semantic_retriever,
            timeout_seconds=timeout_seconds, top_k=semantic_top_k, min_score=semantic_min_score)
    else:
        course_queries = CourseQueryService(repository, synthesis_client, timeout_seconds)

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
        return controlled_error_response(status_code, _request_id(_request))

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        _request.state.response_status = "error"
        return controlled_error_response(exc.status_code, _request_id(_request))

    @app.exception_handler(Exception)
    async def internal_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        _request.state.response_status = "error"
        return controlled_error_response(500, _request_id(_request))

    @app.exception_handler(SynthesisError)
    async def synthesis_error_handler(
        _request: Request, _exc: SynthesisError
    ) -> JSONResponse:
        # Handled explicitly so ASGI does not log provider exception tracebacks.
        _request.state.response_status = "error"
        return controlled_error_response(502, _request_id(_request))

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/api/v1/ask", response_model=AskResponse)
    async def ask(payload: AskRequest, request: Request) -> AskResponse:
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
        course_response = await course_queries.answer(payload.question, request_id)
        if course_response is not None:
            return _mark_response(request, course_response)

        # Unsupported ANU/follow-up questions abstain rather than claiming facts.
        # No broad planner/history resolver is introduced in this Day 4 slice.
        if (
            COURSE_CODE_CANDIDATE_PATTERN.search(payload.question)
            or re.search(
                r"\b(?:ANU|course|courses|program|prerequisites?|requisites?|"
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
            load_course_program_records_directory(path)
            if path.is_dir()
            else (load_course_program_record_file(path),)
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
    )


# Legacy deterministic entrypoint. The Day 4 CLI uses create_configured_app.
# Importing this module/tests never reads .env or constructs a real SDK client.
app = create_app()
