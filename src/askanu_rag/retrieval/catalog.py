"""Internal catalog access and hard metadata filters; no shared schema changes."""

import re
from typing import Protocol, runtime_checkable

from askanu_rag.models import CourseProgramRecord
from askanu_rag.retrieval.repository import CourseProgramReader, LookupResult


@runtime_checkable
class CatalogReader(CourseProgramReader, Protocol):
    def find_program_by_code(self, identifier: str, academic_year: str | None = None) -> LookupResult: ...
    def all_records(self) -> tuple[CourseProgramRecord, ...]: ...


def normalize_title(value: str) -> str:
    return " ".join(value.split()).casefold()


def record_code(record: CourseProgramRecord) -> str:
    metadata = record.metadata_json
    if metadata.entity_type == "course":
        return metadata.course_code
    if metadata.entity_type == "program":
        return metadata.program_code
    return metadata.subplan_code


def matches_session(record: CourseProgramRecord, session: str | None) -> bool:
    if session is None:
        return True
    offerings = getattr(record.metadata_json, "offerings", None)
    if not offerings:
        return False
    normalized_session = normalize_title(session).replace(
        "semester 1", "first semester"
    ).replace("semester 2", "second semester")
    # Only explicit stored session text; no dates, IDs or URL-derived inference.
    for offering in offerings:
        value = offering.get("session")
        if not isinstance(value, str):
            continue
        clean = normalize_title(value).replace(
            "semester 1", "first semester"
        ).replace("semester 2", "second semester")
        if re.fullmatch(
            re.escape(normalized_session) + r"(?:,?\s+\d{4})?", clean
        ):
            years = re.findall(r"\b\d{4}\b", clean)
            if not years or years == [record.metadata_json.academic_year]:
                return True
    return False


def filter_records(records, entity_type=None, academic_year=None, session=None):
    return tuple(
        record for record in records
        if (entity_type is None or record.metadata_json.entity_type == entity_type)
        and (academic_year is None or record.metadata_json.academic_year == academic_year)
        and matches_session(record, session)
    )
