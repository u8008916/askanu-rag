from __future__ import annotations

import io
import json
import socket
from email.message import Message
from urllib import error

import pytest

from askanu_rag.retrieval.hybrid import SharedHybridRetriever
from askanu_rag.retrieval.reranking import (
    CohereReranker,
    RerankerError,
    RerankerUnavailableError,
)
from test_grounded_synthesis import record


def _http_error(status: int, headers: dict[str, str] | None = None):
    values = Message()
    for name, value in (headers or {}).items():
        values[name] = value
    return error.HTTPError(
        "https://api.cohere.ai/v2/rerank",
        status,
        "provider error",
        values,
        io.BytesIO(b'{"message":"redacted provider body"}'),
    )


@pytest.mark.parametrize("status", (401, 403, 498))
def test_cohere_auth_errors_are_safe_and_distinguishable(monkeypatch, status):
    monkeypatch.setattr(
        "askanu_rag.retrieval.reranking.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(_http_error(status)),
    )

    with pytest.raises(RerankerError) as caught:
        CohereReranker("test-key").rerank("query", ("document",), top_n=1)

    assert not isinstance(caught.value, RerankerUnavailableError)
    assert caught.value.diagnostic.category == "auth"
    assert caught.value.diagnostic.status_code == status
    assert "redacted" not in str(caught.value)


def test_cohere_rate_limit_has_safe_headers_and_still_falls_back(monkeypatch):
    monkeypatch.setattr(
        "askanu_rag.retrieval.reranking.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            _http_error(
                429,
                {
                    "x-request-id": "safe-request-id",
                    "retry-after": "6",
                    "x-ratelimit-remaining": "0",
                    "authorization": "must-not-appear",
                },
            )
        ),
    )
    reranker = CohereReranker("test-key")

    with pytest.raises(RerankerUnavailableError) as caught:
        reranker.rerank("query", ("document",), top_n=1)

    diagnostic = caught.value.diagnostic
    assert diagnostic.category == "rate_limit"
    assert diagnostic.status_code == 429
    assert diagnostic.request_id == "safe-request-id"
    assert dict(diagnostic.rate_limit_headers) == {
        "retry-after": "6",
        "x-ratelimit-remaining": "0",
    }
    assert "authorization" not in dict(diagnostic.rate_limit_headers)

    selected = SharedHybridRetriever().select(
        query="query",
        sparse=((record(), 1.0),),
        reranker=reranker,
        top_n=1,
    )
    assert selected.reranker_fallback is True
    assert selected.provider_error_category == "rate_limit"
    assert len(selected.candidates) == 1


def test_cohere_timeout_is_transient_and_distinguishable(monkeypatch):
    monkeypatch.setattr(
        "askanu_rag.retrieval.reranking.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(socket.timeout()),
    )
    with pytest.raises(RerankerUnavailableError) as caught:
        CohereReranker("test-key").rerank("query", ("document",), top_n=1)
    assert caught.value.diagnostic.category == "timeout"
    assert caught.value.diagnostic.status_code is None


@pytest.mark.parametrize("status", (500, 503, 504))
def test_cohere_server_errors_are_transient_and_distinguishable(
    monkeypatch, status
):
    monkeypatch.setattr(
        "askanu_rag.retrieval.reranking.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(_http_error(status)),
    )
    with pytest.raises(RerankerUnavailableError) as caught:
        CohereReranker("test-key").rerank("query", ("document",), top_n=1)
    assert caught.value.diagnostic.category == "server_error"
    assert caught.value.diagnostic.status_code == status


@pytest.mark.parametrize(
    ("status", "category"),
    ((400, "invalid_request"), (422, "invalid_request"), (404, "model_not_found")),
)
def test_cohere_permanent_request_errors_are_distinguishable(
    monkeypatch, status, category
):
    monkeypatch.setattr(
        "askanu_rag.retrieval.reranking.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(_http_error(status)),
    )
    with pytest.raises(RerankerError) as caught:
        CohereReranker("test-key").rerank("query", ("document",), top_n=1)
    assert not isinstance(caught.value, RerankerUnavailableError)
    assert caught.value.diagnostic.category == category
    assert caught.value.diagnostic.status_code == status


def test_cohere_success_observer_contains_shape_not_payload(monkeypatch):
    observed = []

    class Response:
        headers = {
            "x-request-id": "safe-request-id",
            "x-ratelimit-limit": "10",
            "authorization": "must-not-appear",
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"results": [{"index": 0, "relevance_score": 0.9}]}
            ).encode()

    monkeypatch.setattr(
        "askanu_rag.retrieval.reranking.request.urlopen",
        lambda *_args, **_kwargs: Response(),
    )
    CohereReranker("test-key", diagnostic_observer=observed.append).rerank(
        "private query", ("private document",), top_n=1
    )

    assert len(observed) == 1
    diagnostic = observed[0]
    assert diagnostic.category == "success"
    assert diagnostic.status_code == 200
    assert diagnostic.request_id == "safe-request-id"
    assert dict(diagnostic.rate_limit_headers) == {"x-ratelimit-limit": "10"}
    assert (diagnostic.query_chars, diagnostic.document_count) == (13, 1)
    assert "private" not in repr(diagnostic)
