"""Fixture-backed deterministic course and program data access."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, TypeAlias

from askanu_rag.models import CourseMetadata, CourseProgramRecord
from askanu_rag.retrieval.identifiers import (
    normalize_course_code,
    normalize_program_code,
)

LookupResult: TypeAlias = (
    CourseProgramRecord | tuple[CourseProgramRecord, ...] | None
)
LookupKey: TypeAlias = tuple[Literal["course", "program"], str, str]
CodeKey: TypeAlias = tuple[Literal["course", "program"], str]


def load_course_program_records(
    fixture_path: str | Path,
) -> tuple[CourseProgramRecord, ...]:
    """Load and validate schema-v1 records from a local JSON fixture."""

    payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Course/program fixture must contain a JSON array.")
    return tuple(CourseProgramRecord.model_validate(item) for item in payload)


class CourseProgramRepository:
    """Own multi-year-safe exact lookup without inferring an academic year."""

    def __init__(self, records: Iterable[CourseProgramRecord]) -> None:
        self._records: dict[LookupKey, CourseProgramRecord] = {}
        self._records_by_code: dict[CodeKey, list[CourseProgramRecord]] = {}

        for record in records:
            metadata = record.metadata_json
            if isinstance(metadata, CourseMetadata):
                entity_type: Literal["course", "program"] = "course"
                code = metadata.course_code
            else:
                entity_type = "program"
                code = metadata.program_code

            lookup_key = (entity_type, code, metadata.academic_year)
            if lookup_key in self._records:
                raise ValueError(f"Duplicate exact lookup key: {lookup_key}")

            self._records[lookup_key] = record
            self._records_by_code.setdefault((entity_type, code), []).append(record)

    def _find(
        self,
        entity_type: Literal["course", "program"],
        code: str,
        academic_year: str | None,
    ) -> LookupResult:
        if academic_year is not None:
            return self._records.get((entity_type, code, academic_year))

        matches = tuple(
            sorted(
                self._records_by_code.get((entity_type, code), ()),
                key=lambda record: record.metadata_json.academic_year,
            )
        )
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        return matches

    def find_course_by_code(
        self, identifier: str, academic_year: str | None = None
    ) -> LookupResult:
        """Return an exact course match or preserve multi-year ambiguity."""

        canonical = normalize_course_code(identifier)
        if canonical is None:
            return None
        return self._find("course", canonical, academic_year)

    def find_program_by_code(
        self, identifier: str, academic_year: str | None = None
    ) -> LookupResult:
        """Return an exact program match or preserve multi-year ambiguity."""

        canonical = normalize_program_code(identifier)
        if not canonical:
            return None
        return self._find("program", canonical, academic_year)
