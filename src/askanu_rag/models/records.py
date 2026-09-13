"""Validated shared schema-v1 persisted records."""

from datetime import date, datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    field_validator,
    model_validator,
)

RecordStatus = Literal["NEW", "CHANGED", "UNCHANGED", "MISSING"]
IndexStatus = Literal["PENDING", "INDEXED", "FAILED"]
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class CourseMetadata(BaseModel):
    """Required and recognized schema-v1 course metadata."""

    model_config = ConfigDict(extra="allow", frozen=True)

    entity_type: Literal["course"]
    course_code: str = Field(pattern=r"^[A-Z]{4}\d{4}[A-Z]?$")
    academic_year: str = Field(pattern=r"^\d{4}$")
    career: str | None = None
    units: str | None = None
    delivery_mode: str | None = None
    prerequisites: str | None = None
    incompatibilities: str | None = None
    assumed_knowledge: str | None = None
    offerings: list[dict[str, object]] | None = None


class ProgramMetadata(BaseModel):
    """Required and recognized schema-v1 program metadata."""

    model_config = ConfigDict(extra="allow", frozen=True)

    entity_type: Literal["program"]
    program_code: str = Field(min_length=1)
    academic_year: str = Field(pattern=r"^\d{4}$")
    career: str | None = None
    units: str | None = None
    duration: str | None = None
    delivery_mode: str | None = None
    learning_outcomes: list[str] | None = None

    @field_validator("program_code")
    @classmethod
    def validate_normalized_program_code(cls, value: str) -> str:
        if value != value.strip().upper():
            raise ValueError("program_code must be trimmed and uppercase")
        return value


class ScholarshipMetadata(BaseModel):
    """Exact Day 9 Scholarship metadata_json v1 boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: Literal["scholarship"]
    featured: StrictBool | None
    status: str | None
    application_required: StrictBool | None
    study_stage: list[str]
    student_type: list[str]
    study_level: list[str]
    area_of_study: list[str]
    value: str | None
    selection_basis: str | None
    opening_date: IsoDate | None
    closing_date: IsoDate | None
    eligibility: str | None

    @field_validator("opening_date", "closing_date")
    @classmethod
    def validate_calendar_date(cls, value: str | None) -> str | None:
        if value is not None:
            date.fromisoformat(value)
        return value


CourseProgramMetadata = Annotated[
    CourseMetadata | ProgramMetadata,
    Field(discriminator="entity_type"),
]
CommonMetadata = Annotated[
    CourseMetadata | ProgramMetadata | ScholarshipMetadata,
    Field(discriminator="entity_type"),
]


class CommonRecord(BaseModel):
    """The shared 16-field persisted-record boundary across approved domains."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    source_id: Literal["courses_programs_and_courses", "scholarships_anu_finder"]
    entity_id: str
    domain: Literal["courses", "scholarships"]
    title: str
    content: str = Field(min_length=1)
    canonical_url: HttpUrl
    status: RecordStatus
    effective_from: datetime | None
    effective_to: datetime | None
    collected_at: datetime
    last_seen_at: datetime
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedding_version: str | None
    index_status: IndexStatus
    metadata_json: CommonMetadata

    @field_validator(
        "effective_from",
        "effective_to",
        "collected_at",
        "last_seen_at",
    )
    @classmethod
    def validate_timezone_aware_datetime(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("datetime must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_schema_identity(self) -> "CommonRecord":
        metadata = self.metadata_json
        if isinstance(metadata, CourseMetadata):
            expected_source = "courses_programs_and_courses"
            expected_domain = "courses"
            entity_type = "course"
            expected_entity_id = f"{metadata.course_code}_{metadata.academic_year}"
        elif isinstance(metadata, ProgramMetadata):
            expected_source = "courses_programs_and_courses"
            expected_domain = "courses"
            entity_type = "program"
            expected_entity_id = f"{metadata.program_code}_{metadata.academic_year}"
        else:
            expected_source = "scholarships_anu_finder"
            expected_domain = "scholarships"
            entity_type = "scholarship"
            expected_entity_id = self._scholarship_url_slug()

        if self.source_id != expected_source or self.domain != expected_domain:
            raise ValueError("source_id/domain do not match metadata entity_type")
        if self.entity_id != expected_entity_id:
            raise ValueError("entity_id does not match normalized metadata/source URL")
        expected_record_id = f"{expected_domain}:{entity_type}:{expected_entity_id}"
        if self.record_id != expected_record_id:
            raise ValueError("record_id does not match normalized metadata")
        return self

    def _scholarship_url_slug(self) -> str:
        parsed = urlsplit(str(self.canonical_url))
        host = (parsed.hostname or "").casefold()
        if host != "anu.edu.au" and not host.endswith(".anu.edu.au"):
            raise ValueError("Scholarship canonical_url must use an ANU host")
        if parsed.query or parsed.fragment or parsed.path.endswith("/"):
            raise ValueError("Scholarship canonical_url must be canonical")
        slug = parsed.path.rsplit("/", 1)[-1]
        if not slug:
            raise ValueError("Scholarship canonical_url must contain an entity slug")
        return slug


class CourseProgramRecord(CommonRecord):
    """Backward-compatible Courses/Programs view of a shared record."""

    source_id: Literal["courses_programs_and_courses"]
    domain: Literal["courses"]
    metadata_json: CourseProgramMetadata


class ScholarshipRecord(CommonRecord):
    """Day 9 Scholarship view of a shared record."""

    source_id: Literal["scholarships_anu_finder"]
    domain: Literal["scholarships"]
    metadata_json: ScholarshipMetadata
