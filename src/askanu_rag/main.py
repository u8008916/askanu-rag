"""Minimal Day 1 HTTP service for the frozen AskANU contracts."""

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from askanu_rag.models import (
    AskRequest,
    AskResponse,
    Clarification,
    ClarificationOption,
    ErrorResponse,
    HealthResponse,
    NeedsClarificationResponse,
    OkResponse,
    Source,
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


def create_app() -> FastAPI:
    app = FastAPI(title="AskANU RAG", version="0.1.0", debug=False)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        status_code = 413 if _is_oversized_input(exc.errors()) else 400
        return controlled_error_response(status_code)

    @app.exception_handler(Exception)
    async def internal_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return controlled_error_response(500)

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

        return OkResponse(
            answer="Mock response only. Retrieval and generation are not implemented.",
            sources=[
                Source(
                    record_id="course:COMP1110:2026",
                    source_id="programs-and-courses",
                    title="COMP1110 (mock contract data)",
                    url="https://programsandcourses.anu.edu.au/",
                    domain="courses",
                )
            ],
            request_id=new_request_id(),
        )

    return app


app = create_app()
