"""Remaining R4/R5 release-blocker regressions."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from askanu_rag.main import create_app
from askanu_rag.retrieval import CourseProgramRepository
from test_v7_day4_accommodation_vertical import ALPHA, BRAVO
from test_v7_day5_courses_scholarships import _scholarship_records
from test_v7_day6_journeys import NOW, TODAY, event, job


class Conversation:
    def __init__(self, records) -> None:
        self.client = TestClient(
            create_app(
                CourseProgramRepository(records),
                events_now_provider=lambda: NOW,
                jobs_today_provider=lambda: TODAY,
            )
        )
        self.state: dict = {}

    def ask(self, question: str, **request_fields) -> dict:
        response = self.client.post(
            "/api/v1/ask",
            json={
                "question": question,
                "history": [],
                "conversation_state": self.state,
                **request_fields,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        self.state = body["conversation_state"]
        return body


def selection(body: dict, index: int) -> dict:
    item = body["items"][index]
    return {
        "result_set_id": item["result_set_id"],
        "canonical_id": item["canonical_id"],
        "ordinal": item["ordinal"],
    }


@pytest.mark.parametrize(
    "wording",
    (
        "Tell me about {title}",
        "Tell me more about {title}",
        "Give me more information about {title}",
    ),
)
def test_r4_accommodation_title_overview_variants_keep_valid_selection(
    wording: str,
) -> None:
    chat = Conversation((ALPHA, BRAVO))
    discovered = chat.ask("Show me accommodation options")

    body = chat.ask(
        wording.format(title=ALPHA.title),
        selected_result=selection(discovered, 0),
    )

    assert body["status"] == "ok"
    assert body["items"][0]["canonical_id"] == ALPHA.entity_id
    assert body["sources"][0]["record_id"] == ALPHA.record_id


def digit_title_jobs():
    return tuple(
        job(str(700000 + index), title=f"Verified Role {index}")
        for index in range(1, 8)
    )


def selected_title_jobs():
    return tuple(
        job(
            str(700000 + index),
            title=(
                "Software Engineer"
                if index == 1
                else f"Verified Role {index}"
            ),
        )
        for index in range(1, 8)
    )


def assert_exact_job_without_title_constraint(body: dict, record) -> None:
    assert body["status"] == "ok"
    assert body["answer_state"] == "CONFIRMED"
    assert len(body["items"]) == 1
    assert body["items"][0]["canonical_id"] == record.entity_id
    assert body["items"][0]["record_id"] == record.record_id
    assert body["sources"][0]["record_id"] == record.record_id
    assert body["conversation_state"]["selected_result"] is None
    assert all(
        not (
            item["semantic_type"] == "employment_type"
            and str(item["value"]).casefold() == "verified"
        )
        for item in body["conversation_state"]["constraints"]["items"]
    )


def test_r4_exact_job_title_fresh_returns_structured_item_without_constraint_leak() -> None:
    records = digit_title_jobs()
    chat = Conversation(records)

    body = chat.ask(f"Tell me about {records[4].title}")

    assert_exact_job_without_title_constraint(body, records[4])

    discovery = chat.ask("Show me jobs")
    assert [item["canonical_id"] for item in discovery["items"]] == [
        record.entity_id for record in records[:5]
    ]
    assert discovery["conversation_state"]["constraints"]["items"] == []


@pytest.mark.parametrize(
    ("title_index", "wording"),
    (
        (0, "Tell me more about {title}"),
        (0, "Tell me about {title}"),
        (1, "Tell me more about {title}"),
        (1, "Tell me about {title}"),
        (2, "Tell me more about {title}"),
        (2, "Tell me about {title}"),
    ),
)
def test_r4_same_exact_job_title_preserves_selected_result_state(
    title_index: int,
    wording: str,
) -> None:
    records = selected_title_jobs()
    chat = Conversation(records)
    discovered = chat.ask("What jobs are available at ANU?")
    original_selection = selection(discovered, title_index)
    selected = chat.ask(
        "Tell me about it",
        selected_result=original_selection,
    )
    selected_state = selected["conversation_state"]

    body = chat.ask(wording.format(title=records[title_index].title))

    assert body["status"] == "ok"
    assert body["answer_state"] == "CONFIRMED"
    assert len(body["items"]) == 1
    assert body["items"][0]["canonical_id"] == records[title_index].entity_id
    assert body["items"][0]["result_set_id"] == original_selection["result_set_id"]
    assert body["items"][0]["ordinal"] == original_selection["ordinal"]
    state = body["conversation_state"]
    assert state["selected_result"] == original_selection
    assert state["selected_result"]["canonical_id"] == records[title_index].entity_id
    assert state["selected_result"]["result_set_id"] == original_selection["result_set_id"]
    assert state["selected_result"]["ordinal"] == original_selection["ordinal"]
    assert state["focus"]["result_set_id"] == original_selection["result_set_id"]
    assert state["focus"] == selected_state["focus"]
    assert state["constraints"]["items"] == []


def test_r4_show_more_after_same_exact_job_title_uses_original_resultset() -> None:
    records = selected_title_jobs()
    chat = Conversation(records)
    discovered = chat.ask("What jobs are available at ANU?")
    result_set_id = discovered["result_page"]["result_set_id"]
    chat.ask(
        "Tell me about it",
        selected_result=selection(discovered, 1),
    )
    same = chat.ask(f"Tell me about {records[1].title}")
    assert same["conversation_state"]["selected_result"] is not None

    more = chat.ask(
        "Show More",
        result_page={
            "result_set_id": result_set_id,
            "start_ordinal": 6,
            "limit": 5,
        },
    )

    assert [item["ordinal"] for item in more["items"]] == [6, 7]


def test_r4_exact_job_title_after_resultset_returns_structured_item() -> None:
    records = digit_title_jobs()
    chat = Conversation(records)
    chat.ask("What jobs are available at ANU?")

    body = chat.ask(f"Tell me about {records[4].title}")

    assert_exact_job_without_title_constraint(body, records[4])


def test_r4_exact_job_title_after_selection_overrides_selected_job() -> None:
    records = digit_title_jobs()
    chat = Conversation(records)
    discovered = chat.ask("What jobs are available at ANU?")
    selected = chat.ask(
        "Tell me about it",
        selected_result=selection(discovered, 1),
    )
    assert selected["items"][0]["canonical_id"] == records[1].entity_id

    body = chat.ask(f"Tell me about {records[4].title}")

    assert_exact_job_without_title_constraint(body, records[4])
    assert body["items"][0]["canonical_id"] != records[1].entity_id


def test_r4_exact_job_title_after_continuation_returns_structured_item() -> None:
    records = digit_title_jobs()
    chat = Conversation(records)
    discovered = chat.ask("What jobs are available at ANU?")
    result_set_id = discovered["result_page"]["result_set_id"]
    continued = chat.ask(
        "Show More",
        result_page={
            "result_set_id": result_set_id,
            "start_ordinal": 6,
            "limit": 5,
        },
    )
    assert [item["ordinal"] for item in continued["items"]] == [6, 7]

    body = chat.ask(f"Tell me more about {records[4].title}")

    assert_exact_job_without_title_constraint(body, records[4])


@pytest.mark.parametrize("title_index", (2, 3))
@pytest.mark.parametrize(
    "wording", ("Tell me about {title}", "Tell me more about {title}")
)
def test_r4_exact_job_title_with_digit_beats_numeric_id(
    title_index: int, wording: str
) -> None:
    records = digit_title_jobs()
    chat = Conversation(records)
    discovered = chat.ask("What jobs are available at ANU?")

    body = chat.ask(
        wording.format(title=records[title_index - 1].title),
        selected_result=selection(discovered, title_index - 1),
    )

    assert body["status"] == "ok"
    assert body["items"][0]["canonical_id"] == records[title_index - 1].entity_id
    assert all(
        str(item["value"]).casefold() != "verified"
        for item in body["conversation_state"]["constraints"]["items"]
    )


def test_r4_real_numeric_job_reference_still_resolves() -> None:
    records = digit_title_jobs()
    chat = Conversation(records)

    body = chat.ask(f"Tell me about job {records[2].entity_id}")

    assert_exact_job_without_title_constraint(body, records[2])


def test_r4_different_exact_job_title_overrides_retained_selection() -> None:
    records = digit_title_jobs()
    chat = Conversation(records)
    discovered = chat.ask("What jobs are available at ANU?")

    body = chat.ask(
        f"Tell me about {records[2].title}",
        selected_result=selection(discovered, 1),
    )

    assert_exact_job_without_title_constraint(body, records[2])


ORDINALS = (
    ("first", 1),
    ("second", 2),
    ("third", 3),
    ("fourth", 4),
    ("1st", 1),
    ("2nd", 2),
    ("3rd", 3),
    ("4th", 4),
    ("number 1", 1),
    ("number 2", 2),
    ("number 3", 3),
    ("number 4", 4),
)


@pytest.mark.parametrize("context", ("fresh", "selection", "continuation", "show_more"))
@pytest.mark.parametrize(("wording", "ordinal"), ORDINALS)
def test_r5_bounded_ordinal_forms_keep_original_resultset_order(
    context: str, wording: str, ordinal: int
) -> None:
    records = tuple(
        event(f"ordinal-{index}", day=14, hour=9 + index)
        for index in range(1, 8)
    )
    chat = Conversation(records)
    discovered = chat.ask("What events are on at ANU today?")
    result_set_id = discovered["result_page"]["result_set_id"]
    if context == "selection":
        chat.ask("Where is the second one?")
    elif context == "continuation":
        chat.ask("Any more?")
    elif context == "show_more":
        chat.ask(
            "Show More",
            result_page={
                "result_set_id": result_set_id,
                "start_ordinal": 6,
                "limit": 5,
            },
        )

    body = chat.ask(f"Where is {wording}?")

    assert body["status"] == "ok"
    assert body["items"][0]["canonical_id"] == records[ordinal - 1].entity_id
    assert body["items"][0]["ordinal"] == ordinal
    assert body["items"][0]["result_set_id"] == result_set_id


def test_r5_explicit_numbered_scholarship_title_is_not_an_ordinal() -> None:
    records = _scholarship_records()
    chat = Conversation(records)
    chat.ask(
        "I'm an international Bachelor of Computing student. "
        "What scholarships might suit me?"
    )

    body = chat.ask(f"Am I eligible for {records[7].title}?")

    assert body["items"][0]["canonical_id"] == records[7].entity_id

