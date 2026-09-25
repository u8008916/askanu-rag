"""Extensible deterministic problem-language domain resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from askanu_rag.models import Domain


@dataclass(frozen=True)
class ProblemDomainSignal:
    name: str
    domain: Domain
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class ProblemDomainResolution:
    domain: Domain | None = None
    possible_domains: tuple[Domain, ...] = ()


class ProblemDomainResolver(Protocol):
    def resolve(self, question: str) -> ProblemDomainResolution: ...


class PatternProblemDomainResolver:
    """Resolve bounded problem language without coupling to retrieval."""

    def __init__(self, signals: Sequence[ProblemDomainSignal]) -> None:
        self._signals = tuple(signals)

    def resolve(self, question: str) -> ProblemDomainResolution:
        matched = {
            signal.domain
            for signal in self._signals
            if any(re.search(pattern, question, re.IGNORECASE) for pattern in signal.patterns)
        }
        ordered = tuple(sorted(matched, key=lambda domain: domain.value))
        if len(ordered) == 1:
            return ProblemDomainResolution(domain=ordered[0])
        if len(ordered) > 1:
            return ProblemDomainResolution(possible_domains=ordered)
        return ProblemDomainResolution()


DEFAULT_PROBLEM_DOMAIN_RESOLVER = PatternProblemDomainResolver(
    (
        ProblemDomainSignal(
            name="academic_grading_concern",
            domain=Domain.SUPPORT,
            patterns=(
                r"\bgraded unfairly\b",
                r"\bunfair(?:ly)? graded\b",
                r"\bappeal(?:ing)? (?:a |my |the )?grade\b",
                r"\bgrade (?:appeal|review)\b",
                r"\bchallenge (?:a |my |the )?(?:mark|grade|assessment)\b",
            ),
        ),
        ProblemDomainSignal(
            name="financial_hardship_concern",
            domain=Domain.SUPPORT,
            patterns=(
                r"\b(?:cannot|can't) afford (?:food|groceries|rent)\b",
                r"\bmoney stress\b",
                r"\bfinancial hardship\b",
            ),
        ),
        ProblemDomainSignal(
            name="international_settling_concern",
            domain=Domain.SUPPORT,
            patterns=(
                r"\binternational student\b.*\bsettling in\b",
            ),
        ),
    )
)
