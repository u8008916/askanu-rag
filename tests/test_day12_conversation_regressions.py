"""Current-session regression coverage for Day 12 resource domains."""

from __future__ import annotations

import pytest

from test_day12_capabilities import ACADEMIC, FINANCIAL_MISSING, URSULA, YUK, _ask


def _turn(turn_id: str, role: str, content: str) -> dict[str, str]:
    return {"turn_id": turn_id, "role": role, "content": content}


def test_current_source_data_beats_prior_chat_statement() -> None:
    history = (
        _turn("t1", "user", "Tell me about Yukeembruk accommodation"),
        _turn("t2", "assistant", "The old rate was $1 per week."),
    )

    body = _ask((YUK,), "What is its cost?", history=history)

    assert body["status"] == "ok"
    assert "From $340 per week" in body["answer"]
    assert "$1 per week" not in body["answer"]


def test_resource_clarification_options_remain_domain_scoped() -> None:
    broad = _ask((YUK, URSULA, ACADEMIC), "Tell me about accommodation")

    assert broad["status"] == "needs_clarification"
    assert all(
        option["id"].startswith("accommodation:residence:")
        for option in broad["clarification"]["options"]
    )
    selected = _ask(
        (YUK, URSULA, ACADEMIC),
        "first",
        pending=broad["clarification"],
        history=(
            _turn("t1", "user", "Tell me about accommodation"),
            _turn("t2", "assistant", broad["answer"]),
        ),
    )
    assert selected["status"] == "ok"
    assert all(source["domain"] == "accommodation" for source in selected["sources"])
    assert "Published overview" in selected["answer"]


@pytest.mark.parametrize(
    ("records", "question", "status", "expected"),
    [
        (
            (YUK, URSULA),
            "What accommodation accessibility information is published?",
            "ok",
            "Published accessibility",
        ),
        (
            (YUK, URSULA),
            "What accommodation vacancy status is published?",
            "insufficient_evidence",
            "null vacancy status means unknown",
        ),
        (
            (YUK, URSULA),
            "What accommodation application information is published?",
            "ok",
            "Published application information",
        ),
        (
            (ACADEMIC, FINANCIAL_MISSING),
            "What support hours are published?",
            "ok",
            "Published hours",
        ),
        (
            (ACADEMIC, FINANCIAL_MISSING),
            "What support access information is published?",
            "ok",
            "Published access information",
        ),
        (
            (ACADEMIC, FINANCIAL_MISSING),
            "What support referrals are published?",
            "ok",
            "Published referral navigation",
        ),
        (
            (ACADEMIC, FINANCIAL_MISSING),
            "What support contact information is published?",
            "ok",
            "Published contact",
        ),
    ],
)
def test_resource_selection_preserves_original_requested_fact(
    records, question, status, expected
) -> None:
    broad = _ask(records, question)
    assert broad["status"] == "needs_clarification"
    selected_id = broad["clarification"]["options"][0]["id"]

    selected = _ask(
        records,
        "first",
        pending=broad["clarification"],
        history=(
            _turn("t1", "user", question),
            _turn("t2", "assistant", broad["answer"]),
        ),
    )

    assert selected["status"] == status
    assert selected["sources"][0]["record_id"] == selected_id
    assert expected.casefold() in selected["answer"].casefold()


def test_explicit_accommodation_to_support_topic_switch_wins() -> None:
    history = (
        _turn("t1", "user", "Tell me about Yukeembruk accommodation"),
        _turn("t2", "assistant", "Old accommodation answer"),
    )

    body = _ask(
        (YUK, ACADEMIC),
        "What is the purpose of Academic Support?",
        history=history,
    )

    assert body["status"] == "ok"
    assert body["sources"][0]["record_id"] == ACADEMIC.record_id


def test_explicit_support_to_accommodation_topic_switch_wins() -> None:
    history = (
        _turn("t1", "user", "Tell me about Academic Support"),
        _turn("t2", "assistant", "Old support answer"),
    )

    body = _ask(
        (YUK, ACADEMIC),
        "Tell me about Yukeembruk accommodation",
        history=history,
    )

    assert body["status"] == "ok"
    assert body["sources"][0]["record_id"] == YUK.record_id


def test_resource_entity_context_does_not_leak_across_domains() -> None:
    history = (
        _turn("t1", "user", "Tell me about Yukeembruk accommodation"),
        _turn("t2", "assistant", "Accommodation answer"),
    )

    body = _ask(
        (YUK, ACADEMIC),
        "What hours is Academic Support open?",
        history=history,
    )

    assert body["status"] == "ok"
    assert body["sources"][0]["record_id"] == ACADEMIC.record_id
    assert YUK.record_id not in {source["record_id"] for source in body["sources"]}


def test_clear_new_chat_removes_old_resource_entity_context() -> None:
    body = _ask((YUK, URSULA), "What is its cost?", history=(), pending=None)

    assert body["status"] in {
        "off_topic",
        "insufficient_evidence",
        "needs_clarification",
    }
    assert YUK.record_id not in {source["record_id"] for source in body["sources"]}


def test_clear_new_chat_removes_old_support_context() -> None:
    body = _ask((ACADEMIC,), "What are its hours?", history=(), pending=None)

    assert body["status"] in {"off_topic", "insufficient_evidence"}
    assert ACADEMIC.record_id not in {
        source["record_id"] for source in body["sources"]
    }


def test_insufficient_evidence_remains_fail_closed_after_history() -> None:
    history = (
        _turn("t1", "user", "Tell me about Yukeembruk accommodation"),
        _turn("t2", "assistant", "It is available now."),
    )

    body = _ask((YUK,), "Is it available right now?", history=history)

    assert body["status"] == "insufficient_evidence"
    assert "unknown" in body["answer"]
    assert "It is available now" not in body["answer"]


def test_source_provenance_survives_support_follow_up() -> None:
    history = (
        _turn("t1", "user", "Tell me about Academic Support"),
        _turn("t2", "assistant", "Stored answer"),
    )

    body = _ask((ACADEMIC,), "What are its hours?", history=history)

    assert body["status"] == "ok"
    assert body["sources"][0] == {
        "record_id": ACADEMIC.record_id,
        "source_id": "support_anusa_student_assistance",
        "title": ACADEMIC.title,
        "url": str(ACADEMIC.canonical_url),
        "domain": "support",
    }


def test_source_provenance_survives_accommodation_follow_up() -> None:
    history = (
        _turn("t1", "user", "Tell me about Yukeembruk accommodation"),
        _turn("t2", "assistant", "Stored answer"),
    )

    body = _ask((YUK,), "How do I contact it?", history=history)

    assert body["status"] == "ok"
    assert body["sources"][0]["record_id"] == YUK.record_id
    assert body["sources"][0]["url"] == str(YUK.canonical_url)
