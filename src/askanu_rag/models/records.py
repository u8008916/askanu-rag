"""Validated Courses/Programs schema-v1 normalized records."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

RecordStatus = Literal["NEW", "CHANGED", "UNCHANGED", "MISSING"]
IndexStatus = Literal["PENDING", "INDEXED", "FAILED"]


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


CourseProgramMetadata = Annotated[
    CourseMetadata | ProgramMetadata,
    Field(discriminator="entity_type"),
]


class CourseProgramRecord(BaseModel):
    """Full serialized Courses/Programs schema-v1 boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    source_id: Literal["courses_programs_and_courses"]
    entity_id: str
    domain: Literal["courses"]
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
    metadata_json: CourseProgramMetadata

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
    def validate_schema_identity(self) -> "CourseProgramRecord":
        metadata = self.metadata_json
        if isinstance(metadata, CourseMetadata):
            entity_type = "course"
            code = metadata.course_code
        else:
            entity_type = "program"
            code = metadata.program_code

        expected_entity_id = f"{code}_{metadata.academic_year}"
        expected_record_id = f"courses:{entity_type}:{expected_entity_id}"

        if self.entity_id != expected_entity_id:
            raise ValueError("entity_id does not match normalized metadata")
        if self.record_id != expected_record_id:
            raise ValueError("record_id does not match normalized metadata")
        return self
