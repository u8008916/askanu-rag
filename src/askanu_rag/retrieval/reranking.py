"""Bounded relevance-only reranking provider boundary."""

from __future__ import annotations

import json
import math
import socket
from dataclasses import dataclass
from typing import Protocol, Sequence
from urllib import error, request


class RerankerError(RuntimeError):
    """Safe non-transient provider error without remote payload details."""


class RerankerUnavailableError(RerankerError):
    """Transient provider failure for which deterministic RRF is safe."""


@dataclass(frozen=True)
class RerankResult:
    index: int
    relevance_score: float


class Reranker(Protocol):
    def rerank(
        self, query: str, documents: Sequence[str], *, top_n: int
    ) -> tuple[RerankResult, ...]: ...


class CohereReranker:
    """Cohere v2 adapter; sends only a query and bounded candidate strings."""

    endpoint = "https://api.cohere.ai/v2/rerank"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "rerank-v4.0-fast",
        timeout_seconds: float = 5,
    ) -> None:
        if not api_key or not model.strip() or not 0 < timeout_seconds <= 20:
            raise ValueError("invalid Cohere reranker configuration")
        self._api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def rerank(
        self, query: str, documents: Sequence[str], *, top_n: int
    ) -> tuple[RerankResult, ...]:
        if not query.strip() or not 1 <= len(documents) <= 20:
            raise ValueError("reranking requires a query and 1-20 documents")
        if not 1 <= top_n <= min(5, len(documents)):
            raise ValueError("rerank top_n is outside the frozen bound")
        payload = json.dumps(
            {
                "model": self.model,
                "query": query,
                "documents": list(documents),
                "top_n": top_n,
                "max_tokens_per_doc": 4096,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        outgoing = request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "X-Client-Name": "askanu-rag",
            },
            method="POST",
        )
        try:
            with request.urlopen(outgoing, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code == 429 or 500 <= exc.code < 600:
                raise RerankerUnavailableError("Reranker is temporarily unavailable.") from None
            raise RerankerError("Reranker request was rejected.") from None
        except (error.URLError, TimeoutError, socket.timeout, OSError, json.JSONDecodeError):
            raise RerankerUnavailableError("Reranker is temporarily unavailable.") from None

        try:
            results = tuple(
                RerankResult(int(item["index"]), float(item["relevance_score"]))
                for item in decoded["results"]
            )
            indices = [item.index for item in results]
            if (
                len(results) != top_n
                or len(set(indices)) != len(indices)
                or any(index < 0 or index >= len(documents) for index in indices)
                or any(not math.isfinite(item.relevance_score) for item in results)
            ):
                raise ValueError
            return results
        except (KeyError, TypeError, ValueError, OverflowError):
            raise RerankerError("Reranker returned an invalid response.") from None
