"""Structured identifier normalization for deterministic exact lookup."""

import re
from typing import Final

COURSE_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Z]{4}\d{4}[A-Z]?$"
)


def normalize_course_code(identifier: str) -> str | None:
    """Canonicalize a possible course code, returning None when malformed."""

    canonical = "".join(identifier.split()).upper()
    if COURSE_CODE_PATTERN.fullmatch(canonical) is None:
        return None
    return canonical


def normalize_course_code_reference(identifier: str) -> str | None:
    """Normalize a bounded user-written course-code reference.

    Canonical storage validation remains strict. This accepts only bounded
    four-letter Course-code presentation forms such as COMP1110, BIOL 9001P
    and BIOL-9001P (including harmless surrounding whitespace), then delegates
    to the strict canonical normalizer.
    """

    match = re.fullmatch(
        r"\s*([A-Za-z]{4})\s*(?:-\s*)?(\d{4}[A-Za-z]?)\s*",
        identifier,
    )
    if match is None:
        return None
    return normalize_course_code(f"{match.group(1)}{match.group(2)}")


def normalize_program_code(identifier: str) -> str:
    """Apply conservative normalization without inventing a program grammar."""

    return identifier.strip().upper()


def normalize_subplan_code(identifier: str) -> str:
    """Normalize a source SubPlanCode without inventing a new grammar."""

    return identifier.strip().upper()
