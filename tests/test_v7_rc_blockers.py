"""Release-blocker regressions from the cross-repository V7 RC torture."""

from __future__ import annotations

from fastapi.testclient import TestClient

from askanu_rag.main import create_app
from askanu_rag.retrieval import CourseProgramRepository
from test_v7_day5_courses_scholarships import _course_records, _scholarship_records
from test_v7_day6_journeys import NOW, event


class Conversation:
    def __init__(self, records) -> None:
        self.client = TestClient(
            create_app(
                CourseProgramRepository(records),
                events_now_provider=lambda: NOW,
            )
        )
        self.state: dict = {}

    def ask(self, question: str, *, selected_result: dict | None = None) -> dict:
        payload = {
            "question": question,
            "history": [],
            "conversation_state": self.state,
        }
        if selected_result is not None:
            payload["selected_result"] = selected_result
        response = self.client.post("/api/v1/ask", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        self.state = body["conversation_state"]
        return body


def _selection(body: dict, index: int) -> dict:
    item = body["items"][index]
    return {
        "result_set_id": item["result_set_id"],
        "canonical_id": item["canonical_id"],
        "ordinal": item["ordinal"],
    }


def _scholarship_discovery(conversation: Conversation) -> dict:
    return conversation.ask(
        "I'm an international Bachelor of Computing student. "
        "What scholarships might suit me?"
    )


def _event_records(count: int = 7):
    return tuple(
        event(
            f"blocker-{index}",
            day=14,
            hour=9 + index,
            venue=f"Blocker Venue {index}",
            organiser=f"Blocker Organiser {index}",
        )
        for index in range(1, count + 1)
    )


def test_r1_r4_current_turn_selection_beats_generic_cross_domain_words() -> None:
    conversation = Conversation(_scholarship_records())
    discovered = _scholarship_discovery(conversation)
    selected = _selection(discovered, 1)

    body = conversation.ask(
        "What are the course requirements for it?",
        selected_result=selected,
    )

    assert body["items"][0]["canonical_id"] == selected["canonical_id"]
    assert body["conversation_state"]["selected_result"] == selected


def test_r1_r4_generic_followup_retains_valid_selected_result() -> None:
    conversation = Conversation(_scholarship_records())
    discovered = _scholarship_discovery(conversation)
    selected = _selection(discovered, 1)

    body = conversation.ask(
        "What are the eligibility requirements?",
        selected_result=selected,
    )

    assert body["items"][0]["canonical_id"] == selected["canonical_id"]
    assert body["answer_state"] == "PARTIAL"


def test_r2_explicit_scholarship_name_overrides_old_selection() -> None:
    records = _scholarship_records()
    conversation = Conversation(records)
    discovered = _scholarship_discovery(conversation)
    old = conversation.ask("Tell me about the second one")
    assert old["items"][0]["canonical_id"] == records[1].entity_id

    explicit = conversation.ask(f"Am I eligible for {records[2].title}?")

    assert explicit["items"][0]["canonical_id"] == records[2].entity_id
    assert explicit["sources"][0]["record_id"] == records[2].record_id
    assert explicit["answer_state"] == "PARTIAL"
    assert discovered["items"][1]["canonical_id"] != records[2].entity_id


def test_r2_explicit_scholarship_canonical_id_overrides_current_click() -> None:
    records = _scholarship_records()
    conversation = Conversation(records)
    discovered = _scholarship_discovery(conversation)
    selected = _selection(discovered, 1)

    explicit = conversation.ask(
        f"Am I eligible for {records[2].entity_id}?",
        selected_result=selected,
    )

    assert explicit["items"][0]["canonical_id"] == records[2].entity_id
    assert explicit["answer_state"] == "PARTIAL"


def test_r2_ambiguous_explicit_scholarships_do_not_fall_back_to_selection() -> None:
    records = _scholarship_records()
    conversation = Conversation(records)
    discovered = _scholarship_discovery(conversation)
    conversation.ask(
        "Tell me more about this scholarship",
        selected_result=_selection(discovered, 1),
    )

    body = conversation.ask(
        f"Am I eligible for {records[2].title} or {records[3].title}?"
    )

    assert body["status"] == "needs_clarification"
    assert body["sources"] == []


def test_explicit_course_entity_beats_current_scholarship_click() -> None:
    conversation = Conversation((*_course_records(), *_scholarship_records()))
    discovered = _scholarship_discovery(conversation)

    body = conversation.ask(
        "Tell me about COMP1110 in 2026",
        selected_result=_selection(discovered, 1),
    )

    assert body["items"][0]["domain"] == "courses"
    assert body["items"][0]["canonical_id"] == "COMP1110"


def test_r2_explicit_identity_wins_after_same_selection_comparison_and_page() -> None:
    records = _scholarship_records()
    conversation = Conversation(records)
    _scholarship_discovery(conversation)
    selected = conversation.ask("Tell me about the second one")

    same = conversation.ask(f"Am I eligible for {records[1].title}?")
    assert same["items"][0]["canonical_id"] == records[1].entity_id

    compared = conversation.ask("Compare the first two")
    assert compared["items"][0]["type"] == "comparison"
    after_comparison = conversation.ask(f"Am I eligible for {records[2].title}?")
    assert after_comparison["items"][0]["canonical_id"] == records[2].entity_id

    continued = conversation.ask("Any more?")
    assert continued["items"][0]["ordinal"] == 6
    after_page = conversation.ask(f"Am I eligible for {records[0].title}?")
    assert after_page["items"][0]["canonical_id"] == records[0].entity_id
    assert selected["items"][0]["canonical_id"] != records[0].entity_id


def test_r5_event_ordinals_replace_selection_without_reretrieval() -> None:
    records = _event_records()
    conversation = Conversation(records)
    discovered = conversation.ask("What events are on at ANU today?")
    result_set_id = discovered["result_page"]["result_set_id"]

    second = conversation.ask("Where is the second one?")
    assert second["items"][0]["canonical_id"] == records[1].entity_id
    assert second["items"][0]["ordinal"] == 2
    followup = conversation.ask("Who organises it?")
    assert followup["items"][0]["canonical_id"] == records[1].entity_id

    third = conversation.ask("Where is the third one?")
    assert third["items"][0]["canonical_id"] == records[2].entity_id
    assert third["items"][0]["ordinal"] == 3
    assert third["items"][0]["result_set_id"] == result_set_id
    third_followup = conversation.ask("Who organises it?")
    assert third_followup["items"][0]["canonical_id"] == records[2].entity_id

    first = conversation.ask("Where is the first one?")
    assert first["items"][0]["canonical_id"] == records[0].entity_id
    assert first["items"][0]["ordinal"] == 1


def test_r5_event_ordinal_after_continuation_keeps_original_order() -> None:
    records = _event_records()
    conversation = Conversation(records)
    discovered = conversation.ask("What events are on at ANU today?")
    result_set_id = discovered["result_page"]["result_set_id"]
    continued = conversation.ask("Any more?")
    assert [item["ordinal"] for item in continued["items"]] == [6, 7]

    third = conversation.ask("Where is the third one?")

    assert third["items"][0]["canonical_id"] == records[2].entity_id
    assert third["items"][0]["ordinal"] == 3
    assert third["items"][0]["result_set_id"] == result_set_id


def test_r5_explicit_event_identity_beats_old_ordinal_selection() -> None:
    records = _event_records()
    conversation = Conversation(records)
    conversation.ask("What events are on at ANU today?")
    second = conversation.ask("Where is the second one?")
    assert second["items"][0]["canonical_id"] == records[1].entity_id

    explicit = conversation.ask(f"Where is {records[2].title}?")

    assert explicit["items"][0]["canonical_id"] == records[2].entity_id
    assert explicit["items"][0]["ordinal"] == 3


def test_r5_invalid_or_tampered_event_ordinal_is_controlled() -> None:
    conversation = Conversation(_event_records(3))
    discovered = conversation.ask("What events are on at ANU today?")
    invalid = _selection(discovered, 1) | {"ordinal": 3}
    response = conversation.client.post(
        "/api/v1/ask",
        json={
            "question": "Where is it?",
            "history": [],
            "conversation_state": conversation.state,
            "selected_result": invalid,
        },
    )

    assert response.status_code == 400
    assert response.json()["sources"] == []
