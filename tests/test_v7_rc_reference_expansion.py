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


def test_r4_real_numeric_job_reference_still_resolves() -> None:
    records = digit_title_jobs()
    chat = Conversation(records)

    body = chat.ask(f"Tell me about job {records[2].entity_id}")

    assert body["status"] == "ok"
    assert body["items"][0]["canonical_id"] == records[2].entity_id


def test_r4_different_exact_job_title_overrides_retained_selection() -> None:
    records = digit_title_jobs()
    chat = Conversation(records)
    discovered = chat.ask("What jobs are available at ANU?")

    body = chat.ask(
        f"Tell me about {records[2].title}",
        selected_result=selection(discovered, 1),
    )

    assert body["items"][0]["canonical_id"] == records[2].entity_id


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

