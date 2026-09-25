"""Small provider-neutral embedding boundary with a deterministic test double."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, Sequence

from google import genai
from google.genai import types


class EmbeddingProvider(Protocol):
    """Provider boundary; model/version live here, not in retrieval code."""

    model: str
    version: str

    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...


class EmbeddingProviderError(RuntimeError):
    """Safe provider boundary error without remote request details."""


class GeminiEmbeddingProvider:
    """Official Gemini Embedding 2 adapter with frozen 768-dimension output."""

    provider = "gemini"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-embedding-2",
        dimension: int = 768,
        format_version: str = "retrieval-format-v1",
        timeout_seconds: float = 20,
    ) -> None:
        if not api_key or not model.strip() or dimension != 768:
            raise ValueError("invalid frozen Gemini embedding configuration")
        if format_version != "retrieval-format-v1" or not 0 < timeout_seconds <= 30:
            raise ValueError("invalid embedding format or timeout")
        self._api_key = api_key
        self.model = model
        self.dimension = dimension
        self.version = f"{model}:{dimension}:{format_version}"
        self.timeout_seconds = timeout_seconds

    def _embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        try:
            contents = [
                types.Content(parts=[types.Part(text=text)]) for text in texts
            ]
            with genai.Client(
                api_key=self._api_key,
                vertexai=False,
                http_options=types.HttpOptions(
                    base_url="https://generativelanguage.googleapis.com",
                    timeout=int(self.timeout_seconds * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ) as client:
                response = client.models.embed_content(
                    model=self.model,
                    contents=contents,
                    config=types.EmbedContentConfig(
                        output_dimensionality=self.dimension
                    ),
                )
            embeddings = response.embeddings or []
            if len(embeddings) != len(texts):
                raise ValueError
            return tuple(
                validate_vector(item.values or (), dimension=self.dimension)
                for item in embeddings
            )
        except Exception:
            raise EmbeddingProviderError(
                "Embedding provider request failed."
            ) from None

    def embed_documents(
        self, texts: Sequence[str]
    ) -> tuple[tuple[float, ...], ...]:
        return self._embed(texts)

    def embed_query(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise ValueError("embedding query must not be blank")
        return self._embed((text,))[0]


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
