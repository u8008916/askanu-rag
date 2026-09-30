"""V7 Day 5 Course and Scholarship student-journey acceptance coverage."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from askanu_rag.main import create_app
from askanu_rag.models import CourseProgramRecord, ScholarshipRecord
from askanu_rag.retrieval import (
    CourseProgramRepository,
    load_common_records,
    load_course_program_records,
)
from test_resources import accommodation


ROOT = Path(__file__).parents[1]
COURSE_FIXTURE = ROOT / "fixtures/day5_course_program_records.json"
SCHOLARSHIP_FIXTURE = ROOT / "fixtures/day9_scholarship_records.json"


class Conversation:
    def __init__(self, records, *, vector=None):
        self.repository = (
            records
            if isinstance(records, CourseProgramRepository)
            else CourseProgramRepository(records)
        )
        self.client = TestClient(
            create_app(
                self.repository,
                semantic_retriever=vector,
            )
        )
        self.state = {}
        self.history: list[dict[str, str]] = []

    def ask(self, question: str, **request_fields):
        payload = {
            "question": question,
            "history": self.history,
            "conversation_state": self.state,
        }
        payload.update(request_fields)
        response = self.client.post("/api/v1/ask", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        self.state = body["conversation_state"]
        index = len(self.history) + 1
        self.history.extend(
            (
                {"turn_id": f"t{index}", "role": "user", "content": question},
                {
                    "turn_id": f"t{index + 1}",
                    "role": "assistant",
                    "content": body["answer"],
                },
            )
        )
        self.history = self.history[-10:]
        return body


def _course_variant(
    base: CourseProgramRecord,
    *,
    code: str,
    title: str,
    year: str = "2026",
    units: str | None = "6",
    prerequisites: str | None = None,
    description: str | None = None,
) -> CourseProgramRecord:
    values = base.model_dump(mode="python")
    values.update(
        record_id=f"courses:course:{code}_{year}",
        entity_id=f"{code}_{year}",
        title=title,
        content=(
            f"Description: {description}\nOverview: Approved overview for {title}."
            if description is not None
            else f"Overview: Approved overview for {title}."
        ),
        canonical_url=(
            f"https://programsandcourses.anu.edu.au/{year}/course/{code.lower()}"
        ),
    )
    values["metadata_json"].update(
        course_code=code,
        academic_year=year,
        units=units,
        prerequisites=prerequisites,
        description=description,
    )
    return CourseProgramRecord.model_validate(values)


def _course_records() -> tuple[CourseProgramRecord, ...]:
    source = load_course_program_records(COURSE_FIXTURE)
    base = next(
        record
        for record in source
        if record.record_id == "courses:course:COMP1110_2026"
    )
    comp1110 = _course_variant(
        base,
        code="COMP1110",
        title="Structured Programming",
        units="6",
        prerequisites="COMP1100 OR COMP1130 OR COMP1730",
        description="Structured programming with object-oriented design.",
    )
    comp2120 = _course_variant(
        base,
        code="COMP2120",
        title="Software Engineering",
        units="6",
        prerequisites=(
            "Students must have successfully completed or be currently studying "
            "COMP2100"
        ),
        description=None,
    )
    comp1110_old = _course_variant(
        base,
        code="COMP1110",
        title="Structured Programming",
        year="2025",
        units="6",
        prerequisites="COMP1000",
    )
    return (comp1110, comp2120, comp1110_old)


def _scholarship_variant(
    base: ScholarshipRecord,
    *,
    number: int,
    status: str | None = "open",
    student_type: list[str] | None = None,
    study_level: list[str] | None = None,
    area_of_study: list[str] | None = None,
    closing_date: str | None = "2026-10-31",
    eligibility: str | None = "International Bachelor of Computing students may apply.",
) -> ScholarshipRecord:
    slug = f"day5-international-computing-{number}"
    values = base.model_dump(mode="python")
    values.update(
        record_id=f"scholarships:scholarship:{slug}",
        entity_id=slug,
        title=f"Day 5 International Computing Scholarship {number}",
        content=(
            "Approved scholarship information for international Bachelor of "
            "Computing students."
        ),
        canonical_url=(
            "https://study.anu.edu.au/scholarships/find-scholarship/" + slug
        ),
    )
    values["metadata_json"].update(
        status=status,
        student_type=(
            ["International"] if student_type is None else student_type
        ),
        study_level=(["Bachelor"] if study_level is None else study_level),
        area_of_study=(
            ["Computing"] if area_of_study is None else area_of_study
        ),
        closing_date=closing_date,
        eligibility=eligibility,
    )
    return ScholarshipRecord.model_validate(values)


def _scholarship_records() -> tuple[ScholarshipRecord, ...]:
    base = ScholarshipRecord.model_validate(
        load_common_records(SCHOLARSHIP_FIXTURE)[0].model_dump(mode="python")
    )
    records = [
        _scholarship_variant(base, number=number)
        for number in range(1, 7)
    ]
    records.append(_scholarship_variant(base, number=7, status="closed"))
    records.append(
        _scholarship_variant(
            base,
            number=8,
            status=None,
            closing_date=None,
            eligibility=None,
        )
    )
    records.append(
        _scholarship_variant(
            base,
            number=9,
            student_type=[],
            study_level=[],
            area_of_study=[],
            closing_date=None,
            eligibility=None,
        )
    )
    return tuple(records)


class AdversarialVector:
    def __init__(self):
        self.calls = []

    def search(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return ()


def _latest_result(body):
    return body["conversation_state"]["result_sets"][0]


def test_course_canonical_journey_switch_compare_return_and_clear() -> None:
    conversation = Conversation(_course_records())

    exact = conversation.ask("Tell me about COMP1110 in 2026")
    assert exact["status"] == "ok"
    assert exact["answer_state"] == "CONFIRMED"
    assert exact["items"][0]["canonical_id"] == "COMP1110"
    assert exact["items"][0]["fields"]["units"] == "6"

    natural = conversation.ask("Tell me about Structured Programming in 2026")
    assert natural["sources"][0]["record_id"].endswith("COMP1110_2026")

    prerequisite = conversation.ask("What are the prerequisites?")
    assert "COMP1100 OR COMP1130 OR COMP1730" in prerequisite["answer"]

    units = conversation.ask("How many units is it?")
    assert "6" in units["answer"]

    switched = conversation.ask("What about COMP2120?")
    assert switched["items"][0]["canonical_id"] == "COMP2120"
    switched_prerequisite = conversation.ask("What are its prerequisites?")
    assert (
        "successfully completed or be currently studying COMP2100"
        in switched_prerequisite["answer"]
    )
    assert "COMP1100 OR" not in switched_prerequisite["answer"]

    compared = conversation.ask("Compare COMP1110 and COMP2120 in 2026")
    assert compared["items"][0]["type"] == "comparison"
    assert {item["canonical_id"] for item in compared["items"][0]["records"]} == {
        "COMP1110",
        "COMP2120",
    }
    answer_lower = compared["answer"].casefold()
    assert not {"easier", "harder", "better"}.intersection(answer_lower.split())

    returned = conversation.ask("Back to COMP1110")
    assert returned["items"][0]["canonical_id"] == "COMP1110"
    again = conversation.ask("What were its prerequisites again?")
    assert "COMP1100 OR COMP1130 OR COMP1730" in again["answer"]

    cleared = conversation.ask("Clear Chat")
    assert cleared["conversation_state"]["recent_entities"] == []
    assert cleared["conversation_state"]["result_sets"] == []
    missing = conversation.ask("What are its prerequisites?")
    assert missing["status"] in {
        "needs_clarification",
        "insufficient_evidence",
        "off_topic",
    }
    assert missing["sources"] == []


def test_course_exact_and_year_paths_beat_semantic_and_do_not_mix_versions() -> None:
    vector = AdversarialVector()
    conversation = Conversation(_course_records(), vector=vector)

    body = conversation.ask("Prerequisites for COMP1110 in 2025")

    assert "COMP1000" in body["answer"]
    assert "COMP1100 OR" not in body["answer"]
    assert body["sources"][0]["record_id"].endswith("COMP1110_2025")
    assert vector.calls == []


def test_course_unsupported_staff_and_hard_type_guard_still_abstain() -> None:
    staff = Conversation(_course_records()).ask("Who teaches COMP1110 in 2026?")
    wrong_type = Conversation(_course_records()).ask(
        "Tell me about program COMP1110 in 2026"
    )

    assert staff["status"] == "insufficient_evidence"
    assert wrong_type["status"] == "insufficient_evidence"


def test_course_comparison_marks_missing_field_not_published() -> None:
    body = Conversation(_course_records()).ask(
        "Compare COMP1110 and COMP2120 in 2026"
    )

    comparison = body["items"][0]
    description = next(
        field for field in comparison["fields"] if field["name"] == "description"
    )
    assert [value["state"] for value in description["values"]] == [
        "published",
        "not_published",
    ]
    assert description["values"][0]["value"] == (
        "Structured programming with object-oriented design."
    )
    assert description["values"][1]["value"] is None
    corequisites = next(
        field for field in comparison["fields"] if field["name"] == "corequisites"
    )
    assert all(
        value["state"] == "not_published" for value in corequisites["values"]
    )
    assert body["answer_state"] == "PARTIAL"


def test_scholarship_canonical_resultset_selection_refinement_and_continuation() -> None:
    conversation = Conversation(_scholarship_records())

    discovered = conversation.ask(
        "I'm an international Bachelor of Computing student. "
        "What scholarships might suit me?"
    )
    original = _latest_result(discovered)
    assert original["domain"] == "scholarships"
    assert original["ordered_canonical_ids"] == [
        f"day5-international-computing-{number}" for number in range(1, 9)
    ]
    assert discovered["answer_state"] == "PARTIAL"
    assert [item["ordinal"] for item in discovered["items"]] == [1, 2, 3, 4, 5]
    assert all(item["type"] == "result" for item in discovered["items"])

    second = conversation.ask("Tell me about the second one")
    assert second["items"][0]["canonical_id"] == original["ordered_canonical_ids"][1]
    assert second["conversation_state"]["selected_result"]["ordinal"] == 2

    closing = conversation.ask("When does it close?")
    assert "2026-10-31" in closing["answer"]

    eligibility = conversation.ask("Am I eligible?")
    assert eligibility["answer_state"] == "PARTIAL"
    assert "cannot determine your personal eligibility" in eligibility["answer"]
    assert "you are eligible" not in eligibility["answer"].casefold()

    refined = conversation.ask("Only show me ones I can still apply for")
    child = _latest_result(refined)
    assert child["parent_result_set_id"] == original["result_set_id"]
    assert child["ordered_canonical_ids"] == [
        f"day5-international-computing-{number}" for number in range(1, 7)
    ]
    assert refined["answer_state"] == "PARTIAL"
    assert "incomplete" in refined["answer"].casefold()

    compared = conversation.ask("Compare the first two")
    assert compared["items"][0]["type"] == "comparison"
    assert [
        item["canonical_id"] for item in compared["items"][0]["records"]
    ] == child["ordered_canonical_ids"][:2]

    continued = conversation.ask("Any more?")
    assert continued["items"][0]["canonical_id"] == child[
        "ordered_canonical_ids"
    ][5]
    assert continued["items"][0]["ordinal"] == 6


def test_scholarship_missing_criteria_is_unknown_not_ineligible() -> None:
    conversation = Conversation(_scholarship_records())
    body = conversation.ask(
        "Am I eligible for Day 5 International Computing Scholarship 8?"
    )

    assert body["answer_state"] == "UNKNOWN"
    assert "cannot determine your personal eligibility" in body["answer"]
    assert "ineligible" not in body["answer"].casefold()


def test_scholarship_clear_chat_removes_result_and_entity_context() -> None:
    conversation = Conversation(_scholarship_records())
    conversation.ask(
        "I'm an international Bachelor of Computing student. "
        "What scholarships might suit me?"
    )
    conversation.ask("Tell me about the second one")

    cleared = conversation.ask("Clear Chat")
    assert cleared["conversation_state"]["recent_entities"] == []
    assert cleared["conversation_state"]["result_sets"] == []
    assert cleared["conversation_state"]["selected_result"] is None
    missing = conversation.ask("When does it close?")
    assert missing["status"] in {
        "needs_clarification",
        "insufficient_evidence",
        "off_topic",
    }
    assert missing["sources"] == []


def test_scholarship_selected_followup_reresolves_current_repository_record() -> None:
    repository = CourseProgramRepository(_scholarship_records())
    conversation = Conversation(repository)
    discovered = conversation.ask(
        "I'm an international Bachelor of Computing student. "
        "What scholarships might suit me?"
    )
    selected = conversation.ask("Tell me about the second one")
    entity_id = selected["items"][0]["canonical_id"]
    current = repository._scholarships[entity_id]
    repository._scholarships[entity_id] = current.model_copy(
        update={
            "metadata_json": current.metadata_json.model_copy(
                update={"closing_date": "2026-12-15"}
            )
        }
    )

    closing = conversation.ask("When does it close?")

    assert discovered["items"][1]["fields"]["closing_date"] == "2026-10-31"
    assert "2026-12-15" in closing["answer"]
    assert "2026-10-31" not in closing["answer"]


def test_day5_topic_switches_preserve_typed_accommodation_isolation() -> None:
    records = (
        *_course_records(),
        *_scholarship_records(),
        accommodation("day5-hall", title="Day 5 Hall"),
    )
    conversation = Conversation(records)

    course = conversation.ask("Tell me about COMP1110 in 2026")
    residence_after_course = conversation.ask("Show me accommodation options")
    scholarship = conversation.ask(
        "I'm an international Bachelor of Computing student. "
        "What scholarships might suit me?"
    )
    residence_after_scholarship = conversation.ask(
        "Return to accommodation options"
    )

    assert course["items"][0]["domain"] == "courses"
    assert _latest_result(residence_after_course)["domain"] == "accommodation"
    assert _latest_result(scholarship)["domain"] == "scholarships"
    assert _latest_result(residence_after_scholarship)["domain"] == "accommodation"
    assert all(
        result_set["domain"] != "courses"
        or result_set["entity_kind"] == "course"
        for result_set in residence_after_scholarship["conversation_state"][
            "result_sets"
        ]
    )
