"""Day 7 release-candidate torture across the frozen six-domain contract."""

from __future__ import annotations

from fastapi.testclient import TestClient

from askanu_rag.main import create_app
from askanu_rag.retrieval import CourseProgramRepository
from test_resources import accommodation
from test_v7_day5_courses_scholarships import (
    _course_records,
    _scholarship_records,
)
from test_v7_day6_journeys import NOW, TODAY, event, job, support_service


class RcConversation:
    def __init__(self, records) -> None:
        self.client = TestClient(
            create_app(
                CourseProgramRepository(records),
                jobs_today_provider=lambda: TODAY,
                events_now_provider=lambda: NOW,
            )
        )
        self.state: dict = {}
        self.history: list[dict[str, str]] = []

    def ask(self, question: str) -> dict:
        response = self.client.post(
            "/api/v1/ask",
            json={
                "question": question,
                "history": self.history,
                "conversation_state": self.state,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        self.state = body["conversation_state"]
        turn = len(self.history) + 1
        self.history.extend(
            (
                {"turn_id": f"rc-{turn}", "role": "user", "content": question},
                {
                    "turn_id": f"rc-{turn + 1}",
                    "role": "assistant",
                    "content": body["answer"],
                },
            )
        )
        self.history = self.history[-10:]
        return body


def test_six_domain_rc_journey_switches_returns_and_clears_without_leakage() -> None:
    """One assistant carries typed context across every supported V7 domain."""
    records = [
        *_course_records(),
        *_scholarship_records(),
        accommodation("rc-hall-one", title="RC Hall One"),
        accommodation("rc-hall-two", title="RC Hall Two"),
        *[
            job(
                str(730000 + index),
                title=f"RC Software Role {index}",
                requirements=[f"Published requirement {index}"],
            )
            for index in range(1, 8)
        ],
        *[
            event(
                f"rc-{index}",
                day=14,
                hour=17 + index,
                venue=f"RC Venue {index}",
                organiser=f"RC Organiser {index}",
            )
            for index in range(1, 6)
        ],
        support_service(),
    ]
    conversation = RcConversation(records)

    course = conversation.ask("Tell me about COMP1110 in 2026")
    assert course["items"][0]["domain"] == "courses"
    prerequisite = conversation.ask("What are its prerequisites?")
    assert "COMP1100 OR COMP1130 OR COMP1730" in prerequisite["answer"]

    scholarships = conversation.ask(
        "I'm an international Bachelor of Computing student. "
        "What scholarships might suit me?"
    )
    assert scholarships["conversation_state"]["focus"]["domain"] == "scholarships"
    second_scholarship = conversation.ask("Tell me about the second one")
    assert second_scholarship["items"][0]["ordinal"] == 2
    eligibility = conversation.ask("Am I eligible?")
    assert eligibility["answer_state"] == "PARTIAL"
    assert "cannot determine your personal eligibility" in eligibility["answer"]
    refined = conversation.ask("Only show me ones I can still apply for")
    assert refined["conversation_state"]["result_sets"][0]["parent_result_set_id"]
    comparison = conversation.ask("Compare the first two")
    assert comparison["items"][0]["type"] == "comparison"
    continued = conversation.ask("Any more?")
    assert continued["items"][0]["ordinal"] == 6

    residences = conversation.ask("Show me accommodation options")
    assert residences["conversation_state"]["focus"]["domain"] == "accommodation"
    vacancy = conversation.ask("Does the first one have rooms available now?")
    assert vacancy["answer_state"] == "UNKNOWN"
    assert "rooms are available" not in vacancy["answer"].casefold()

    jobs = conversation.ask("What jobs are available at ANU?")
    assert jobs["conversation_state"]["focus"]["domain"] == "jobs"
    first_job = conversation.ask("Tell me about the first one")
    assert first_job["items"][0]["domain"] == "jobs"
    requirements = conversation.ask("What are its requirements?")
    assert "Published requirement 1" in requirements["answer"]
    more_jobs = conversation.ask("Any more?")
    assert [item["ordinal"] for item in more_jobs["items"]] == [6, 7]

    events = conversation.ask("What events are on at ANU today?")
    assert events["conversation_state"]["focus"]["domain"] == "events"
    evening = conversation.ask("Only after 5pm")
    assert all(item["domain"] == "events" for item in evening["items"])
    second_event = conversation.ask("Where is the second one?")
    assert second_event["items"][0]["ordinal"] == 2
    assert "RC Venue 2" in second_event["answer"]

    support = conversation.ask(
        "I think I was graded unfairly on an assignment, who should I talk to?"
    )
    assert support["conversation_state"]["focus"]["domain"] == "support"
    assert "marker was wrong" not in support["answer"].casefold()
    contact = conversation.ask("How do I contact them?")
    assert "student.assistance@anusa.com.au" in contact["answer"]

    returned_course = conversation.ask("Back to COMP1110")
    assert returned_course["items"][0]["domain"] == "courses"
    returned_accommodation = conversation.ask("Return to accommodation options")
    assert returned_accommodation["conversation_state"]["focus"]["domain"] == (
        "accommodation"
    )

    cleared = conversation.ask("Clear Chat")
    assert cleared["conversation_state"]["recent_entities"] == []
    assert cleared["conversation_state"]["result_sets"] == []
    assert cleared["conversation_state"]["selected_result"] is None
    ambiguous = conversation.ask("Where is it?")
    assert ambiguous["status"] != "ok"
    assert ambiguous["sources"] == []
