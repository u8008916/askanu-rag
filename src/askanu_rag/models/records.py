"""Validated shared schema-v1 persisted records."""

import re
from datetime import date, datetime
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    field_validator,
    model_validator,
)


def _require_non_blank(value: str) -> str:
    """Match the frozen scraper contract: stored strings may not be blank."""

    if not value.strip():
        raise ValueError("value must contain at least one non-whitespace character")
    return value


NonBlankString = Annotated[str, AfterValidator(_require_non_blank)]

RecordStatus = Literal["NEW", "CHANGED", "UNCHANGED", "MISSING"]
IndexStatus = Literal["PENDING", "INDEXED", "FAILED"]
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
SCHOLARSHIP_URL_PREFIX = (
    "https://study.anu.edu.au/scholarships/find-scholarship/"
)
SCHOLARSHIP_PATH_PREFIX = "/scholarships/find-scholarship/"
SCHOLARSHIP_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
JOB_PATH_PATTERN = re.compile(r"^/jobs/[^/\s?#]+$")
JOB_CLOSING_AT_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:[.]\d+)?)?"
    r"(?:Z|[+-]\d{2}:\d{2})$"
)
EVENT_INSTANT_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:[.]\d+)?)?"
    r"(?:Z|[+-]\d{2}:\d{2})$"
)
RESOURCE_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ACCOMMODATION_URL_PREFIX = (
    "https://study.anu.edu.au/accommodation/our-residences/"
)
SUPPORT_URL_PREFIX = "https://anusa.com.au/student-assistance/"
SUPPORT_TOPIC_PATH_PATTERN = re.compile(
    r"^/student-assistance/[a-z0-9]+(?:-[a-z0-9]+)*/"
    r"[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*/?$"
)
COURSES_HOST = "programsandcourses.anu.edu.au"
SUBPLAN_ENTITY_TYPES = ("major", "minor", "specialisation")
COURSES_PATH_PATTERN = re.compile(
    r"^/\d{4}/(?:course|program|major|minor|specialisation)/"
    r"[a-z0-9][a-z0-9._-]*$"
)


class CourseMetadata(BaseModel):
    """Required and recognized schema-v1 course metadata."""

    model_config = ConfigDict(extra="allow", frozen=True)

    entity_type: Literal["course"]
    course_code: str = Field(pattern=r"^[A-Z]{4}\d{4}[A-Z]?$")
    academic_year: str = Field(pattern=r"^\d{4}$")
    career: str | None = None
    units: str | None = None
    delivery_mode: str | None = None
    description: str | None = None
    learning_outcomes: list[str] | None = None
    prerequisites: str | None = None
    corequisites: str | None = None
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
    overview: str | None = None
    learning_outcomes: list[str] | None = None
    program_requirements: str | None = None
    admission_requirements: str | None = None
    prerequisites: str | None = None

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


class JobMetadata(BaseModel):
    """Approved Jobs metadata v2 boundary with source-only requirements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: Literal["job"]
    job_id: str = Field(pattern=r"^\d+$")
    category: str | None
    employment_types: list[str]
    location: str | None
    classification: str | None
    salary: str | None
    closing_text: str | None
    closing_date: IsoDate | None
    closing_at: str | None
    status: Literal["current", "closed"] | None
    summary: str | None
    role_requirements: list[str] | None

    @field_validator("closing_date")
    @classmethod
    def validate_closing_date(cls, value: str | None) -> str | None:
        if value is not None:
            date.fromisoformat(value)
        return value

    @field_validator("closing_at")
    @classmethod
    def validate_closing_at(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if JOB_CLOSING_AT_PATTERN.fullmatch(value) is None:
            raise ValueError("closing_at must use the frozen ISO-8601 shape")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("closing_at must be an ISO-8601 datetime") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("closing_at must include a timezone offset")
        return value

    @field_validator("role_requirements")
    @classmethod
    def validate_role_requirements(
        cls, value: list[str] | None
    ) -> list[str] | None:
        if value is not None and any(not item.strip() for item in value):
            raise ValueError("role_requirements cannot contain blank items")
        return value


class EventMetadata(BaseModel):
    """Qasim-frozen V6 Event metadata boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entity_type: Literal["event"]
    source_event_id: NonBlankString
    start_at: str
    end_at: str | None = None
    timezone: NonBlankString | None = None
    organiser_name: NonBlankString | None = None
    venue_name: NonBlankString | None = None
    address: NonBlankString | None = None
    latitude: float | int | None = None
    longitude: float | int | None = None
    category: NonBlankString | None = None
    tags: list[NonBlankString] | None = None
    registration_url: NonBlankString | None = None
    source_status: NonBlankString | None = None
    cancellation_status: NonBlankString | None = None
    audience: NonBlankString | list[NonBlankString] | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def validate_event_instant(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if EVENT_INSTANT_PATTERN.fullmatch(value) is None:
            raise ValueError("event timestamp must be an ISO-8601 offset datetime")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("event timestamp must include a timezone offset")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_iana_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a recognized IANA timezone") from exc
        return value

class SubplanMetadata(BaseModel):
    """Frozen V6 Major/Minor/Specialisation metadata boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: Literal["major", "minor", "specialisation"]
    subplan_code: str = Field(min_length=1)
    academic_year: str = Field(pattern=r"^\d{4}$")
    career: str | None = None
    units: str | None = None
    subplan_type: str | None = None
    overview: str | None = None
    learning_outcomes: list[str] | None = None
    requirements: str | None = None
    relevant_degrees: list[str] | None = None
    other_information: str | None = None

    @field_validator("subplan_code")
    @classmethod
    def validate_normalized_subplan_code(cls, value: str) -> str:
        if value != value.strip().upper():
            raise ValueError("subplan_code must be trimmed and uppercase")
        return value


class AccommodationRoom(BaseModel):
    """One source-published residence room row with relationships intact."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: NonBlankString
    rate: NonBlankString | None
    contract: NonBlankString | None
    inclusions: NonBlankString | None
    other_fees: NonBlankString | None


class AccommodationContact(BaseModel):
    """Published residence contact fields; not the residence location."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    email: NonBlankString | None
    phone: NonBlankString | None
    location: NonBlankString | None
    hours: NonBlankString | None


class AccommodationMetadata(BaseModel):
    """Qasim-frozen Day 12 Accommodation metadata v1 boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entity_type: Literal["residence"]
    category: NonBlankString | None
    location: NonBlankString | None
    catering_options: list[NonBlankString]
    audiences: list[NonBlankString]
    advertised_rate: NonBlankString | None
    cost_period: NonBlankString | None
    rooms: list[AccommodationRoom]
    features: list[NonBlankString]
    overview: NonBlankString | None
    accessibility: NonBlankString | None
    application_text: NonBlankString | None
    application_url: NonBlankString | None
    eligibility: NonBlankString | None
    contact: AccommodationContact
    vacancy_status: NonBlankString | None

    @field_validator("application_url")
    @classmethod
    def validate_application_url(cls, value: str | None) -> str | None:
        """Accept only an explicitly stored HTTPS StarRez subdomain URL."""

        if value is None:
            return None
        parsed = urlsplit(value)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("application_url has an invalid port") from exc
        host = (parsed.hostname or "").casefold()
        if (
            parsed.scheme != "https"
            or not host.endswith(".starrezhousing.com")
            or host == "starrezhousing.com"
            or parsed.username is not None
            or parsed.password is not None
            or port is not None
        ):
            raise ValueError(
                "application_url must be an HTTPS StarRez subdomain destination"
            )
        return value


class SupportContact(BaseModel):
    """Contact details published for the parent ANUSA category only."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    email: NonBlankString | None
    phone: NonBlankString | None
    location: NonBlankString | None


class SupportTopic(BaseModel):
    """A nested topic that remains inside Student Assistance."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    title: NonBlankString
    description: NonBlankString | None
    url: NonBlankString

    @field_validator("url")
    @classmethod
    def validate_topic_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("topic URL has an invalid port") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"anusa.com.au", "www.anusa.com.au"}
            or SUPPORT_TOPIC_PATH_PATTERN.fullmatch(parsed.path) is None
            or parsed.username is not None
            or parsed.password is not None
            or port is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("topic URL must stay inside ANUSA Student Assistance")
        return value


class SupportReferral(BaseModel):
    """Published external navigation evidence, never a service entity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    label: NonBlankString
    url: NonBlankString

    @field_validator("url")
    @classmethod
    def validate_referral_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("referral URL has an invalid port") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.hostname in {"anusa.com.au", "www.anusa.com.au"}
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("referral URL must be an external HTTP(S) destination")
        return value


class SupportMetadata(BaseModel):
    """Qasim-frozen Day 12 Support metadata v1 boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entity_type: Literal["support_service"]
    category: NonBlankString | None
    purpose: NonBlankString | None
    audiences: list[NonBlankString]
    contact: SupportContact
    hours: NonBlankString | None
    access: NonBlankString | None
    cost: NonBlankString | None
    topics: list[SupportTopic]
    referrals: list[SupportReferral]


CourseProgramMetadata = Annotated[
    CourseMetadata | ProgramMetadata | SubplanMetadata,
    Field(discriminator="entity_type"),
]
CommonMetadata = Annotated[
    CourseMetadata
    | ProgramMetadata
    | SubplanMetadata
    | ScholarshipMetadata
    | JobMetadata
    | AccommodationMetadata
    | SupportMetadata
    | EventMetadata,
    Field(discriminator="entity_type"),
]


class CommonRecord(BaseModel):
    """The shared 16-field persisted-record boundary across approved domains."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    source_id: Literal[
        "courses_programs_and_courses",
        "scholarships_anu_finder",
        "jobs_anu_search",
        "accommodation_anu_study",
        "support_anusa_student_assistance",
        "events_anu_official",
        "rubric_unified_search",
    ]
    entity_id: str
    domain: Literal[
        "courses", "scholarships", "jobs", "accommodation", "support", "events"
    ]
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

    @model_validator(mode="before")
    @classmethod
    def validate_raw_domain_url_boundary(cls, values: object) -> object:
        if not isinstance(values, dict):
            return values
        metadata = values.get("metadata_json")
        entity_type = (
            metadata.get("entity_type")
            if isinstance(metadata, dict)
            else getattr(metadata, "entity_type", None)
        )
        canonical_url = str(values.get("canonical_url"))
        if entity_type in ("course", "program", *SUBPLAN_ENTITY_TYPES):
            metadata_code_key = (
                "course_code"
                if entity_type == "course"
                else "program_code"
                if entity_type == "program"
                else "subplan_code"
            )
            code = (
                metadata.get(metadata_code_key)
                if isinstance(metadata, dict)
                else getattr(metadata, metadata_code_key, None)
            )
            academic_year = (
                metadata.get("academic_year")
                if isinstance(metadata, dict)
                else getattr(metadata, "academic_year", None)
            )
            expected_url = (
                f"https://{COURSES_HOST}/{academic_year}/{entity_type}/"
                f"{str(code).lower()}"
            )
            parsed = urlsplit(canonical_url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != COURSES_HOST
                or parsed.query
                or parsed.fragment
                or COURSES_PATH_PATTERN.fullmatch(parsed.path) is None
                or not isinstance(code, str)
                or not isinstance(academic_year, str)
                or canonical_url != expected_url
            ):
                raise ValueError(
                    "Courses-family canonical_url must match year, entity type, "
                    "and lowercase metadata code"
                )
        elif entity_type == "scholarship":
            entity_id = values.get("entity_id")
            if not isinstance(entity_id, str) or canonical_url != (
                f"{SCHOLARSHIP_URL_PREFIX}{entity_id}"
            ):
                raise ValueError(
                    "Scholarship canonical_url must use the exact boundary"
                )
        elif entity_type == "job":
            parsed = urlsplit(canonical_url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "jobs.anu.edu.au"
                or parsed.query
                or parsed.fragment
                or JOB_PATH_PATTERN.fullmatch(parsed.path) is None
                or canonical_url != f"https://jobs.anu.edu.au{parsed.path}"
            ):
                raise ValueError("Job canonical_url must use the exact boundary")
        elif entity_type == "residence":
            entity_id = values.get("entity_id")
            if (
                not isinstance(entity_id, str)
                or canonical_url != f"{ACCOMMODATION_URL_PREFIX}{entity_id}"
            ):
                raise ValueError(
                    "Accommodation canonical_url must exactly match entity_id"
                )
        elif entity_type == "support_service":
            if (
                not isinstance(values.get("entity_id"), str)
                or canonical_url
                != f"{SUPPORT_URL_PREFIX}{values.get('entity_id')}/"
            ):
                raise ValueError("Support canonical_url must exactly match entity_id")
        elif entity_type == "event":
            parsed = urlsplit(canonical_url)
            try:
                parsed.port
            except ValueError as exc:
                raise ValueError("Event canonical_url has an invalid port") from exc
            source_id = values.get("source_id")
            source_event_id = (
                metadata.get("source_event_id")
                if isinstance(metadata, dict)
                else getattr(metadata, "source_event_id", None)
            )
            if (
                parsed.scheme != "https"
                or parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError("Event canonical_url must be credential-free HTTPS")
            if source_id == "events_anu_official" and (
                parsed.hostname.casefold() != "www.anu.edu.au"
                or not parsed.path.startswith("/events/")
            ):
                raise ValueError(
                    "Official Event canonical_url must be an ANU event-detail page"
                )
            if source_id == "rubric_unified_search":
                event_ids = parse_qs(parsed.query).get("eid", [])
                if (
                    parsed.hostname.casefold() != "campus.hellorubric.com"
                    or parsed.path not in {"", "/"}
                    or len(event_ids) != 1
                    or not event_ids[0].strip()
                    or event_ids[0] != source_event_id
                ):
                    raise ValueError(
                        "Rubric canonical_url must be its public event page, "
                        "not the internal detail API"
                    )
        return values

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
        elif isinstance(metadata, SubplanMetadata):
            expected_source = "courses_programs_and_courses"
            expected_domain = "courses"
            entity_type = metadata.entity_type
            expected_entity_id = f"{metadata.subplan_code}_{metadata.academic_year}"
        elif isinstance(metadata, ScholarshipMetadata):
            expected_source = "scholarships_anu_finder"
            expected_domain = "scholarships"
            entity_type = "scholarship"
            expected_entity_id = self._scholarship_url_slug()
            if self.effective_from is not None or self.effective_to is not None:
                raise ValueError(
                    "Scholarship effective_from/effective_to must be null"
                )
        elif isinstance(metadata, JobMetadata):
            expected_source = "jobs_anu_search"
            expected_domain = "jobs"
            entity_type = "job"
            expected_entity_id = metadata.job_id
            if self.effective_from is not None or self.effective_to is not None:
                raise ValueError("Job effective_from/effective_to must be null")
        elif isinstance(metadata, AccommodationMetadata):
            expected_source = "accommodation_anu_study"
            expected_domain = "accommodation"
            entity_type = "residence"
            expected_entity_id = self.entity_id
            if RESOURCE_SLUG_PATTERN.fullmatch(self.entity_id) is None:
                raise ValueError("Accommodation entity_id must be a stable slug")
        elif isinstance(metadata, SupportMetadata):
            expected_source = "support_anusa_student_assistance"
            expected_domain = "support"
            entity_type = "support_service"
            expected_entity_id = self.entity_id
            if RESOURCE_SLUG_PATTERN.fullmatch(self.entity_id) is None:
                raise ValueError("Support entity_id must be a stable slug")
        else:
            expected_source = self.source_id
            expected_domain = "events"
            entity_type = "event"
            if expected_source not in {
                "events_anu_official",
                "rubric_unified_search",
            }:
                raise ValueError("Event source_id is not approved")
            expected_entity_id = (
                metadata.source_event_id
                if expected_source == "events_anu_official"
                else f"rubric-{metadata.source_event_id}"
            )

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
        if parsed.scheme != "https" or parsed.netloc != "study.anu.edu.au":
            raise ValueError("Scholarship canonical_url must use the approved host")
        if parsed.query or parsed.fragment:
            raise ValueError("Scholarship canonical_url must not contain query/fragment")
        if not parsed.path.startswith(SCHOLARSHIP_PATH_PREFIX):
            raise ValueError("Scholarship canonical_url must use the approved path")
        slug = parsed.path.removeprefix(SCHOLARSHIP_PATH_PREFIX)
        if not SCHOLARSHIP_SLUG_PATTERN.fullmatch(slug):
            raise ValueError("Scholarship canonical_url must end in an approved slug")
        if not SCHOLARSHIP_SLUG_PATTERN.fullmatch(self.entity_id):
            raise ValueError("Scholarship entity_id must use the approved slug form")
        if str(self.canonical_url) != f"{SCHOLARSHIP_URL_PREFIX}{slug}":
            raise ValueError("Scholarship canonical_url must use the exact boundary")
        return slug


class CourseProgramRecord(CommonRecord):
    """Courses-family record; the legacy DB view still exposes Course/Program only."""

    source_id: Literal["courses_programs_and_courses"]
    domain: Literal["courses"]
    metadata_json: CourseProgramMetadata


class ScholarshipRecord(CommonRecord):
    """Day 9 Scholarship view of a shared record."""

    source_id: Literal["scholarships_anu_finder"]
    domain: Literal["scholarships"]
    metadata_json: ScholarshipMetadata


class JobRecord(CommonRecord):
    """Day 10 Job view of a shared record."""

    source_id: Literal["jobs_anu_search"]
    domain: Literal["jobs"]
    metadata_json: JobMetadata


class AccommodationRecord(CommonRecord):
    """Approved ANU Study accommodation record view."""

    source_id: Literal["accommodation_anu_study"]
    domain: Literal["accommodation"]
    metadata_json: AccommodationMetadata


class SupportRecord(CommonRecord):
    """Approved ANUSA student-assistance service record view."""

    source_id: Literal["support_anusa_student_assistance"]
    domain: Literal["support"]
    metadata_json: SupportMetadata


class EventRecord(CommonRecord):
    """Frozen V6 Event view of the shared source_records envelope."""

    source_id: Literal["events_anu_official", "rubric_unified_search"]
    domain: Literal["events"]
    metadata_json: EventMetadata
