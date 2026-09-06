"""Deterministic retrieval interfaces."""

from askanu_rag.retrieval.identifiers import (
    COURSE_CODE_PATTERN,
    normalize_course_code,
    normalize_program_code,
)
from askanu_rag.retrieval.repository import (
    CourseProgramRepository,
    LookupResult,
    load_course_program_records,
)

__all__ = [
    "COURSE_CODE_PATTERN",
    "CourseProgramRepository",
    "LookupResult",
    "load_course_program_records",
    "normalize_course_code",
    "normalize_program_code",
]
