"""Frozen V3 request and response contracts."""

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from askanu_rag.models.conversation_state import (
    MAX_CLARIFICATION_OPTIONS,
    MAX_RESULT_IDENTITIES,
    AnswerState,
    ConversationState,
)
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


class ClarificationSelection(ContractModel):
    """Reusable client selection for the current pending clarification only."""

    clarification_id: str = Field(min_length=1, max_length=200)
    option_ids: list[str] = Field(
        min_length=1,
        max_length=MAX_CLARIFICATION_OPTIONS,
    )

    @field_validator("option_ids")
    @classmethod
    def option_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("clarification option IDs must be unique")
        return value


class ResultSelection(ContractModel):
    """Untrusted clicked-result context, revalidated by RAG before use."""

    result_set_id: str = Field(min_length=1, max_length=200)
    canonical_id: str = Field(min_length=1, max_length=200)
    ordinal: int = Field(strict=True, ge=1, le=MAX_RESULT_IDENTITIES)


class ResultPageRequest(ContractModel):
    """Bounded presentation request over one authoritative retained ResultSet."""

    result_set_id: str = Field(min_length=1, max_length=200)
    start_ordinal: int = Field(
        strict=True, ge=1, le=MAX_RESULT_IDENTITIES + 1
    )
    limit: int = Field(strict=True, ge=1, le=5)


class AskRequest(ContractModel):
    question: str = Field(max_length=MAX_QUESTION_CHARS)
    history: list[HistoryTurn] = Field(max_length=MAX_HISTORY_TURNS)
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    selected_result: ResultSelection | None = None
    clarification_selection: ClarificationSelection | None = None
    result_page: ResultPageRequest | None = None

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

    @model_validator(mode="after")
    def selections_reference_current_state(self) -> "AskRequest":
        if self.selected_result is not None:
            selection = self.selected_result
            result_set = next(
                (
                    item
                    for item in self.conversation_state.result_sets
                    if item.result_set_id == selection.result_set_id
                ),
                None,
            )
            if result_set is None:
                raise ValueError("selected result set is not retained")
            index = selection.ordinal - 1
            if (
                index >= len(result_set.ordered_canonical_ids)
                or result_set.ordered_canonical_ids[index]
                != selection.canonical_id
            ):
                raise ValueError("selected result ordinal and identity must agree")
        if self.clarification_selection is not None:
            selection = self.clarification_selection
            pending = self.conversation_state.pending_clarification
            if pending is None or pending.id != selection.clarification_id:
                raise ValueError("clarification selection is stale")
            current_ids = {option.id for option in pending.options}
            if not set(selection.option_ids).issubset(current_ids):
                raise ValueError("clarification selection contains a foreign option")
            if len(selection.option_ids) > 1 and not pending.allow_multiple:
                raise ValueError("clarification does not allow multiple selections")
        if self.result_page is not None:
            page = self.result_page
            result_set = next(
                (
                    item
                    for item in self.conversation_state.result_sets
                    if item.result_set_id == page.result_set_id
                ),
                None,
            )
            if result_set is None:
                raise ValueError("result page set is not retained")
            if result_set.status.value != "RESULTS":
                raise ValueError("result page requires a RESULTS result set")
            if (
                self.conversation_state.focus is None
                or self.conversation_state.focus.result_set_id
                != page.result_set_id
            ):
                raise ValueError("result page set is stale or foreign to current focus")
            cursor = self.conversation_state.result_page
            if cursor is None or cursor.result_set_id != page.result_set_id:
                raise ValueError("result page cursor is not current")
            if page.start_ordinal != cursor.next_ordinal:
                raise ValueError("result page start must match the server cursor")
            if page.start_ordinal > len(result_set.ordered_canonical_ids) + 1:
                raise ValueError("result page start exceeds the retained ordering")
        return self


class Source(ContractModel):
    record_id: str
    source_id: str
    title: str
    url: HttpUrl
    domain: str


PublicFieldValue = str | list[str] | None


class PublicRoomRateEvidence(ContractModel):
    """One named room whose published weekly rate proved a numeric match."""

    type: Literal["room_rate"] = "room_rate"
    room_name: str
    rate: str
    cost_period: str
    contract: str | None
    inclusions: str | None
    other_fees: str | None


class PublicResultItem(ContractModel):
    """Reusable ordered result card backed by one approved stored record."""

    type: Literal["result"] = "result"
    record_id: str
    source_id: str
    canonical_id: str
    title: str
    url: HttpUrl
    domain: str
    result_set_id: str | None = None
    ordinal: int | None = Field(default=None, strict=True, ge=1)
    fields: dict[str, PublicFieldValue] = Field(default_factory=dict)
    qualifying_evidence: PublicRoomRateEvidence | None = None


class PublicComparisonValue(ContractModel):
    record_id: str
    value: PublicFieldValue
    state: Literal["published", "not_published"]


class PublicComparisonField(ContractModel):
    name: str
    label: str
    values: list[PublicComparisonValue]


class PublicComparisonItem(ContractModel):
    """Backend-authored comparison; clients never infer rows from prose."""

    type: Literal["comparison"] = "comparison"
    result_set_id: str | None = None
    records: list[PublicResultItem]
    fields: list[PublicComparisonField]


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


class PublicJobItem(CurrentJobItem):
    """Typed Jobs shape used only inside the shared Ask response."""

    type: Literal["job"] = "job"


PublicItem = Annotated[
    PublicResultItem | PublicComparisonItem | PublicJobItem,
    Field(discriminator="type"),
]


class ResultPage(ContractModel):
    """Server-authored metadata for one stable ResultSet presentation page."""

    result_set_id: str
    start_ordinal: int = Field(strict=True, ge=1, le=MAX_RESULT_IDENTITIES + 1)
    returned: int = Field(strict=True, ge=0, le=5)
    has_more: bool
    next_ordinal: int | None = Field(
        default=None, strict=True, ge=1, le=MAX_RESULT_IDENTITIES
    )

    @model_validator(mode="after")
    def page_metadata_is_consistent(self) -> "ResultPage":
        expected = self.start_ordinal + self.returned
        if self.has_more and self.next_ordinal != expected:
            raise ValueError("continued page requires the next contiguous ordinal")
        if not self.has_more and self.next_ordinal is not None:
            raise ValueError("terminal page cannot advertise another ordinal")
        return self


class ResponseAction(ContractModel):
    """Validated backend action; never synthesized from answer or user text."""

    type: Literal["application"]
    label: str
    url: HttpUrl
    record_id: str
    source_id: str


class ResponseBody(ContractModel):
    answer: str
    items: list[PublicItem] = Field(default_factory=list)
    answer_state: AnswerState | None = None
    actions: list[ResponseAction] = Field(default_factory=list)
    result_page: ResultPage | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
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
