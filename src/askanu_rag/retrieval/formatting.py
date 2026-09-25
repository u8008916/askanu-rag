"""Versioned, deterministic text boundaries for retrieval providers."""

from __future__ import annotations

from dataclasses import dataclass

from askanu_rag.models import CommonRecord
from askanu_rag.retrieval.units import RetrievalUnit

RETRIEVAL_FORMAT_VERSION = "retrieval-format-v1"


@dataclass(frozen=True)
class ResolvedRetrievalRequest:
    """Bounded meaning sent to retrieval, never opaque conversation state."""

    question: str
    domain: str
    entity_id: str | None = None
    intent: str | None = None
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.question.strip() or not self.domain.strip():
            raise ValueError("resolved retrieval request requires query and domain")
        if len(self.question) > 8_192 or len(self.constraints) > 16:
            raise ValueError("resolved retrieval request exceeds bounds")


def _one_line(value: str) -> str:
    return " ".join(value.split())


def format_embedding_query(request: ResolvedRetrievalRequest) -> str:
    fields = ["task: question answering", f"domain: {_one_line(request.domain)}"]
    if request.intent:
        fields.append(f"intent: {_one_line(request.intent)}")
    if request.constraints:
        fields.append(
            "constraints: " + "; ".join(_one_line(item) for item in request.constraints)
        )
    fields.append(f"query: {_one_line(request.question)}")
    return " | ".join(fields)


def format_embedding_document(record: CommonRecord, unit: RetrievalUnit) -> str:
    """Format approved text only; identity/provenance remain application-owned."""

    return " | ".join(
        (
            f"title: {_one_line(record.title)}",
            f"text: {_one_line(unit.content)}",
        )
    )


def format_rerank_document(record: CommonRecord, unit_ids: tuple[str, ...]) -> str:
    """Format bounded candidate text without IDs, URLs or provenance metadata."""

    content = _one_line(record.content)[:4_000]
    return f"title: {_one_line(record.title)} | text: {content}"
