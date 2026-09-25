"""Small, auditable query expansions justified by the frozen Day 3 benchmark."""

from __future__ import annotations

import re

_SUPPORT_EXPANSIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(?:graded unfairly|unfair(?:ly)? graded|unfair (?:mark|grade)|"
            r"challenge (?:a |my |the )?(?:mark|grade|assessment))\b",
            re.IGNORECASE,
        ),
        "grade appeal academic difficulty assessment unfair grades",
    ),
    (
        re.compile(
            r"\b(?:cannot afford|can't afford|money stress|financial hardship|"
            r"struggling (?:with|to pay for) (?:food|groceries|rent))\b",
            re.IGNORECASE,
        ),
        "financial support money stress financial hardship",
    ),
    (
        re.compile(
            r"\binternational student\b.*\b(?:settling in|community|where can .* help)\b",
            re.IGNORECASE,
        ),
        "international student support study community referral",
    ),
)


def expand_support_problem_query(question: str) -> str:
    """Append bounded retrieval vocabulary without changing hard constraints."""

    expansions = [
        expansion
        for pattern, expansion in _SUPPORT_EXPANSIONS
        if pattern.search(question)
    ]
    if not expansions:
        return question
    return " ".join((question, *expansions))
