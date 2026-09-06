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


def normalize_program_code(identifier: str) -> str:
    """Apply conservative normalization without inventing a program grammar."""

    return identifier.strip().upper()
