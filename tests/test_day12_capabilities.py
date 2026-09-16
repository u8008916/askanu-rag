"""Measured Day 12 Accommodation and Support capability matrices."""

from __future__ import annotations

import copy
import hashlib

import pytest
from fastapi.testclient import TestClient

from askanu_rag.main import create_app
from askanu_rag.models import AccommodationRecord, SupportRecord
from askanu_rag.retrieval import CourseProgramRepository
from test_day12_contracts import accommodation_payload, support_payload


def _rehash(payload: dict[str, object], content: str) -> None:
    payload["content"] = content
    payload["content_hash"] = hashlib.sha256(content.encode()).hexdigest()


def _accommodation(
    entity_id: str,
    title: str,
    *,
    missing: tuple[str, ...] = (),
    vacancy_status: str | None = None,
) -> AccommodationRecord:
    payload = copy.deepcopy(accommodation_payload())
    payload.update(
        entity_id=entity_id,
        record_id=f"accommodation:residence:{entity_id}",
        title=title,
        canonical_url=(
            "https://study.anu.edu.au/accommodation/our-residences/"
            f"{entity_id}"
        ),
    )
    metadata = payload["metadata_json"]
    for field in missing:
        metadata[field] = None
    metadata["vacancy_status"] = vacancy_status
    _rehash(
        payload,
        f"{title}. Self-catered residence with a Single studio, study rooms, "
        "published rates, accessibility and application information.",
    )
    return AccommodationRecord.model_validate(payload)


def _support(
    entity_id: str,
    title: str,
    *,
    hours: str | None,
    access: str | None,
) -> SupportRecord:
    payload = copy.deepcopy(support_payload())
    payload.update(
        entity_id=entity_id,
        record_id=f"support:support_service:{entity_id}",
        title=title,
        canonical_url=f"https://anusa.com.au/student-assistance/{entity_id}/",
    )
    metadata = payload["metadata_json"]
    metadata["category"] = "Academic" if entity_id == "academic" else "Financial"
    metadata["purpose"] = (
        "ANUSA can help with grade appeals and academic difficulty."
        if entity_id == "academic"
        else "ANUSA can help with financial difficulty."
    )
    metadata["hours"] = hours
    metadata["access"] = access
    metadata["topics"][0]["url"] = (
        f"https://anusa.com.au/student-assistance/{entity_id}/grade-appeal/"
    )
    _rehash(
        payload,
        f"{title}. {metadata['purpose']} Grade Appeal. "
        "Published contact, cost, topic and referral evidence.",
    )
    return SupportRecord.model_validate(payload)


YUK = _accommodation("yukeembruk", "Yukeembruk")
URSULA = _accommodation("ursula-hall", "Ursula Hall")
BRUCE_MISSING = _accommodation(
    "bruce-hall",
    "Bruce Hall",
    missing=("eligibility", "location", "accessibility"),
)
WRIGHT_VACANCY = _accommodation(
    "wright-hall",
    "Wright Hall",
    vacancy_status="Applications closed; no vacancies published",
)
BRUCE_MAIN = _accommodation("bruce-hall-main-wing", "Bruce Hall Main Wing")
BRUCE_PACKARD = _accommodation(
    "bruce-hall-packard-wing", "Bruce Hall Packard Wing"
)
ACADEMIC = _support(
    "academic",
    "Academic Support",
    hours="Monday to Friday, 10 am to 4 pm",
    access="Book an appointment or attend the published drop-in.",
)
FINANCIAL_MISSING = _support(
    "financial",
    "Financial Support",
    hours=None,
    access=None,
)


def _ask(records, question: str, *, pending=None, history=None):
    with TestClient(create_app(CourseProgramRepository(records))) as client:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": question,
                "history": history or [],
                "conversation_state": {"pending_clarification": pending},
            },
        )
    assert response.status_code == 200
    return response.json()


ACCOMMODATION_CASES = (
    ("exact residence", (YUK, URSULA), "Tell me about Yukeembruk accommodation", "ok", ("Yukeembruk",)),
    ("compare two", (YUK, URSULA), "Compare Yukeembruk versus Ursula Hall", "ok", ("Yukeembruk", "Ursula Hall")),
    ("category", (YUK,), "What category is Yukeembruk accommodation?", "ok", ("Self-catered residence",)),
    ("location", (YUK,), "Where is Yukeembruk located?", "ok", ("Acton campus",)),
    ("catering", (YUK,), "What catering does Yukeembruk offer?", "ok", ("Self-catered",)),
    ("audiences", (YUK,), "Who can live at Yukeembruk?", "ok", ("Undergraduate students",)),
    ("advertised rate", (YUK,), "How much does Yukeembruk cost?", "ok", ("advertised rate wording", "From $340 per week")),
    ("cost period", (YUK,), "What is the cost period for Yukeembruk?", "ok", ("2026 academic year",)),
    ("room rate", (YUK,), "What is the Single studio room rate at Yukeembruk?", "ok", ("Room Single studio", "$340 per week")),
    ("room contract", (YUK,), "What is the Single studio contract at Yukeembruk?", "ok", ("44 weeks",)),
    ("room inclusions", (YUK,), "What does the Single studio include at Yukeembruk?", "ok", ("Utilities and internet",)),
    ("room other fees", (YUK,), "What other fees apply to the Single studio at Yukeembruk?", "ok", ("Refundable deposit applies",)),
    ("features", (YUK,), "What facilities does Yukeembruk have?", "ok", ("Study rooms", "Shared kitchen")),
    ("overview", (YUK,), "Give me an overview of Yukeembruk", "ok", ("self-catered ANU residence",)),
    ("accessibility", (YUK,), "Is Yukeembruk accessible?", "ok", ("Accessible rooms",)),
    ("application text", (YUK,), "How do I apply for Yukeembruk accommodation?", "ok", ("Apply through the published portal",)),
    ("application URL", (YUK,), "What is the application link for Yukeembruk?", "ok", ("https://anu.starrezhousing.com/StarRezPortalX",)),
    ("contact email", (YUK,), "What is the contact email for Yukeembruk?", "ok", ("accommodation@anu.edu.au",)),
    ("contact phone", (YUK,), "What is the contact phone for Yukeembruk?", "ok", ("02 6125 0000",)),
    ("contact location", (YUK,), "How do I contact Yukeembruk accommodation?", "ok", ("Accommodation Services reception",)),
    ("contact hours", (YUK,), "What are the contact hours for Yukeembruk?", "ok", ("Monday to Friday",)),
    ("explicit eligibility", (YUK,), "Who is eligible for Yukeembruk?", "ok", ("Open to enrolled ANU students",)),
    ("missing eligibility", (BRUCE_MISSING,), "Who is eligible for Bruce Hall?", "insufficient_evidence", ("does not publish",)),
    ("explicit vacancy", (WRIGHT_VACANCY,), "Is Wright Hall available right now?", "ok", ("Applications closed", "not inferred")),
    ("missing vacancy", (YUK,), "Is Yukeembruk available right now?", "insufficient_evidence", ("null vacancy status means unknown",)),
    ("guaranteed price", (YUK,), "Is the Yukeembruk room price guaranteed?", "ok", ("not a guaranteed final price",)),
    ("missing location", (BRUCE_MISSING,), "Where is Bruce Hall located?", "insufficient_evidence", ("does not publish",)),
    ("missing accessibility", (BRUCE_MISSING,), "Is Bruce Hall accessible?", "insufficient_evidence", ("does not publish",)),
    ("unknown residence", (YUK, URSULA), "Tell me about Imaginary Hall accommodation", "insufficient_evidence", ("could not find",)),
    ("ambiguous residence", (BRUCE_MAIN, BRUCE_PACKARD), "Tell me about Bruce Hall accommodation", "needs_clarification", ("Which residence",)),
    ("broad clarification", (YUK, URSULA), "Tell me about accommodation", "needs_clarification", ("Which residence",)),
    ("unsupported fact", (YUK,), "What is the pet policy for Yukeembruk accommodation?", "insufficient_evidence", ("does not publish",)),
    ("source link preservation", (YUK,), "Tell me about Yukeembruk accommodation", "ok", ("Yukeembruk",)),
)


@pytest.mark.parametrize(
    "_name,records,question,status,expected",
    ACCOMMODATION_CASES,
    ids=[case[0] for case in ACCOMMODATION_CASES],
)
def test_accommodation_capability_matrix(_name, records, question, status, expected):
    body = _ask(records, question)

    assert body["status"] == status
    for text in expected:
        assert text.casefold() in body["answer"].casefold()
    if status == "ok" or records and body["sources"]:
        if body["sources"]:
            assert all(source["domain"] == "accommodation" for source in body["sources"])
            assert all(source["url"].startswith("https://study.anu.edu.au/") for source in body["sources"])


SUPPORT_CASES = (
    ("exact service", (ACADEMIC,), "Tell me about Academic Support", "ok", ("Academic Support",)),
    ("category", (ACADEMIC,), "What category is Academic Support?", "ok", ("Academic",)),
    ("purpose", (ACADEMIC,), "What is the purpose of Academic Support?", "ok", ("grade appeals",)),
    ("audiences", (ACADEMIC,), "Who can use Academic Support?", "ok", ("all ANU Students",)),
    ("who can help", (ACADEMIC, FINANCIAL_MISSING), "Who can help me with grade appeal?", "ok", ("Academic Support", "Grade Appeal")),
    ("contact email", (ACADEMIC,), "What is the contact email for Academic Support?", "ok", ("sa.assistance@anu.edu.au",)),
    ("contact phone", (ACADEMIC,), "What is the contact phone for Academic Support?", "ok", ("02 6125 2444",)),
    ("contact location", (ACADEMIC,), "Where is Academic Support located?", "ok", ("Di Riddell Student Centre",)),
    ("hours", (ACADEMIC,), "What hours is Academic Support open?", "ok", ("Monday to Friday",)),
    ("missing hours", (FINANCIAL_MISSING,), "What hours is Financial Support open?", "insufficient_evidence", ("remain unknown",)),
    ("access", (ACADEMIC,), "How can I access Academic Support?", "ok", ("Book an appointment",)),
    ("missing access", (FINANCIAL_MISSING,), "How can I access Financial Support?", "insufficient_evidence", ("remain unknown",)),
    ("cost", (ACADEMIC,), "What does Academic Support cost?", "ok", ("service is free",)),
    ("topics", (ACADEMIC,), "What topics does Academic Support cover?", "ok", ("Grade Appeal",)),
    ("topic description", (ACADEMIC,), "Tell me about Grade Appeal topic in Academic Support", "ok", ("Advice about appealing a grade",)),
    ("topic routing", (ACADEMIC, FINANCIAL_MISSING), "Who can help me with Grade Appeal?", "ok", ("Academic Support",)),
    ("referrals", (ACADEMIC,), "Show referrals for Academic Support", "ok", ("not a separate support service",)),
    ("external referral", (ACADEMIC,), "What external referral does Academic Support publish?", "ok", ("https://www.anu.edu.au/students/",)),
    ("diagnosis", (ACADEMIC,), "Can Academic Support diagnose me?", "insufficient_evidence", ("cannot diagnose",)),
    ("availability guarantee", (ACADEMIC,), "Is Academic Support available right now?", "insufficient_evidence", ("does not establish",)),
    ("emergency guarantee", (ACADEMIC,), "Does Academic Support guarantee emergency coverage?", "insufficient_evidence", ("does not establish",)),
    ("response-time guarantee", (ACADEMIC,), "Will Academic Support respond within one hour?", "insufficient_evidence", ("response-time guarantee",)),
    ("24/7 guarantee", (ACADEMIC,), "Is Academic Support available 24/7?", "insufficient_evidence", ("24/7",)),
    ("unknown service", (ACADEMIC,), "Tell me about Imaginary Support service", "insufficient_evidence", ("could not find",)),
    ("ambiguous support request", (ACADEMIC, FINANCIAL_MISSING), "What support is available?", "needs_clarification", ("Which support service",)),
    ("source provenance", (ACADEMIC,), "What is the purpose of Academic Support?", "ok", ("published purpose",)),
)


@pytest.mark.parametrize(
    "_name,records,question,status,expected",
    SUPPORT_CASES,
    ids=[case[0] for case in SUPPORT_CASES],
)
def test_support_capability_matrix(_name, records, question, status, expected):
    body = _ask(records, question)

    assert body["status"] == status
    for text in expected:
        assert text.casefold() in body["answer"].casefold()
    if body["sources"]:
        assert all(source["domain"] == "support" for source in body["sources"])
        assert all(source["url"].startswith("https://anusa.com.au/") for source in body["sources"])


def test_accommodation_capability_denominator_is_stable() -> None:
    assert len(ACCOMMODATION_CASES) == 33


def test_support_capability_denominator_is_stable() -> None:
    assert len(SUPPORT_CASES) == 26
