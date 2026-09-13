"""PostgreSQL adapter for the existing deterministic course/program boundary."""

from collections.abc import Mapping
from typing import Any, Literal, TypeVar

from askanu_rag.config import Settings
from askanu_rag.database import (
    ConnectionFactory,
    DatabaseConnectionConfig,
    RepositoryUnavailableError,
)
from askanu_rag.models import CommonRecord, CourseProgramRecord, ScholarshipRecord
from askanu_rag.retrieval.identifiers import (
    normalize_course_code,
    normalize_program_code,
)
from askanu_rag.retrieval.repository import LookupResult
from askanu_rag.retrieval.repository import ScholarshipLookupResult

COURSE_PROGRAM_WHERE = """
source_id = 'courses_programs_and_courses'
AND domain = 'courses'
"""
SCHOLARSHIP_WHERE = """
source_id = 'scholarships_anu_finder'
AND domain = 'scholarships'
AND metadata_json ->> 'entity_type' = 'scholarship'
"""

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
        entity_type: Literal["course", "program"],
        code: str,
        academic_year: str | None,
    ) -> LookupResult:
        code_key = "course_code" if entity_type == "course" else "program_code"
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
