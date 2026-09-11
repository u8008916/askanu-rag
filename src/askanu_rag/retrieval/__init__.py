"""Deterministic retrieval interfaces."""

from askanu_rag.retrieval.identifiers import (
    COURSE_CODE_PATTERN,
    normalize_course_code,
    normalize_program_code,
)
from askanu_rag.retrieval.repository import (
    CourseProgramReader,
    CourseProgramRepository,
    LookupResult,
    create_default_course_program_repository,
    load_course_program_record_file,
    load_course_program_records,
    load_course_program_records_directory,
)
from askanu_rag.retrieval.postgres import (
    PostgresCourseProgramRepository,
    UnavailableCourseProgramRepository,
)

__all__ = [
    "COURSE_CODE_PATTERN",
    "CourseProgramReader",
    "CourseProgramRepository",
    "LookupResult",
    "PostgresCourseProgramRepository",
    "UnavailableCourseProgramRepository",
    "create_default_course_program_repository",
    "load_course_program_record_file",
    "load_course_program_records",
    "load_course_program_records_directory",
    "normalize_course_code",
    "normalize_program_code",
]
