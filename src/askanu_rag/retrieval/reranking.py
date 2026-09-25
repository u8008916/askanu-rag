"""Bounded relevance-only reranking provider boundary."""

from __future__ import annotations

import json
import math
import socket
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence
from urllib import error, request


@dataclass(frozen=True)
class RerankerDiagnostic:
    """Safe provider metadata; never contains credentials or request text."""

    category: str
    status_code: int | None = None
    request_id: str | None = None
    rate_limit_headers: tuple[tuple[str, str], ...] = ()
    model: str = ""
    query_chars: int = 0
    document_count: int = 0
    max_document_chars: int = 0
    top_n: int = 0


class RerankerError(RuntimeError):
    """Safe non-transient provider error without remote payload details."""

    def __init__(
        self, message: str, *, diagnostic: RerankerDiagnostic | None = None
    ) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic


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
        diagnostic_observer: Callable[[RerankerDiagnostic], None] | None = None,
    ) -> None:
        if not api_key or not model.strip() or not 0 < timeout_seconds <= 20:
            raise ValueError("invalid Cohere reranker configuration")
        self._api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._diagnostic_observer = diagnostic_observer

    def rerank(
        self, query: str, documents: Sequence[str], *, top_n: int
    ) -> tuple[RerankResult, ...]:
        if not query.strip() or not 1 <= len(documents) <= 20:
            raise ValueError("reranking requires a query and 1-20 documents")
        if not 1 <= top_n <= min(5, len(documents)):
            raise ValueError("rerank top_n is outside the frozen bound")
        shape = {
            "model": self.model,
            "query_chars": len(query),
            "document_count": len(documents),
            "max_document_chars": max(len(document) for document in documents),
            "top_n": top_n,
        }
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
        response_headers = None
        try:
            with request.urlopen(outgoing, timeout=self.timeout_seconds) as response:
                response_headers = getattr(response, "headers", None)
                raw_response = response.read().decode("utf-8")
        except error.HTTPError as exc:
            diagnostic = self._diagnostic(
                _http_category(exc.code),
                headers=exc.headers,
                status_code=exc.code,
                **shape,
            )
            if exc.code == 429 or 500 <= exc.code < 600:
                raise RerankerUnavailableError(
                    "Reranker is temporarily unavailable.",
                    diagnostic=diagnostic,
                ) from None
            raise RerankerError(
                "Reranker request was rejected.", diagnostic=diagnostic
            ) from None
        except (TimeoutError, socket.timeout):
            diagnostic = self._diagnostic("timeout", **shape)
            raise RerankerUnavailableError(
                "Reranker is temporarily unavailable.", diagnostic=diagnostic
            ) from None
        except (error.URLError, OSError):
            diagnostic = self._diagnostic("network", **shape)
            raise RerankerUnavailableError(
                "Reranker is temporarily unavailable.", diagnostic=diagnostic
            ) from None

        try:
            decoded = json.loads(raw_response)
        except json.JSONDecodeError:
            diagnostic = self._diagnostic(
                "invalid_response", headers=response_headers, status_code=200, **shape
            )
            raise RerankerUnavailableError(
                "Reranker is temporarily unavailable.", diagnostic=diagnostic
            ) from None

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
            self._diagnostic(
                "success", headers=response_headers, status_code=200, **shape
            )
            return results
        except (KeyError, TypeError, ValueError, OverflowError):
            diagnostic = self._diagnostic(
                "invalid_response", headers=response_headers, status_code=200, **shape
            )
            raise RerankerError(
                "Reranker returned an invalid response.", diagnostic=diagnostic
            ) from None

    def _diagnostic(
        self,
        category: str,
        *,
        headers=None,
        status_code: int | None = None,
        model: str,
        query_chars: int,
        document_count: int,
        max_document_chars: int,
        top_n: int,
    ) -> RerankerDiagnostic:
        diagnostic = RerankerDiagnostic(
            category=category,
            status_code=status_code,
            request_id=_first_header(
                headers, "x-request-id", "request-id", "x-correlation-id"
            ),
            rate_limit_headers=tuple(
                (name, value)
                for name in (
                    "retry-after",
                    "x-ratelimit-limit",
                    "x-ratelimit-remaining",
                    "x-ratelimit-reset",
                )
                if (value := _header(headers, name)) is not None
            ),
            model=model,
            query_chars=query_chars,
            document_count=document_count,
            max_document_chars=max_document_chars,
            top_n=top_n,
        )
        if self._diagnostic_observer is not None:
            try:
                self._diagnostic_observer(diagnostic)
            except Exception:
                pass
        return diagnostic


def _http_category(status_code: int) -> str:
    if status_code in {401, 403, 498}:
        return "auth"
    if status_code == 404:
        return "model_not_found"
    if status_code == 429:
        return "rate_limit"
    if 500 <= status_code < 600:
        return "server_error"
    if 400 <= status_code < 500:
        return "invalid_request"
    return "unknown"


def _header(headers, name: str) -> str | None:
    if headers is None:
        return None
    try:
        value = headers.get(name)
    except Exception:
        return None
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized[:500] if normalized else None


def _first_header(headers, *names: str) -> str | None:
    return next(
        (value for name in names if (value := _header(headers, name)) is not None),
        None,
    )
