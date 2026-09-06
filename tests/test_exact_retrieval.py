"""Day 2 schema boundary and deterministic exact-retrieval tests."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from askanu_rag.models import (
    CourseMetadata,
    CourseProgramRecord,
    ProgramMetadata,
)
from askanu_rag.retrieval import (
    CourseProgramRepository,
    load_course_program_records,
    normalize_course_code,
    normalize_program_code,
)

FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "day2_course_program_records.json"
)
EXPECTED_TOP_LEVEL_FIELDS = {
    "record_id",
    "source_id",
    "entity_id",
    "domain",
    "title",
    "content",
    "canonical_url",
    "status",
    "effective_from",
    "effective_to",
    "collected_at",
    "last_seen_at",
    "content_hash",
    "embedding_version",
    "index_status",
    "metadata_json",
}


@pytest.fixture(scope="module")
def fixture_payload() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def records() -> tuple[CourseProgramRecord, ...]:
    return load_course_program_records(FIXTURE_PATH)


@pytest.fixture(scope="module")
def repository(
    records: tuple[CourseProgramRecord, ...],
) -> CourseProgramRepository:
    return CourseProgramRepository(records)


def copy_record_payload(
    fixture_payload: list[dict[str, object]], index: int = 0
) -> dict[str, object]:
    payload = dict(fixture_payload[index])
    payload["metadata_json"] = dict(payload["metadata_json"])
    return payload


def test_loader_accepts_full_course_and_program_schema(
    records: tuple[CourseProgramRecord, ...],
) -> None:
    assert len(records) == 4
    assert all(
        set(record.model_dump()) == EXPECTED_TOP_LEVEL_FIELDS
        for record in records
    )
    assert isinstance(records[0].metadata_json, CourseMetadata)
    assert isinstance(records[2].metadata_json, ProgramMetadata)


def test_loader_requires_a_json_array(tmp_path: Path) -> None:
    fixture = tmp_path / "not-an-array.json"
    fixture.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON array"):
        load_course_program_records(fixture)


def test_unknown_top_level_field_is_rejected(
    fixture_payload: list[dict[str, object]],
) -> None:
    payload = copy_record_payload(fixture_payload)
    payload["invented_field"] = "not allowed"

    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(payload)


@pytest.mark.parametrize("field", ["source_id", "content_hash", "metadata_json"])
def test_required_top_level_field_is_rejected_when_missing(
    fixture_payload: list[dict[str, object]], field: str
) -> None:
    payload = copy_record_payload(fixture_payload)
    del payload[field]

    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(payload)


def test_nullable_fields_accept_explicit_null(
    fixture_payload: list[dict[str, object]],
) -> None:
    record = CourseProgramRecord.model_validate(fixture_payload[0])

    assert record.effective_from is None
    assert record.effective_to is None
    assert record.embedding_version is None


@pytest.mark.parametrize(
    "field", ["effective_from", "effective_to", "embedding_version"]
)
def test_nullable_top_level_keys_are_still_required(
    fixture_payload: list[dict[str, object]], field: str
) -> None:
    payload = copy_record_payload(fixture_payload)
    del payload[field]

    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(payload)


@pytest.mark.parametrize("field", ["collected_at", "last_seen_at"])
def test_required_timestamp_must_be_timezone_aware(
    fixture_payload: list[dict[str, object]], field: str
) -> None:
    payload = copy_record_payload(fixture_payload)
    payload[field] = "2026-09-06T09:00:00"

    with pytest.raises(ValidationError, match="timezone"):
        CourseProgramRecord.model_validate(payload)


def test_optional_timestamp_must_be_timezone_aware_when_present(
    fixture_payload: list[dict[str, object]],
) -> None:
    payload = copy_record_payload(fixture_payload)
    payload["effective_from"] = "2026-01-01T00:00:00"

    with pytest.raises(ValidationError, match="timezone"):
        CourseProgramRecord.model_validate(payload)


def test_timezone_offset_is_preserved_in_json_serialization(
    records: tuple[CourseProgramRecord, ...],
) -> None:
    serialized = records[0].model_dump(mode="json")

    assert serialized["collected_at"].endswith("+10:00")
    assert serialized["last_seen_at"].endswith("+10:00")


@pytest.mark.parametrize(
    "bad_hash",
    ["abc", "A" * 64, "g" * 64],
)
def test_content_hash_must_be_lowercase_sha256_shape(
    fixture_payload: list[dict[str, object]], bad_hash: str
) -> None:
    payload = copy_record_payload(fixture_payload)
    payload["content_hash"] = bad_hash

    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(payload)


def test_content_must_not_be_empty(
    fixture_payload: list[dict[str, object]],
) -> None:
    payload = copy_record_payload(fixture_payload)
    payload["content"] = ""

    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "ACTIVE"), ("index_status", "READY")],
)
def test_status_fields_use_frozen_values(
    fixture_payload: list[dict[str, object]], field: str, value: str
) -> None:
    payload = copy_record_payload(fixture_payload)
    payload[field] = value

    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [("source_id", "another_source"), ("domain", "programs")],
)
def test_source_and_domain_use_frozen_values(
    fixture_payload: list[dict[str, object]], field: str, value: str
) -> None:
    payload = copy_record_payload(fixture_payload)
    payload[field] = value

    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(payload)


@pytest.mark.parametrize("field", ["entity_type", "course_code", "academic_year"])
def test_course_metadata_requires_identity_fields(
    fixture_payload: list[dict[str, object]], field: str
) -> None:
    payload = copy_record_payload(fixture_payload)
    metadata = payload["metadata_json"]
    del metadata[field]

    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(payload)


@pytest.mark.parametrize("bad_year", ["26", "20260", "20A6", 2026])
def test_academic_year_is_a_four_digit_string(
    fixture_payload: list[dict[str, object]], bad_year: object
) -> None:
    payload = copy_record_payload(fixture_payload)
    metadata = payload["metadata_json"]
    metadata["academic_year"] = bad_year

    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(payload)


@pytest.mark.parametrize("field", ["entity_type", "program_code", "academic_year"])
def test_program_metadata_requires_identity_fields(
    fixture_payload: list[dict[str, object]], field: str
) -> None:
    payload = copy_record_payload(fixture_payload, index=2)
    metadata = payload["metadata_json"]
    del metadata[field]

    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(payload)


@pytest.mark.parametrize("program_code", ["bacct", " BACCT "])
def test_stored_program_code_must_already_be_normalized(
    fixture_payload: list[dict[str, object]], program_code: str
) -> None:
    payload = copy_record_payload(fixture_payload, index=2)
    metadata = payload["metadata_json"]
    metadata["program_code"] = program_code

    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(payload)


def test_optional_course_metadata_accepts_null(
    records: tuple[CourseProgramRecord, ...],
) -> None:
    metadata = records[1].metadata_json

    assert isinstance(metadata, CourseMetadata)
    assert metadata.career is None
    assert metadata.offerings is None


def test_optional_program_metadata_accepts_null(
    records: tuple[CourseProgramRecord, ...],
) -> None:
    metadata = records[2].metadata_json

    assert isinstance(metadata, ProgramMetadata)
    assert metadata.duration is None
    assert metadata.learning_outcomes is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("COMP1100", "COMP1100"),
        ("comp1100", "COMP1100"),
        ("CoMp1100", "COMP1100"),
        (" comp 1100 ", "COMP1100"),
        ("BIOL9001P", "BIOL9001P"),
    ],
)
def test_course_code_normalization(raw: str, expected: str) -> None:
    assert normalize_course_code(raw) == expected


@pytest.mark.parametrize("raw", ["COMP110", "COMP11000", "COM1100", "COMP-1100"])
def test_invalid_course_shape_does_not_normalize(raw: str) -> None:
    assert normalize_course_code(raw) is None


@pytest.mark.parametrize("raw", ["BACCT", "bacct", " bacct "])
def test_program_code_normalization(raw: str) -> None:
    assert normalize_program_code(raw) == "BACCT"


def test_program_code_normalization_does_not_invent_a_grammar() -> None:
    assert normalize_program_code("B ACCT") == "B ACCT"


def test_explicit_year_lookup_is_deterministic(
    repository: CourseProgramRepository,
) -> None:
    record_2026 = repository.find_course_by_code("comp 1100", "2026")
    record_2027 = repository.find_course_by_code("COMP1100", "2027")

    assert isinstance(record_2026, CourseProgramRecord)
    assert isinstance(record_2027, CourseProgramRecord)
    assert record_2026.entity_id == "COMP1100_2026"
    assert record_2027.entity_id == "COMP1100_2027"


@pytest.mark.parametrize("identifier", ["COMP1110", "COMP 1110", "comp1110"])
def test_comp1110_variants_retrieve_the_same_schema_v1_record(
    fixture_payload: list[dict[str, object]],
    repository: CourseProgramRepository,
    identifier: str,
) -> None:
    result = repository.find_course_by_code(identifier, "2026")
    stored = next(
        item
        for item in fixture_payload
        if item["record_id"] == "courses:course:COMP1110_2026"
    )

    assert isinstance(result, CourseProgramRecord)
    assert isinstance(result.metadata_json, CourseMetadata)
    assert result.metadata_json.course_code == "COMP1110"
    assert result.metadata_json.academic_year == "2026"
    assert result.entity_id == "COMP1110_2026"
    assert result.record_id == "courses:course:COMP1110_2026"
    assert result.source_id == "courses_programs_and_courses"
    assert result.domain == "courses"
    assert str(result.canonical_url) == stored["canonical_url"]
    assert result.content_hash == stored["content_hash"]
    assert result.content_hash == (
        "ab3484047890d18c871133ede5055122d4b868f5ff3b9ed04c97828574429978"
    )


def test_code_only_lookup_returns_the_sole_comp1110_year(
    repository: CourseProgramRepository,
) -> None:
    result = repository.find_course_by_code("COMP1110")

    assert isinstance(result, CourseProgramRecord)
    assert result.entity_id == "COMP1110_2026"


def test_code_only_lookup_preserves_multi_year_ambiguity(
    repository: CourseProgramRepository,
) -> None:
    result = repository.find_course_by_code("COMP1100")

    assert isinstance(result, tuple)
    assert [record.entity_id for record in result] == [
        "COMP1100_2026",
        "COMP1100_2027",
    ]


def test_code_only_lookup_returns_single_program_record(
    repository: CourseProgramRepository,
) -> None:
    result = repository.find_program_by_code(" bacct ")

    assert isinstance(result, CourseProgramRecord)
    assert result.entity_id == "BACCT_2026"


def test_lookup_does_not_apply_course_grammar_to_program_codes(
    repository: CourseProgramRepository,
) -> None:
    assert repository.find_program_by_code("B ACCT", "2026") is None


def test_unknown_identifiers_and_year_return_none(
    repository: CourseProgramRepository,
) -> None:
    assert repository.find_course_by_code("NOT-A-COURSE") is None
    assert repository.find_course_by_code("COMP1100", "2030") is None
    assert repository.find_program_by_code("UNKNOWN", "2026") is None
    assert repository.find_program_by_code("   ") is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entity_id", "COMP1100_2025"),
        ("record_id", "courses:program:COMP1100_2026"),
    ],
)
def test_record_identity_must_match_metadata(
    fixture_payload: list[dict[str, object]], field: str, value: str
) -> None:
    payload = copy_record_payload(fixture_payload)
    payload[field] = value

    with pytest.raises(ValidationError, match="does not match"):
        CourseProgramRecord.model_validate(payload)


def test_duplicate_exact_lookup_key_is_rejected(
    records: tuple[CourseProgramRecord, ...],
) -> None:
    with pytest.raises(ValueError, match="Duplicate exact lookup key"):
        CourseProgramRepository([records[0], records[0]])


def test_stored_provenance_url_and_hash_are_preserved(
    fixture_payload: list[dict[str, object]],
    repository: CourseProgramRepository,
) -> None:
    record = repository.find_course_by_code("COMP1100", "2026")
    raw = fixture_payload[0]

    assert isinstance(record, CourseProgramRecord)
    assert record.source_id == raw["source_id"]
    assert str(record.canonical_url) == raw["canonical_url"]
    assert record.content_hash == raw["content_hash"]
    assert hashlib.sha256(record.content.encode("utf-8")).hexdigest() == (
        record.content_hash
    )
