"""Frozen V6 Courses-family model, identity, URL and retrieval contract."""

import asyncio
import hashlib
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from askanu_rag.hybrid_queries import HybridQueryService
from askanu_rag.models import (
    CourseMetadata,
    CourseProgramRecord,
    ProgramMetadata,
    SubplanMetadata,
)
from askanu_rag.query_planner import plan_query
from askanu_rag.retrieval import CourseProgramRepository


def make_subplan(
    entity_type: str = "major",
    code: str = "ACCT-MAJ",
    *,
    title: str = "Accounting Major",
    year: str = "2026",
) -> CourseProgramRecord:
    content = (
        f"Entity Type: {entity_type}\nTitle: {title}\nSubplan Code: {code}\n"
        f"Academic Year: {year}\nCareer: Undergraduate\nUnits: 48\n"
        "Overview: Study accounting practice and analysis.\n"
        "Learning Outcomes:\n- Apply accounting concepts.\n"
        "Requirements: Complete 48 units from the published course list.\n"
        "Relevant Degrees:\n- Bachelor of Accounting\n"
        "Other Information: Consult the official study requirements."
    )
    observed = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)
    return CourseProgramRecord(
        record_id=f"courses:{entity_type}:{code}_{year}",
        source_id="courses_programs_and_courses",
        entity_id=f"{code}_{year}",
        domain="courses",
        title=title,
        content=content,
        canonical_url=(
            f"https://programsandcourses.anu.edu.au/{year}/"
            f"{entity_type}/{code.lower()}"
        ),
        status="NEW",
        effective_from=None,
        effective_to=None,
        collected_at=observed,
        last_seen_at=observed,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        embedding_version=None,
        index_status="PENDING",
        metadata_json=SubplanMetadata(
            entity_type=entity_type,
            subplan_code=code,
            academic_year=year,
            career="Undergraduate",
            units="48",
            subplan_type=entity_type.title(),
            overview="Study accounting practice and analysis.",
            learning_outcomes=["Apply accounting concepts."],
            requirements="Complete 48 units from the published course list.",
            relevant_degrees=["Bachelor of Accounting"],
            other_information="Consult the official study requirements.",
        ),
    )


@pytest.mark.parametrize(
    ("entity_type", "code"),
    [
        ("major", "ACCT-MAJ"),
        ("minor", "AAGR-MIN"),
        ("specialisation", "MEAS-SPEC"),
    ],
)
def test_valid_subplan_records_and_lowercase_canonical_paths(entity_type, code):
    record = make_subplan(entity_type, code)

    assert record.metadata_json.entity_type == entity_type
    assert record.entity_id == f"{code}_2026"
    assert record.record_id == f"courses:{entity_type}:{code}_2026"
    assert str(record.canonical_url).endswith(f"/{entity_type}/{code.lower()}")
    assert record.effective_from is None and record.effective_to is None


@pytest.mark.parametrize("code", ["acct-maj", " ACCT-MAJ "])
def test_subplan_metadata_code_must_arrive_trimmed_and_uppercase(code):
    with pytest.raises(ValidationError, match="trimmed and uppercase"):
        SubplanMetadata(entity_type="major", subplan_code=code, academic_year="2026")


@pytest.mark.parametrize(
    "canonical_url",
    [
        "http://programsandcourses.anu.edu.au/2026/major/acct-maj",
        "https://evil.example/2026/major/acct-maj",
        "https://programsandcourses.anu.edu.au:443/2026/major/acct-maj",
        "https://programsandcourses.anu.edu.au/2025/major/acct-maj",
        "https://programsandcourses.anu.edu.au/2026/minor/acct-maj",
        "https://programsandcourses.anu.edu.au/2026/major/ACCT-MAJ",
        "https://programsandcourses.anu.edu.au/2026/major/other-maj",
        "https://programsandcourses.anu.edu.au/2026/major/acct-maj?x=1",
        "https://programsandcourses.anu.edu.au/2026/major/acct-maj#overview",
        "https://programsandcourses.anu.edu.au/2026/major/acct-maj/",
    ],
)
def test_subplan_rejects_noncanonical_or_mismatched_url(canonical_url):
    values = make_subplan().model_dump(mode="json")
    values["canonical_url"] = canonical_url
    with pytest.raises(ValidationError, match="canonical_url"):
        CourseProgramRecord.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_id", "scholarships_anu_finder"),
        ("domain", "scholarships"),
        ("entity_id", "OTHER-MAJ_2026"),
        ("record_id", "courses:program:ACCT-MAJ_2026"),
    ],
)
def test_subplan_rejects_mismatched_provenance_and_identity(field, value):
    values = make_subplan().model_dump(mode="json")
    values[field] = value
    with pytest.raises(ValidationError):
        CourseProgramRecord.model_validate(values)


def test_subplan_rejects_invalid_academic_year():
    with pytest.raises(ValidationError):
        SubplanMetadata(
            entity_type="major", subplan_code="ACCT-MAJ", academic_year="26"
        )


def test_subplan_rejects_unknown_metadata_but_course_program_remain_extensible():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SubplanMetadata(
            entity_type="major",
            subplan_code="ACCT-MAJ",
            academic_year="2026",
            invented_field="not approved",
        )
    course = CourseMetadata(
        entity_type="course",
        course_code="COMP1110",
        academic_year="2026",
        future_source_field="preserved",
    )
    program = ProgramMetadata(
        entity_type="program",
        program_code="BACCT",
        academic_year="2026",
        future_source_field="preserved",
    )
    assert course.model_extra == {"future_source_field": "preserved"}
    assert program.model_extra == {"future_source_field": "preserved"}


@pytest.mark.parametrize(
    "query_session",
    ["First Semester", "first semester", "SEMESTER 1"],
)
def test_session_matching_normalizes_query_and_stored_forms(query_session):
    course = CourseProgramRecord.model_validate(
        {
            **make_subplan().model_dump(mode="json"),
            "record_id": "courses:course:COMP1110_2026",
            "entity_id": "COMP1110_2026",
            "canonical_url": "https://programsandcourses.anu.edu.au/2026/course/comp1110",
            "metadata_json": CourseMetadata(
                entity_type="course",
                course_code="COMP1110",
                academic_year="2026",
                offerings=[{"session": "First Semester, 2026"}],
            ).model_dump(mode="json"),
        }
    )
    repository = CourseProgramRepository((course,))
    plan = plan_query(
        f"List courses offered in {query_session} in 2026", repository
    )
    assert HybridQueryService(repository).retrieve(plan) == (course,)


@pytest.mark.parametrize(
    ("entity_type", "code", "metadata"),
    [
        (
            "course",
            "COMP1110",
            CourseMetadata(
                entity_type="course", course_code="COMP1110", academic_year="2026"
            ),
        ),
        (
            "program",
            "BACCT",
            ProgramMetadata(
                entity_type="program", program_code="BACCT", academic_year="2026"
            ),
        ),
    ],
)
def test_course_and_program_require_lowercase_canonical_path(
    entity_type, code, metadata
):
    values = make_subplan().model_dump(mode="json")
    values.update(
        record_id=f"courses:{entity_type}:{code}_2026",
        entity_id=f"{code}_2026",
        canonical_url=(
            f"https://programsandcourses.anu.edu.au/2026/"
            f"{entity_type}/{code.lower()}"
        ),
    )
    values["metadata_json"] = metadata.model_dump(mode="json")
    assert CourseProgramRecord.model_validate(values).entity_id == f"{code}_2026"

    values["canonical_url"] = (
        f"https://programsandcourses.anu.edu.au/2026/{entity_type}/{code}"
    )
    with pytest.raises(ValidationError, match="canonical_url"):
        CourseProgramRecord.model_validate(values)


def test_repository_identity_distinguishes_entity_type_and_rejects_duplicates():
    major = make_subplan("major", "SHARED-CODE")
    minor = make_subplan("minor", "SHARED-CODE", title="Shared-code Minor")
    repository = CourseProgramRepository((major, minor))

    assert repository.find_by_code("major", "shared-code", "2026") == major
    assert repository.find_by_code("minor", "shared-code", "2026") == minor
    response = asyncio.run(
        HybridQueryService(repository).answer("SHARED-CODE", "req-shared")
    )
    assert response.status == "needs_clarification"
    assert {option.id for option in response.clarification.options} == {
        major.record_id,
        minor.record_id,
    }
    assert {option.label.split(" ", 1)[0] for option in response.clarification.options} == {
        "Major",
        "Minor",
    }
    with pytest.raises(ValueError, match="Duplicate exact lookup key"):
        CourseProgramRepository((major, major))


def test_new_course_and_program_fields_preserve_source_text_and_nulls():
    course = CourseMetadata(
        entity_type="course",
        course_code="COMP1110",
        academic_year="2026",
        description="Source description.",
        learning_outcomes=["Source learning outcome."],
        corequisites="MATH1005",
    )
    program = ProgramMetadata(
        entity_type="program",
        program_code="BACCT",
        academic_year="2026",
        overview="Source overview.",
        program_requirements="Source program requirements.",
        admission_requirements="Source admission requirements.",
        prerequisites="Source prerequisites.",
    )

    assert course.corequisites == "MATH1005"
    assert course.description == "Source description."
    assert course.learning_outcomes == ["Source learning outcome."]
    assert course.prerequisites is None
    assert program.program_requirements == "Source program requirements."
    assert program.admission_requirements == "Source admission requirements."
    assert ProgramMetadata(
        entity_type="program", program_code="BACCT", academic_year="2026"
    ).overview is None


def test_program_requirements_are_retrieved_from_structured_source_text():
    values = make_subplan().model_dump(mode="json")
    values.update(
        record_id="courses:program:BACCT_2026",
        entity_id="BACCT_2026",
        title="Bachelor of Accounting",
        content=(
            "Overview: Source overview.\n"
            "Program Requirements: Complete the published 144-unit structure.\n"
            "Minors: Source-present minor information.\n"
            "Elective Study: Source-present elective information.\n"
            "Study Options: Source-present study-option information."
        ),
        canonical_url="https://programsandcourses.anu.edu.au/2026/program/bacct",
    )
    values["metadata_json"] = ProgramMetadata(
        entity_type="program",
        program_code="BACCT",
        academic_year="2026",
        overview="Source overview.",
        program_requirements="Complete the published 144-unit structure.",
        admission_requirements="Source admission requirements.",
        prerequisites="Source prerequisites.",
    ).model_dump(mode="json")
    program = CourseProgramRecord.model_validate(values)
    service = HybridQueryService(CourseProgramRepository((program,)))

    response = asyncio.run(
        service.answer(
            "What are the program requirements for BACCT in 2026?",
            "req-program",
        )
    )
    assert response.status == "ok"
    assert "Complete the published 144-unit structure." in response.answer
    assert "Minors:" in program.content
    assert "Elective Study:" in program.content
    assert "Study Options:" in program.content


def test_exact_subplan_code_and_course_corequisite_are_deterministic():
    subplan = make_subplan()
    course_values = make_subplan().model_dump(mode="json")
    course_values.update(
        record_id="courses:course:COMP1110_2026",
        entity_id="COMP1110_2026",
        title="Structured Programming",
        canonical_url="https://programsandcourses.anu.edu.au/2026/course/comp1110",
    )
    course_values["metadata_json"] = CourseMetadata(
        entity_type="course",
        course_code="COMP1110",
        academic_year="2026",
        corequisites="MATH1005",
    ).model_dump(mode="json")
    course = CourseProgramRecord.model_validate(course_values)
    repository = CourseProgramRepository((subplan, course))
    service = HybridQueryService(repository)

    exact = plan_query("Tell me about ACCT-MAJ in 2026", repository)
    assert exact.route == "exact"
    assert service.retrieve(exact) == (subplan,)
    answer = asyncio.run(
        service.answer(
            "What are the corequisites for COMP1110 in 2026?", "req-coreq"
        )
    )
    assert answer.status == "ok"
    assert "MATH1005" in answer.answer


def test_subplans_share_semantic_and_hybrid_candidate_pipeline():
    major = make_subplan("major", "ACCT-MAJ", title="Accounting Major")
    minor = make_subplan("minor", "DATA-MIN", title="Data Analytics Minor")
    specialisation = make_subplan(
        "specialisation", "MEAS-SPEC", title="Measurement Specialisation"
    )
    repository = CourseProgramRepository((major, minor, specialisation))
    service = HybridQueryService(repository, min_score=0.05)

    plan = plan_query("Which major is about accounting?", repository)
    assert plan.route == "semantic" and plan.entity_type == "major"
    assert service.retrieve(plan) == (major,)
    broad = plan_query("Which ANU option involves accounting?", repository)
    assert broad.semantic_allowed
    assert major in service.retrieve(broad)
    response = asyncio.run(service.answer("Which major is about accounting?", "req-major"))
    assert response.status == "ok"
    assert "Major ACCT-MAJ (2026)" in response.answer


def test_subplan_content_and_hash_are_preserved_as_source_evidence():
    record = make_subplan()

    assert "Requirements:" in record.content
    assert "Relevant Degrees:" in record.content
    assert hashlib.sha256(record.content.encode("utf-8")).hexdigest() == record.content_hash
