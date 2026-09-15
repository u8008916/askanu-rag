"""Deterministic retrieval-unit construction for persisted source records."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from askanu_rag.models import CommonRecord

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n+")


@dataclass(frozen=True)
class RetrievalUnit:
    """One stable, source-owned piece of text eligible for embedding."""

    source_record_id: str
    retrieval_unit_id: str
    source_content_hash: str
    retrieval_content_hash: str
    content: str


class RetrievalUnitBuilder:
    """Build units only from canonical ``content`` covered by ``content_hash``."""

    POLICY_VERSION = "content-paragraph-v1"

    def __init__(
        self,
        *,
        max_chars: int = 2_000,
        max_units: int = 20,
        policy_version: str = POLICY_VERSION,
    ) -> None:
        if max_chars < 256:
            raise ValueError("max_chars must be at least 256")
        if not 1 <= max_units <= 100:
            raise ValueError("max_units must be between 1 and 100")
        if not policy_version.strip():
            raise ValueError("policy_version must not be blank")
        self.max_chars = max_chars
        self.max_units = max_units
        # Chunking bounds are part of the persisted-index compatibility version.
        self.policy_version = (
            f"{policy_version.strip()}:chars={max_chars}:units={max_units}"
        )

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def build(self, record: CommonRecord) -> tuple[RetrievalUnit, ...]:
        body = record.content.strip()
        if len(body) <= self.max_chars:
            return (self._unit(record, "whole", body),)

        paragraphs = [
            " ".join(part.split())
            for part in _PARAGRAPH_BREAK.split(body)
            if part.strip()
        ]
        if not paragraphs:
            paragraphs = [" ".join(body.split())]

        chunks: list[str] = []
        current = ""
        available = self.max_chars
        for paragraph in paragraphs:
            pieces = self._bounded_pieces(paragraph, available)
            for piece in pieces:
                proposed = piece if not current else f"{current}\n\n{piece}"
                if len(proposed) <= available:
                    current = proposed
                else:
                    chunks.append(current)
                    current = piece
        if current:
            chunks.append(current)
        if len(chunks) > self.max_units:
            raise ValueError("record exceeds the configured retrieval-unit limit")
        return tuple(
            self._unit(record, f"chunk-{index:04d}", chunk)
            for index, chunk in enumerate(chunks, start=1)
        )

    @staticmethod
    def _bounded_pieces(paragraph: str, limit: int) -> tuple[str, ...]:
        if len(paragraph) <= limit:
            return (paragraph,)
        words = paragraph.split()
        pieces: list[str] = []
        current = ""
        for word in words:
            if len(word) > limit:
                if current:
                    pieces.append(current)
                    current = ""
                pieces.extend(
                    word[start : start + limit]
                    for start in range(0, len(word), limit)
                )
                continue
            proposed = word if not current else f"{current} {word}"
            if len(proposed) <= limit:
                current = proposed
            else:
                pieces.append(current)
                current = word
        if current:
            pieces.append(current)
        return tuple(pieces)

    def _unit(
        self, record: CommonRecord, retrieval_unit_id: str, content: str
    ) -> RetrievalUnit:
        return RetrievalUnit(
            source_record_id=record.record_id,
            retrieval_unit_id=retrieval_unit_id,
            source_content_hash=record.content_hash,
            retrieval_content_hash=self._hash(content),
            content=content,
        )
