"""AskANU HTTP service with exact-first, grounded Day 4 synthesis."""

from collections.abc import Sequence
import re
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from askanu_rag.course_queries import COURSE_CODE_CANDIDATE_PATTERN, CourseQueryService
from askanu_rag.config import Settings
from askanu_rag.gemini import GeminiSynthesisClient
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
    load_course_program_record_file,
    load_course_program_records_directory,
)

MOCK_CLARIFICATION_TRIGGER = "mock:needs_clarification"
SAFE_ERROR_ANSWER = "The request could not be completed."


def new_request_id() -> str:
    """Return an opaque request identifier with no internal state."""

    return f"req_{uuid4().hex}"


def controlled_error_response(status_code: int) -> JSONResponse:
    """Build the frozen error envelope for controlled HTTP failures."""

    payload = ErrorResponse(answer=SAFE_ERROR_ANSWER, request_id=new_request_id())
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


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
) -> FastAPI:
    """Inject providers explicitly; omission preserves the deterministic test path."""
    app = FastAPI(title="AskANU RAG", version="0.1.0", debug=False)
    course_queries = CourseQueryService(
        repository
        if repository is not None
        else create_default_course_program_repository(),
        synthesis_client=synthesis_client,
        timeout_seconds=timeout_seconds,
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        status_code = 413 if _is_oversized_input(exc.errors()) else 400
        return controlled_error_response(status_code)

    @app.exception_handler(Exception)
    async def internal_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return controlled_error_response(500)

    @app.exception_handler(SynthesisError)
    async def synthesis_error_handler(
        _request: Request, _exc: SynthesisError
    ) -> JSONResponse:
        # Handled explicitly so ASGI does not log provider exception tracebacks.
        return controlled_error_response(502)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/api/v1/ask", response_model=AskResponse)
    async def ask(request: AskRequest) -> AskResponse:
        # Temporary Day 1 mock hook. It is not query-planning behaviour.
        if request.question == MOCK_CLARIFICATION_TRIGGER:
            return NeedsClarificationResponse(
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
                request_id=new_request_id(),
            )

        request_id = new_request_id()
        course_response = await course_queries.answer(request.question, request_id)
        if course_response is not None:
            return course_response

        # Unsupported ANU/follow-up questions abstain rather than claiming facts.
        # No broad planner/history resolver is introduced in this Day 4 slice.
        if (
            COURSE_CODE_CANDIDATE_PATTERN.search(request.question)
            or re.search(
                r"\b(?:ANU|course|courses|program|prerequisites?|requisites?|"
                r"scholarships?|accommodation|jobs?|events?|support)\b",
                request.question,
                re.IGNORECASE,
            )
            or request.conversation_state.pending_clarification is not None
        ):
            return InsufficientEvidenceResponse(
                answer="I do not have retrieved evidence to answer that question. "
                "Please ask a standalone course prerequisite question with a course code.",
                request_id=request_id,
            )
        return OffTopicResponse(
            answer="I can help with ANU course prerequisite questions. "
            "Please include a course code.",
            request_id=request_id,
        )

    return app


def create_configured_app() -> FastAPI:
    """Runtime entrypoint: explicit local data path and environment-based Gemini."""
    settings = Settings.from_environment()
    repository = None
    if settings.course_records_path is not None:
        path = settings.course_records_path
        records = (
            load_course_program_records_directory(path)
            if path.is_dir()
            else (load_course_program_record_file(path),)
        )
        repository = CourseProgramRepository(records)
    return create_app(
        repository,
        GeminiSynthesisClient(settings),
        timeout_seconds=settings.timeout_seconds,
    )


# Legacy deterministic entrypoint. The Day 4 CLI uses create_configured_app.
# Importing this module/tests never reads .env or constructs a real SDK client.
app = create_app()
