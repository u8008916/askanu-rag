"""PostgreSQL adapter for the existing deterministic course/program boundary."""

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Literal, TypeVar

from askanu_rag.config import Settings
from askanu_rag.database import (
    ConnectionFactory,
    DatabaseConnectionConfig,
    RepositoryUnavailableError,
)
from askanu_rag.models import (
    AccommodationRecord,
    CommonRecord,
    CourseProgramRecord,
    EventRecord,
    JobRecord,
    ScholarshipRecord,
    SupportRecord,
)
from askanu_rag.retrieval.identifiers import (
    normalize_course_code,
    normalize_program_code,
    normalize_subplan_code,
)
from askanu_rag.retrieval.repository import (
    JobLookupResult,
    CoursesEntityType,
    LookupResult,
    ScholarshipLookupResult,
    ResourceRecord,
    normalize_job_title,
)

COURSE_PROGRAM_WHERE = """
source_id = 'courses_programs_and_courses'
AND domain = 'courses'
"""
SCHOLARSHIP_WHERE = """
source_id = 'scholarships_anu_finder'
AND domain = 'scholarships'
AND metadata_json ->> 'entity_type' = 'scholarship'
"""
JOB_WHERE = """
source_id = 'jobs_anu_search'
AND domain = 'jobs'
AND metadata_json ->> 'entity_type' = 'job'
"""
RESOURCE_SOURCES = {
    "accommodation": "accommodation_anu_study",
    "support": "support_anusa_student_assistance",
}

SELECT_COLUMNS = """
record_id, source_id, entity_id, domain, title, content, canonical_url,
status, effective_from, effective_to, collected_at, last_seen_at,
content_hash, embedding_version, index_status, metadata_json
"""


RecordModel = TypeVar("RecordModel", bound=CommonRecord)


class PostgresCourseProgramRepository:
    """Fresh shared-table reads with compatible course/program methods."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    @classmethod
    def from_settings(cls, settings: Settings) -> "PostgresCourseProgramRepository":
        config = DatabaseConnectionConfig.from_settings(settings)
        return cls(config.connect)

    def _find(
        self,
        entity_type: CoursesEntityType,
        code: str,
        academic_year: str | None,
    ) -> LookupResult:
        code_key = (
            "course_code"
            if entity_type == "course"
            else "program_code"
            if entity_type == "program"
            else "subplan_code"
        )
        query = f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE {COURSE_PROGRAM_WHERE}
              AND metadata_json ->> 'entity_type' = %s
              AND metadata_json ->> '{code_key}' = %s
        """
        parameters: list[str] = [entity_type, code]
        if academic_year is not None:
            query += " AND metadata_json ->> 'academic_year' = %s"
            parameters.append(academic_year)
        query += " ORDER BY metadata_json ->> 'academic_year', record_id"

        records = self._fetch_records(
            query, tuple(parameters), model=CourseProgramRecord
        )
        if not records:
            return None
        if len(records) == 1:
            return records[0]
        return records

    def _fetch_records(
        self,
        query: str,
        parameters: tuple[object, ...] = (),
        *,
        model: type[RecordModel],
    ) -> tuple[RecordModel, ...]:
        try:
            with self._connection_factory() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, parameters)
                    rows = cursor.fetchall()
            records = tuple(model.model_validate(dict(row)) for row in rows)
        except Exception:
            raise RepositoryUnavailableError() from None
        return records

    def find_course_by_code(
        self, identifier: str, academic_year: str | None = None
    ) -> LookupResult:
        canonical = normalize_course_code(identifier)
        if canonical is None:
            return None
        return self._find("course", canonical, academic_year)

    def find_program_by_code(
        self, identifier: str, academic_year: str | None = None
    ) -> LookupResult:
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

    def find_major_by_code(self, identifier: str, academic_year: str | None = None) -> LookupResult:
        return self.find_by_code("major", identifier, academic_year)

    def find_minor_by_code(self, identifier: str, academic_year: str | None = None) -> LookupResult:
        return self.find_by_code("minor", identifier, academic_year)

    def find_specialisation_by_code(self, identifier: str, academic_year: str | None = None) -> LookupResult:
        return self.find_by_code("specialisation", identifier, academic_year)

    def all_records(self) -> tuple[CourseProgramRecord, ...]:
        return self._fetch_records(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE {COURSE_PROGRAM_WHERE}
            ORDER BY record_id
            """,
            model=CourseProgramRecord,
        )

    def find_scholarship_by_entity_id(
        self, entity_id: str
    ) -> ScholarshipLookupResult:
        records = self._fetch_records(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE {SCHOLARSHIP_WHERE}
              AND entity_id = %s
            ORDER BY record_id
            """,
            (entity_id.strip(),),
            model=ScholarshipRecord,
        )
        return records[0] if records else None

    def all_scholarships(self) -> tuple[ScholarshipRecord, ...]:
        return self._fetch_records(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE {SCHOLARSHIP_WHERE}
            ORDER BY record_id
            """,
            model=ScholarshipRecord,
        )

    def find_job_by_entity_id(self, entity_id: str) -> JobLookupResult:
        records = self._fetch_records(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE {JOB_WHERE}
              AND entity_id = %s
            ORDER BY record_id
            """,
            (entity_id.strip(),),
            model=JobRecord,
        )
        return records[0] if records else None

    def find_jobs_by_title(self, title: str) -> tuple[JobRecord, ...]:
        return self._fetch_records(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE {JOB_WHERE}
              AND lower(regexp_replace(btrim(title), '[[:space:]]+', ' ', 'g')) = %s
            ORDER BY entity_id::numeric
            """,
            (normalize_job_title(title),),
            model=JobRecord,
        )

    def current_jobs(
        self,
        limit: int,
        today: date,
        employment_type: str | None = None,
    ) -> tuple[JobRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        query = f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE {JOB_WHERE}
              AND metadata_json ->> 'status' = 'current'
              AND (
                  metadata_json ->> 'closing_date' IS NULL
                  OR (metadata_json ->> 'closing_date')::date >= %s
              )
        """
        parameters: list[object] = [today]
        if employment_type is not None:
            query += " AND metadata_json -> 'employment_types' ? %s"
            parameters.append(employment_type)
        query += """
            ORDER BY
                (metadata_json ->> 'closing_date') IS NULL ASC,
                (metadata_json ->> 'closing_date')::date ASC,
                entity_id::numeric ASC
            LIMIT %s
        """
        parameters.append(limit)
        return self._fetch_records(query, tuple(parameters), model=JobRecord)

    def current_job_candidates(
        self,
        today: date,
        employment_type: str | None = None,
    ) -> tuple[JobRecord, ...]:
        query = f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE {JOB_WHERE}
              AND metadata_json ->> 'status' = 'current'
              AND (
                  metadata_json ->> 'closing_date' IS NULL
                  OR (metadata_json ->> 'closing_date')::date >= %s
              )
        """
        parameters: list[object] = [today]
        if employment_type is not None:
            query += " AND metadata_json -> 'employment_types' ? %s"
            parameters.append(employment_type)
        query += """
            ORDER BY
                (metadata_json ->> 'closing_date') IS NULL ASC,
                (metadata_json ->> 'closing_date')::date ASC,
                entity_id::numeric ASC
        """
        return self._fetch_records(
            query,
            tuple(parameters),
            model=JobRecord,
        )

    def all_domain_records(
        self, domain: Literal["accommodation", "support"]
    ) -> tuple[ResourceRecord, ...]:
        model = AccommodationRecord if domain == "accommodation" else SupportRecord
        return self._fetch_records(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE domain = %s AND source_id = %s
            ORDER BY record_id
            """,
            (domain, RESOURCE_SOURCES[domain]),
            model=model,
        )

    def find_domain_by_title(
        self, domain: Literal["accommodation", "support"], title: str
    ) -> tuple[ResourceRecord, ...]:
        model = AccommodationRecord if domain == "accommodation" else SupportRecord
        return self._fetch_records(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE domain = %s AND source_id = %s
              AND lower(regexp_replace(btrim(title), '[[:space:]]+', ' ', 'g')) = %s
            ORDER BY record_id
            """,
            (domain, RESOURCE_SOURCES[domain], normalize_job_title(title)),
            model=model,
        )

    def all_events(self) -> tuple[EventRecord, ...]:
        return self._fetch_records(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE domain = 'events'
              AND source_id IN ('events_anu_official', 'rubric_unified_search')
              AND metadata_json ->> 'entity_type' = 'event'
            ORDER BY (metadata_json ->> 'start_at')::timestamptz, record_id
            """,
            model=EventRecord,
        )

    def upcoming_official_events(
        self, limit: int, now: datetime
    ) -> tuple[EventRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        return self._fetch_records(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM source_records
            WHERE domain = 'events'
              AND source_id = 'events_anu_official'
              AND metadata_json ->> 'entity_type' = 'event'
              AND (metadata_json ->> 'start_at')::timestamptz >= %s
            ORDER BY (metadata_json ->> 'start_at')::timestamptz, record_id
            LIMIT %s
            """,
            (now, limit),
            model=EventRecord,
        )


class UnavailableCourseProgramRepository:
    """Fail closed when production expects Cloud SQL but config is incomplete."""

    @staticmethod
    def _raise() -> None:
        raise RepositoryUnavailableError()

    def find_course_by_code(
        self, _identifier: str, _academic_year: str | None = None
    ) -> LookupResult:
        self._raise()

    def find_program_by_code(
        self, _identifier: str, _academic_year: str | None = None
    ) -> LookupResult:
        self._raise()

    def all_records(self) -> tuple[CourseProgramRecord, ...]:
        self._raise()

    def find_scholarship_by_entity_id(
        self, _entity_id: str
    ) -> ScholarshipLookupResult:
        self._raise()

    def all_scholarships(self) -> tuple[ScholarshipRecord, ...]:
        self._raise()

    def find_job_by_entity_id(self, _entity_id: str) -> JobLookupResult:
        self._raise()

    def find_jobs_by_title(self, _title: str) -> tuple[JobRecord, ...]:
        self._raise()

    def current_jobs(
        self,
        _limit: int,
        _today: date,
        _employment_type: str | None = None,
    ) -> tuple[JobRecord, ...]:
        self._raise()

    def current_job_candidates(
        self,
        _today: date,
        _employment_type: str | None = None,
    ) -> tuple[JobRecord, ...]:
        self._raise()

    def find_by_code(
        self,
        _entity_type: CoursesEntityType,
        _identifier: str,
        _academic_year: str | None = None,
    ) -> LookupResult:
        self._raise()

    def find_major_by_code(self, _identifier: str, _academic_year: str | None = None) -> LookupResult:
        self._raise()

    def find_minor_by_code(self, _identifier: str, _academic_year: str | None = None) -> LookupResult:
        self._raise()

    def find_specialisation_by_code(self, _identifier: str, _academic_year: str | None = None) -> LookupResult:
        self._raise()

    def all_domain_records(
        self, _domain: Literal["accommodation", "support"]
    ) -> tuple[ResourceRecord, ...]:
        self._raise()

    def find_domain_by_title(
        self,
        _domain: Literal["accommodation", "support"],
        _title: str,
    ) -> tuple[ResourceRecord, ...]:
        self._raise()

    def all_events(self) -> tuple[EventRecord, ...]:
        self._raise()

    def upcoming_official_events(
        self, _limit: int, _now: datetime
    ) -> tuple[EventRecord, ...]:
        self._raise()
