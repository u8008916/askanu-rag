"""Small provider-neutral embedding boundary with a deterministic test double."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, Sequence


class EmbeddingProvider(Protocol):
    """Provider boundary; model/version live here, not in retrieval code."""

    model: str
    version: str

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...


def validate_vector(vector: Sequence[float], *, dimension: int | None = None) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("embedding must contain finite values")
    if dimension is not None and len(values) != dimension:
        raise ValueError("embedding dimension does not match configuration")
    return values


class DeterministicFakeEmbedder:
    """Stable token-hash embeddings for tests only; never a production provider."""

    model = "deterministic-fake"

    def __init__(self, *, dimension: int = 16, version: str = "test-v1") -> None:
        if not 2 <= dimension <= 2_048:
            raise ValueError("dimension must be between 2 and 2048")
        self.dimension = dimension
        self.version = version
        self.document_calls = 0
        self.query_calls = 0

    def _embed(self, text: str) -> tuple[float, ...]:
        values = [0.0] * self.dimension
        for token in re.findall(r"[a-z0-9]+", text.casefold()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            values[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0:
            values[0] = 1.0
            norm = 1.0
        return tuple(value / norm for value in values)

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        self.document_calls += len(texts)
        return tuple(self._embed(text) for text in texts)

    def embed_query(self, text: str) -> tuple[float, ...]:
        self.query_calls += 1
        return self._embed(text)
