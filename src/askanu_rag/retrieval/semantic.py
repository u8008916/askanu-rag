"""Bounded local sparse-vector baseline, not pretrained semantic embeddings."""

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from askanu_rag.models import CourseProgramRecord

STOP_WORDS = frozenset("which what is are a an the course courses program programs teaches covers about in of and or for me tell learn study".split())


@dataclass(frozen=True)
class SemanticHit:
    record_id: str
    score: float


class SemanticRetriever(Protocol):
    def search(
        self, query: str, candidates: tuple[CourseProgramRecord, ...],
        *, top_k: int, min_score: float,
    ) -> tuple[SemanticHit, ...]: ...


def _tokens(text: str) -> Counter[str]:
    return Counter(token for token in re.findall(r"[a-z]+", text.casefold()) if token not in STOP_WORDS)


class LocalTfidfRetriever:
    """Ephemeral cosine ranking over ONLY the supplied prefiltered snapshot.

    No provider, files, history, generated answers or persistent index metadata.
    Lexical vectors are a transparent Day 5 local fallback, not synonym inference.
    """

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
