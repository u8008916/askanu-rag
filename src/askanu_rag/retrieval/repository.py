"""Validated local record loading and deterministic course/program data access."""

import json
import stat
from collections.abc import Iterable
from os import stat_result
from pathlib import Path
from typing import Literal, Protocol, TypeAlias

from pydantic import ValidationError

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


class CourseProgramReader(Protocol):
    """Minimal read boundary used by deterministic course request handling."""

    def find_course_by_code(
        self, identifier: str, academic_year: str | None = None
    ) -> LookupResult:
        """Return an exact course match or preserve multi-year ambiguity."""

        ...


def load_course_program_records(
    fixture_path: str | Path,
) -> tuple[CourseProgramRecord, ...]:
    """Load and validate schema-v1 records from a local JSON fixture."""

    payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Course/program fixture must contain a JSON array.")
    return tuple(CourseProgramRecord.model_validate(item) for item in payload)


def _handoff_path_stat(path: Path) -> stat_result:
    """Inspect the supplied entry without following links or reparse points."""

    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise ValueError(f"Handoff path must not be a link or reparse point: {path}")
    return info


def load_course_program_record_file(path: str | Path) -> CourseProgramRecord:
    """Read one UTF-8 schema-v1 JSON object; identity comes only from its content."""

    record_path = Path(path)
    if not stat.S_ISREG(_handoff_path_stat(record_path).st_mode):
        raise ValueError(f"Handoff record must be a regular file: {record_path}")
    try:
        return CourseProgramRecord.model_validate_json(
            record_path.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        exc.add_note(f"Invalid handoff record file: {record_path}")
        raise


def load_course_program_records_directory(
    path: str | Path,
) -> tuple[CourseProgramRecord, ...]:
    """Load direct JSON entries in filename order, without traversing subfolders.

    Supply the records directory itself, not the scraper storage base directory.
    Empty directories return an empty tuple. Invalid JSON entries fail the load.
    """

    records_path = Path(path)
    if not stat.S_ISDIR(_handoff_path_stat(records_path).st_mode):
        raise NotADirectoryError(f"Not a handoff records directory: {records_path}")
    return tuple(
        load_course_program_record_file(entry)
        for entry in sorted(records_path.iterdir(), key=lambda entry: entry.name)
        if entry.suffix.lower() == ".json"
    )


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

    def all_records(self) -> tuple[CourseProgramRecord, ...]:
        """Read-only catalog snapshot for bounded Day 5 name/metadata planning."""
        return tuple(sorted(self._records.values(), key=lambda record: record.record_id))


def create_default_course_program_repository() -> CourseProgramRepository:
    """Load today's approved local fixture behind the repository boundary."""

    fixture_path = (
        Path(__file__).parents[3]
        / "fixtures"
        / "day2_course_program_records.json"
    )
    return CourseProgramRepository(load_course_program_records(fixture_path))
