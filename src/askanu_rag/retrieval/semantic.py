"""Bounded local sparse candidate retrievers."""

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from askanu_rag.models import CommonRecord

STOP_WORDS = frozenset("which what is are a an the course courses program programs teaches covers about in of and or for me tell learn study".split())


@dataclass(frozen=True)
class SemanticHit:
    record_id: str
    score: float


class SemanticRetriever(Protocol):
    def search(
        self, query: str, candidates: tuple[CommonRecord, ...],
        *, top_k: int, min_score: float,
    ) -> tuple[SemanticHit, ...]: ...


def _tokens(text: str) -> Counter[str]:
    return Counter(token for token in re.findall(r"[a-z]+", text.casefold()) if token not in STOP_WORDS)


class LocalTfidfRetriever:
    """Ephemeral cosine ranking over ONLY the supplied prefiltered snapshot.

    No provider, files, history, generated answers or persistent index metadata.
    Lexical vectors are a transparent Day 5 local fallback, not synonym inference.
    """

    uses_persistent_index = False

    def search(self, query, candidates, *, top_k, min_score):
        if not candidates:
            return ()
        documents = [_tokens(record.title + "\n" + record.content) for record in candidates]
        frequencies = Counter(word for document in documents for word in document)
        idf = {word: math.log((1 + len(documents)) / (1 + count)) + 1 for word, count in frequencies.items()}

        def vector(tokens):
            weighted = {word: count * idf.get(word, math.log(1 + len(documents)) + 1) for word, count in tokens.items()}
            norm = math.sqrt(sum(value * value for value in weighted.values()))
            return {word: value / norm for word, value in weighted.items()} if norm else {}

        query_vector = vector(_tokens(query))
        results = []
        for record, document in zip(candidates, documents):
            doc_vector = vector(document)
            score = sum(weight * doc_vector.get(word, 0) for word, weight in query_vector.items())
            if score > 0 and score >= min_score:
                results.append(SemanticHit(record.record_id, score))
        return tuple(sorted(results, key=lambda hit: (-hit.score, hit.record_id))[:top_k])


_BM25_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class LocalBm25Retriever:
    """Ephemeral BM25 over the prefiltered title-plus-content snapshot.

    This is the exact repository-owned implementation evaluated by the frozen
    V7 Day 3 benchmark: k1=1.2, b=0.75, case-folded alphanumeric tokens, no
    stopword removal or stemming, and deterministic record-ID tie breaking.
    BM25 scores are positive ranking signals, not normalized confidence.
    """

    uses_persistent_index = False
    uses_min_score = False
    score_kind = "bm25"

    def __init__(self, *, k1: float = 1.2, b: float = 0.75) -> None:
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("invalid BM25 parameters")
        self.k1 = k1
        self.b = b

    def search(self, query, candidates, *, top_k, min_score):
        del min_score  # The evaluated BM25 configuration accepts every score > 0.
        if not candidates or top_k < 1:
            return ()
        documents = [
            self._tokens(f"{record.title}\n{record.content}")
            for record in candidates
        ]
        query_tokens = tuple(self._tokens(query))
        if not query_tokens:
            return ()
        document_frequency = Counter(
            token for document in documents for token in set(document)
        )
        average_length = sum(len(document) for document in documents) / len(
            documents
        )
        scored: list[tuple[float, str]] = []
        for record, document in zip(candidates, documents):
            score = 0.0
            length_normalizer = 1 - self.b + self.b * (
                len(document) / average_length if average_length else 0
            )
            for token in query_tokens:
                frequency = document[token]
                if frequency == 0:
                    continue
                frequency_docs = document_frequency[token]
                inverse_frequency = math.log(
                    1
                    + (
                        len(documents) - frequency_docs + 0.5
                    )
                    / (frequency_docs + 0.5)
                )
                score += inverse_frequency * (
                    frequency * (self.k1 + 1)
                ) / (frequency + self.k1 * length_normalizer)
            if score > 0:
                scored.append((score, record.record_id))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(
            SemanticHit(record_id=record_id, score=score)
            for score, record_id in scored[:top_k]
        )

    @staticmethod
    def _tokens(value: str) -> Counter[str]:
        return Counter(_BM25_TOKEN_PATTERN.findall(value.casefold()))


def sparse_score_is_usable(retriever, score: float, *, min_score: float) -> bool:
    """Validate a sparse score without treating BM25 as normalized confidence."""

    if not math.isfinite(score):
        return False
    if getattr(retriever, "score_kind", None) == "bm25":
        return score > 0
    return min_score <= score <= 1
