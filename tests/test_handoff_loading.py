"""Consume scraper-style files with synthetic test data, without a scraper checkout."""

import hashlib
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from askanu_rag.main import create_app
from askanu_rag.models import CourseProgramRecord
from askanu_rag.retrieval import (
    CourseProgramRepository,
    load_course_program_record_file,
    load_course_program_records_directory,
)


def synthetic_payload(code="COMP1110", year="2026", entity_type="course"):
    """Test-only identity/provenance; makes no real course prerequisite claim."""

    content = f"Synthetic handoff test record: {code} ({year}) — no factual claims."
    metadata = {
        "entity_type": entity_type,
        f"{entity_type}_code": code,
        "academic_year": year,
        "career": None,
        "units": None,
        "delivery_mode": None,
    }
    if entity_type == "course":
        metadata.update(
            prerequisites=None, incompatibilities=None,
            assumed_knowledge=None, offerings=None,
        )
    else:
        metadata.update(duration=None, learning_outcomes=None)
    return {
        "record_id": f"courses:{entity_type}:{code}_{year}",
        "source_id": "courses_programs_and_courses",
        "entity_id": f"{code}_{year}",
        "domain": "courses",
        "title": f"Synthetic {code} handoff test record",
        "content": content,
        "canonical_url": f"https://programsandcourses.anu.edu.au/{year}/{entity_type}/{code}",
        "status": "UNCHANGED",
        "effective_from": None,
        "effective_to": None,
        "collected_at": "2026-09-07T09:00:00+10:00",
        "last_seen_at": "2026-09-07T10:00:00+10:00",
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "embedding_version": None,
        "index_status": "PENDING",
        "metadata_json": metadata,
    }


def write_record(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def records_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "records"
    directory.mkdir()
    # Creation order differs from expected filename order.
    for filename, payload in [
        ("courses__program__BACCT_2026.json", synthetic_payload("BACCT", entity_type="program")),
        ("courses__course__COMP1110_2026.json", synthetic_payload()),
        ("courses__course__COMP1100_2027.json", synthetic_payload("COMP1100", "2027")),
        ("courses__course__COMP1100_2026.json", synthetic_payload("COMP1100")),
    ]:
        write_record(directory / filename, payload)
    return directory


@pytest.mark.parametrize("code,entity_type", [("COMP1110", "course"), ("BACCT", "program")])
def test_single_record_preserves_complete_serialized_boundary(tmp_path, code, entity_type):
    payload = synthetic_payload(code, entity_type=entity_type)
    path = write_record(tmp_path / "arbitrary-name.json", payload)

    record = load_course_program_record_file(path)

    assert isinstance(record, CourseProgramRecord)
    assert len(record.model_dump()) == 16
    assert record.model_dump(mode="json") == payload


@pytest.mark.parametrize("raw", ['{"broken":', "[]", "null", "{}"])
def test_single_record_rejects_malformed_json_or_non_record(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(ValidationError) as caught:
        load_course_program_record_file(path)
    assert str(path) in caught.value.__notes__[0]


@pytest.mark.parametrize(
    "field,value",
    [
        ("record_id", "courses:course:COMP1110_2027"),
        ("entity_id", "COMP1110_2027"),
        ("source_id", "unapproved"),
        ("content_hash", "invalid"),
        ("collected_at", "2026-09-07T09:00:00"),
        ("canonical_url", "not a URL"),
        ("metadata_json", {"entity_type": "course", "course_code": "COMP1110"}),
        ("extra_top_level", "must not be dropped"),
    ],
)
def test_invalid_schema_is_rejected_by_existing_model(tmp_path, field, value):
    payload = synthetic_payload()
    payload[field] = value
    path = write_record(tmp_path / "bad.json", payload)

    with pytest.raises(ValidationError):
        load_course_program_record_file(path)


def test_required_field_is_not_invented(tmp_path):
    payload = synthetic_payload()
    del payload["source_id"]
    path = write_record(tmp_path / "missing-field.json", payload)
    with pytest.raises(ValidationError):
        load_course_program_record_file(path)


def test_hash_and_url_are_preserved_without_recalculation_or_reconstruction(tmp_path):
    payload = synthetic_payload()
    # Existing RAG model validates hash shape, not hash equality; loader must reuse it.
    payload["content_hash"] = "0" * 64
    payload["canonical_url"] = "https://programsandcourses.anu.edu.au/Stored/Canonical?version=one"
    payload["metadata_json"]["source_note"] = "Synthetic extension evidence"
    record = load_course_program_record_file(write_record(tmp_path / "opaque.json", payload))
    assert record.model_dump(mode="json") == payload


def test_identity_comes_from_json_not_filename(tmp_path):
    path = write_record(tmp_path / "courses__course__FAKE9999_2099.json", synthetic_payload())
    record = load_course_program_records_directory(tmp_path)[0]
    assert record.record_id == "courses:course:COMP1110_2026"
    assert record.metadata_json.academic_year == "2026"
    assert path.exists()


def test_directory_order_and_multi_year_repository_lookup(records_directory):
    records = load_course_program_records_directory(records_directory)
    assert [record.record_id for record in records] == [
        "courses:course:COMP1100_2026", "courses:course:COMP1100_2027",
        "courses:course:COMP1110_2026", "courses:program:BACCT_2026",
    ]
    repository = CourseProgramRepository(records)
    assert repository.find_course_by_code("comp 1110") == records[2]
    assert repository.find_program_by_code("bacct") == records[3]
    assert repository.find_course_by_code("COMP1100") == records[:2]
    assert repository.find_course_by_code("COMP1100", "2026") == records[0]
    assert repository.find_course_by_code("COMP1100", "2027") == records[1]
    assert repository.find_course_by_code("COMP1100", "2030") is None


def test_directory_does_not_read_runs_nested_files_or_non_json(records_directory):
    (records_directory.parent / "runs").mkdir()
    (records_directory.parent / "runs" / "run_123.json").write_text("{}")
    (records_directory / "nested").mkdir()
    (records_directory / "nested" / "invalid.json").write_text("invalid JSON")
    (records_directory / "README.txt").write_text("not JSON")
    assert len(load_course_program_records_directory(records_directory)) == 4


@pytest.mark.parametrize("raw", ["{", "[]", '{"run_id": "run_123"}'])
def test_directory_fails_instead_of_skipping_invalid_json(records_directory, raw):
    bad_file = records_directory / "zzz-invalid.json"
    bad_file.write_text(raw, encoding="utf-8")
    with pytest.raises(ValidationError) as caught:
        load_course_program_records_directory(records_directory)
    assert str(bad_file) in caught.value.__notes__[0]


def test_empty_directory_returns_empty_tuple(tmp_path):
    assert load_course_program_records_directory(tmp_path) == ()


@pytest.mark.parametrize("loader", [load_course_program_record_file, load_course_program_records_directory])
def test_missing_path_raises_file_not_found(tmp_path, loader):
    with pytest.raises(FileNotFoundError):
        loader(tmp_path / "missing")


def test_directory_loader_rejects_regular_file(tmp_path):
    path = write_record(tmp_path / "record.json", synthetic_payload())
    with pytest.raises(NotADirectoryError):
        load_course_program_records_directory(path)


def test_record_loader_rejects_directory(tmp_path):
    with pytest.raises(ValueError, match="regular file"):
        load_course_program_record_file(tmp_path)


def test_duplicate_records_are_still_rejected_by_repository(tmp_path):
    for filename in ("one.json", "two.json"):
        write_record(tmp_path / filename, synthetic_payload())
    records = load_course_program_records_directory(tmp_path)
    assert len(records) == 2
    with pytest.raises(ValueError, match="Duplicate exact lookup key"):
        CourseProgramRepository(records)


@pytest.mark.parametrize("entry_kind", ["symlink", "reparse_point"])
@pytest.mark.parametrize("target_kind", ["record", "directory"])
def test_link_entries_are_rejected_without_reading_target(tmp_path, monkeypatch, entry_kind, target_kind):
    # Model lstat results so Windows symlink privileges are not required.
    path = tmp_path / "linked"
    original_lstat = Path.lstat

    def link_stat(entry):
        if entry == path:
            return SimpleNamespace(
                st_mode=stat.S_IFLNK if entry_kind == "symlink" else stat.S_IFDIR,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT if entry_kind == "reparse_point" else 0,
            )
        return original_lstat(entry)

    monkeypatch.setattr(Path, "lstat", link_stat)
    loader = load_course_program_record_file if target_kind == "record" else load_course_program_records_directory
    with pytest.raises(ValueError, match="link or reparse point"):
        loader(path)


def test_directory_rejects_json_symlink(tmp_path):
    outside = write_record(tmp_path / "outside.json", synthetic_payload())
    records = tmp_path / "records"
    records.mkdir()
    try:
        (records / "linked.json").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Creating symlinks is unavailable: {exc}")
    with pytest.raises(ValueError, match="link or reparse point"):
        load_course_program_records_directory(records)


def test_api_from_individual_handoff_files(records_directory):
    # No Day 2 JSON-array fixture is used to populate this injected repository.
    records = load_course_program_records_directory(records_directory)
    repository = CourseProgramRepository(records)
    stored = repository.find_course_by_code("COMP1110")
    with TestClient(create_app(repository=repository)) as client:
        response = client.post("/api/v1/ask", json={
            "question": "What are the prerequisites for COMP1110?",
            "history": [], "conversation_state": {"pending_clarification": None},
        })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_evidence"
    assert "does not establish its prerequisites" in body["answer"]
    assert "no prerequisites" not in body["answer"].lower()
    assert body["items"] == []
    assert body["clarification"] is None
    assert body["request_id"].startswith("req_")
    assert body["sources"] == [{
        "record_id": stored.record_id, "source_id": stored.source_id,
        "title": stored.title, "url": str(stored.canonical_url), "domain": stored.domain,
    }]
    print(json.dumps({
        "records_directory": str(records_directory),
        "records_loaded": len(records), "repository_unique_record_count": len({r.record_id for r in records}),
        "comp1110_record_id": stored.record_id, "http_status": response.status_code,
        "response_status": body["status"], "source_url": body["sources"][0]["url"],
        "prerequisites": stored.metadata_json.prerequisites,
    }))
