"""Validated local record loading and deterministic course/program data access."""

import json
import stat
from collections.abc import Iterable
from datetime import date
from os import stat_result
from pathlib import Path
from typing import Literal, Protocol, TypeAlias, runtime_checkable

from pydantic import ValidationError

from askanu_rag.models import (
    AccommodationMetadata,
    AccommodationRecord,
    CommonRecord,
    CourseMetadata,
    CourseProgramRecord,
    JobMetadata,
    JobRecord,
    ProgramMetadata,
    ScholarshipMetadata,
    ScholarshipRecord,
    SubplanMetadata,
    SupportMetadata,
    SupportRecord,
)
from askanu_rag.retrieval.identifiers import (
    normalize_course_code,
    normalize_program_code,
    normalize_subplan_code,
)

LookupResult: TypeAlias = (
    CourseProgramRecord | tuple[CourseProgramRecord, ...] | None
)
ScholarshipLookupResult: TypeAlias = ScholarshipRecord | None
JobLookupResult: TypeAlias = JobRecord | None
ResourceRecord: TypeAlias = AccommodationRecord | SupportRecord
CoursesEntityType: TypeAlias = Literal[
    "course", "program", "major", "minor", "specialisation"
]
LookupKey: TypeAlias = tuple[CoursesEntityType, str, str]
CodeKey: TypeAlias = tuple[CoursesEntityType, str]


class CourseProgramReader(Protocol):
    """Minimal read boundary used by deterministic course request handling."""

    def find_course_by_code(
        self, identifier: str, academic_year: str | None = None
    ) -> LookupResult:
        """Return an exact course match or preserve multi-year ambiguity."""

        ...

@runtime_checkable
class ScholarshipReader(Protocol):
    """Minimal read boundary for deterministic Scholarship retrieval."""

    def find_scholarship_by_entity_id(
        self, entity_id: str
    ) -> ScholarshipLookupResult: ...

    def all_scholarships(self) -> tuple[ScholarshipRecord, ...]: ...


@runtime_checkable
class JobReader(Protocol):
    """Minimal read boundary for exact and current Jobs candidates."""

    def find_job_by_entity_id(self, entity_id: str) -> JobLookupResult: ...

    def find_jobs_by_title(self, title: str) -> tuple[JobRecord, ...]: ...

    def current_jobs(
        self,
        limit: int,
        today: date,
        employment_type: str | None = None,
    ) -> tuple[JobRecord, ...]: ...

    def current_job_candidates(
        self,
        today: date,
        employment_type: str | None = None,
    ) -> tuple[JobRecord, ...]: ...


@runtime_checkable
class ResourceReader(Protocol):
    """Shared exact/list boundary for Accommodation and Support records."""

    def all_domain_records(
        self, domain: Literal["accommodation", "support"]
    ) -> tuple[ResourceRecord, ...]: ...

    def find_domain_by_title(
        self, domain: Literal["accommodation", "support"], title: str
    ) -> tuple[ResourceRecord, ...]: ...


def normalize_job_title(value: str) -> str:
    """Apply the frozen case/whitespace normalization for exact titles."""

    return " ".join(value.casefold().split())


def load_common_records(fixture_path: str | Path) -> tuple[CommonRecord, ...]:
    """Load the shared 16-field contract from one local JSON array."""

    payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Shared record fixture must contain a JSON array.")
    return tuple(CommonRecord.model_validate(item) for item in payload)


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
    """In-memory shared records with compatible course/program lookup methods."""

    def __init__(self, records: Iterable[CommonRecord]) -> None:
        self._records: dict[LookupKey, CourseProgramRecord] = {}
        self._records_by_code: dict[CodeKey, list[CourseProgramRecord]] = {}
        self._scholarships: dict[str, ScholarshipRecord] = {}
        self._jobs: dict[str, JobRecord] = {}
        self._jobs_by_title: dict[str, list[JobRecord]] = {}
        self._resources: dict[str, ResourceRecord] = {}
        self._resources_by_title: dict[
            tuple[str, str], list[ResourceRecord]
        ] = {}

        for record in records:
            metadata = record.metadata_json
            if isinstance(metadata, (AccommodationMetadata, SupportMetadata)):
                model = (
                    AccommodationRecord
                    if isinstance(metadata, AccommodationMetadata)
                    else SupportRecord
                )
                resource = model.model_validate(record.model_dump(mode="python"))
                if resource.record_id in self._resources:
                    raise ValueError(f"Duplicate record_id: {resource.record_id}")
                self._resources[resource.record_id] = resource
                self._resources_by_title.setdefault(
                    (resource.domain, normalize_job_title(resource.title)), []
                ).append(resource)
                continue
            if isinstance(metadata, JobMetadata):
                job = JobRecord.model_validate(record.model_dump(mode="python"))
                if job.entity_id in self._jobs:
                    raise ValueError(f"Duplicate record_id: {job.record_id}")
                self._jobs[job.entity_id] = job
                self._jobs_by_title.setdefault(
                    normalize_job_title(job.title), []
                ).append(job)
                continue
            if isinstance(metadata, ScholarshipMetadata):
                scholarship = ScholarshipRecord.model_validate(
                    record.model_dump(mode="python")
                )
                if scholarship.entity_id in self._scholarships:
                    raise ValueError(
                        f"Duplicate record_id: {scholarship.record_id}"
                    )
                self._scholarships[scholarship.entity_id] = scholarship
                continue

            course_program = CourseProgramRecord.model_validate(
                record.model_dump(mode="python")
            )
            if isinstance(metadata, CourseMetadata):
                entity_type: CoursesEntityType = "course"
                code = metadata.course_code
            elif isinstance(metadata, ProgramMetadata):
                entity_type = "program"
                code = metadata.program_code
            else:
                entity_type = metadata.entity_type
                code = metadata.subplan_code

            lookup_key = (entity_type, code, metadata.academic_year)
            if lookup_key in self._records:
                raise ValueError(f"Duplicate exact lookup key: {lookup_key}")

            self._records[lookup_key] = course_program
            self._records_by_code.setdefault((entity_type, code), []).append(
                course_program
            )

    def _find(
        self,
        entity_type: CoursesEntityType,
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

    def find_by_code(
        self,
        entity_type: CoursesEntityType,
        identifier: str,
        academic_year: str | None = None,
    ) -> LookupResult:
        if entity_type == "course":
            canonical = normalize_course_code(identifier)
        elif entity_type == "program":
            canonical = normalize_program_code(identifier)
        else:
            canonical = normalize_subplan_code(identifier)
        if not canonical:
            return None
        return self._find(entity_type, canonical, academic_year)

    def find_major_by_code(
        self, identifier: str, academic_year: str | None = None
    ) -> LookupResult:
        return self.find_by_code("major", identifier, academic_year)

    def find_minor_by_code(
        self, identifier: str, academic_year: str | None = None
    ) -> LookupResult:
        return self.find_by_code("minor", identifier, academic_year)

    def find_specialisation_by_code(
        self, identifier: str, academic_year: str | None = None
    ) -> LookupResult:
        return self.find_by_code("specialisation", identifier, academic_year)

    def all_records(self) -> tuple[CourseProgramRecord, ...]:
        """Read-only catalog snapshot for bounded Day 5 name/metadata planning."""
        return tuple(sorted(self._records.values(), key=lambda record: record.record_id))

    def find_scholarship_by_entity_id(
        self, entity_id: str
    ) -> ScholarshipLookupResult:
        """Return one stable URL-slug Scholarship identity without inference."""

        return self._scholarships.get(entity_id.strip())

    def all_scholarships(self) -> tuple[ScholarshipRecord, ...]:
        """Return the current stored Scholarship snapshot in stable ID order."""

        return tuple(
            sorted(self._scholarships.values(), key=lambda record: record.record_id)
        )

    def find_job_by_entity_id(self, entity_id: str) -> JobLookupResult:
        """Return one exact numeric Jobs identity without URL/title inference."""

        return self._jobs.get(entity_id.strip())

    def find_jobs_by_title(self, title: str) -> tuple[JobRecord, ...]:
        """Return every normalized exact-title match in numeric ID order."""

        return tuple(
            sorted(
                self._jobs_by_title.get(normalize_job_title(title), ()),
                key=lambda record: int(record.entity_id),
            )
        )

    def current_jobs(
        self,
        limit: int,
        today: date,
        employment_type: str | None = None,
    ) -> tuple[JobRecord, ...]:
        """Filter, order, then limit source-supported current Jobs."""

        if limit < 1:
            raise ValueError("limit must be positive")
        return self.current_job_candidates(today, employment_type)[:limit]

    def current_job_candidates(
        self,
        today: date,
        employment_type: str | None = None,
    ) -> tuple[JobRecord, ...]:
        """Return every current hard-filter match before response limiting."""

        wanted_type = employment_type.casefold() if employment_type else None
        current = (
            record
            for record in self._jobs.values()
            if record.metadata_json.status == "current"
            and (
                record.metadata_json.closing_date is None
                or date.fromisoformat(record.metadata_json.closing_date) >= today
            )
            and (
                wanted_type is None
                or any(
                    item.casefold() == wanted_type
                    for item in record.metadata_json.employment_types
                )
            )
        )
        ordered = sorted(
            current,
            key=lambda record: (
                record.metadata_json.closing_date is None,
                record.metadata_json.closing_date or "",
                int(record.entity_id),
            ),
        )
        return tuple(ordered)

    def all_domain_records(
        self, domain: Literal["accommodation", "support"]
    ) -> tuple[ResourceRecord, ...]:
        return tuple(
            sorted(
                (record for record in self._resources.values() if record.domain == domain),
                key=lambda record: record.record_id,
            )
        )

    def find_domain_by_title(
        self, domain: Literal["accommodation", "support"], title: str
    ) -> tuple[ResourceRecord, ...]:
        return tuple(
            sorted(
                self._resources_by_title.get(
                    (domain, normalize_job_title(title)), ()
                ),
                key=lambda record: record.record_id,
            )
        )


def create_default_course_program_repository() -> CourseProgramRepository:
    """Load today's approved local fixture behind the repository boundary."""

    fixture_path = (
        Path(__file__).parents[3]
        / "fixtures"
        / "day2_course_program_records.json"
    )
    return CourseProgramRepository(load_course_program_records(fixture_path))
