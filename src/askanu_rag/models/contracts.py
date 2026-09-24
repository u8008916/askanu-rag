"""Frozen V3 request and response contracts."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from askanu_rag.models.conversation_state import ConversationState
from askanu_rag.transport_limits import (
    HISTORY_MAX_BYTES,
    HISTORY_TURN_CONTENT_MAX_CHARS,
    HISTORY_TURN_ID_MAX_CHARS,
    QUESTION_MAX_UTF8_BYTES,
    STATE_MAX_BYTES,
    validate_serialized_limit,
    validate_utf8_text_limit,
)

MAX_QUESTION_CHARS = 2_000
MAX_HISTORY_TURNS = 10


class ContractModel(BaseModel):
    """Base model that rejects undocumented fields."""

    model_config = ConfigDict(extra="forbid")


class HistoryTurn(ContractModel):
    turn_id: str = Field(max_length=HISTORY_TURN_ID_MAX_CHARS)
    role: Literal["user", "assistant"]
    content: str = Field(max_length=HISTORY_TURN_CONTENT_MAX_CHARS)


class ClarificationOption(ContractModel):
    id: str
    label: str


class Clarification(ContractModel):
    id: str
    type: str
    options: list[ClarificationOption]
    allow_multiple: bool


class AskRequest(ContractModel):
    question: str = Field(max_length=MAX_QUESTION_CHARS)
    history: list[HistoryTurn] = Field(max_length=MAX_HISTORY_TURNS)
    conversation_state: ConversationState = Field(default_factory=ConversationState)

    @field_validator("question")
    @classmethod
    def question_fits_utf8_budget(cls, value: str) -> str:
        return validate_utf8_text_limit(
            value, QUESTION_MAX_UTF8_BYTES, "question"
        )

    @field_validator("history", mode="before")
    @classmethod
    def submitted_history_fits_serialized_budget(cls, value: Any) -> Any:
        return validate_serialized_limit(value, HISTORY_MAX_BYTES, "history")

    @field_validator("history")
    @classmethod
    def history_fits_serialized_budget(
        cls, value: list[HistoryTurn]
    ) -> list[HistoryTurn]:
        return validate_serialized_limit(value, HISTORY_MAX_BYTES, "history")

    @field_validator("conversation_state", mode="before")
    @classmethod
    def submitted_state_fits_serialized_budget(cls, value: Any) -> Any:
        return validate_serialized_limit(
            value, STATE_MAX_BYTES, "conversation_state"
        )

    @field_validator("conversation_state")
    @classmethod
    def state_fits_serialized_budget(
        cls, value: ConversationState
    ) -> ConversationState:
        return validate_serialized_limit(
            value, STATE_MAX_BYTES, "conversation_state"
        )


class Source(ContractModel):
    record_id: str
    source_id: str
    title: str
    url: HttpUrl
    domain: str


class ResponseBody(ContractModel):
    answer: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    request_id: str
    conversation_state: ConversationState = Field(default_factory=ConversationState)

    @field_validator("conversation_state")
    @classmethod
    def state_fits_serialized_budget(
        cls, value: ConversationState
    ) -> ConversationState:
        return validate_serialized_limit(
            value, STATE_MAX_BYTES, "conversation_state"
        )


class OkResponse(ResponseBody):
    status: Literal["ok"] = "ok"
    clarification: None = None


class PartialResponse(ResponseBody):
    status: Literal["partial"] = "partial"
    clarification: None = None


class NeedsClarificationResponse(ResponseBody):
    status: Literal["needs_clarification"] = "needs_clarification"
    clarification: Clarification


class InsufficientEvidenceResponse(ResponseBody):
    status: Literal["insufficient_evidence"] = "insufficient_evidence"
    clarification: None = None


class OffTopicResponse(ResponseBody):
    status: Literal["off_topic"] = "off_topic"
    clarification: None = None


class ErrorResponse(ResponseBody):
    status: Literal["error"] = "error"
    clarification: None = None


AskResponse = Annotated[
    OkResponse
    | PartialResponse
    | NeedsClarificationResponse
    | InsufficientEvidenceResponse
    | OffTopicResponse
    | ErrorResponse,
    Field(discriminator="status"),
]


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"


class CurrentJobItem(ContractModel):
    """Minimal source-grounded DTO for the deterministic Current Jobs list."""

    record_id: str
    source_id: str
    job_id: str
    title: str
    employment_types: list[str]
    location: str | None
    classification: str | None
    salary: str | None
    closing_text: str | None
    closing_date: str | None
    closing_at: str | None
    status: Literal["current"]
    url: HttpUrl
    domain: Literal["jobs"]


class CurrentJobsResponse(ContractModel):
    status: Literal["ok"] = "ok"
    items: list[CurrentJobItem]
    request_id: str


class UpcomingEventItem(ContractModel):
    """Source-grounded DTO for the official Upcoming Events surface."""

    record_id: str
    source_id: Literal["events_anu_official"]
    title: str
    start_at: str
    end_at: str | None
    venue: str | None
    organiser: str | None
    status: str | None
    url: HttpUrl
    domain: Literal["events"]


class UpcomingEventsResponse(ContractModel):
    status: Literal["ok"] = "ok"
    items: list[UpcomingEventItem]
    request_id: str
