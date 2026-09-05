"""Frozen V3 request and response contracts."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

MAX_QUESTION_CHARS = 2_000
MAX_HISTORY_TURNS = 10


class ContractModel(BaseModel):
    """Base model that rejects undocumented fields."""

    model_config = ConfigDict(extra="forbid")


class HistoryTurn(ContractModel):
    turn_id: str
    role: Literal["user", "assistant"]
    content: str


class ClarificationOption(ContractModel):
    id: str
    label: str


class Clarification(ContractModel):
    id: str
    type: str
    options: list[ClarificationOption]
    allow_multiple: bool


class ConversationState(ContractModel):
    pending_clarification: Clarification | None


class AskRequest(ContractModel):
    question: str = Field(max_length=MAX_QUESTION_CHARS)
    history: list[HistoryTurn] = Field(max_length=MAX_HISTORY_TURNS)
    conversation_state: ConversationState


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
