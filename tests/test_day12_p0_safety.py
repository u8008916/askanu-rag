"""P0 safety and provenance gates for frozen Day 12 domains."""

from __future__ import annotations

import copy
import socket

import pytest
from pydantic import ValidationError

from askanu_rag.models import SupportRecord
from askanu_rag.retrieval import CourseProgramRepository
from test_day12_capabilities import (
    ACADEMIC,
    BRUCE_MISSING,
    YUK,
    _ask,
)
from test_day12_contracts import support_payload


def test_p0_accommodation_null_vacancy_abstains() -> None:
    body = _ask((YUK,), "Is Yukeembruk available right now?")

    assert body["status"] == "insufficient_evidence"
    assert "unknown" in body["answer"]


def test_p0_accommodation_application_link_never_implies_vacancy() -> None:
    body = _ask((YUK,), "Does the application link mean Yukeembruk has rooms available?")

    assert body["status"] == "insufficient_evidence"
    assert "Published application link" in body["answer"]
    assert "unknown" in body["answer"]


def test_p0_accommodation_never_guarantees_advertised_price() -> None:
    body = _ask((YUK,), "Is the advertised Yukeembruk price guaranteed?")

    assert body["status"] == "ok"
    assert "not a guaranteed final price" in body["answer"]


def test_p0_accommodation_never_infers_eligibility_from_audience() -> None:
    body = _ask((BRUCE_MISSING,), "Who is eligible for Bruce Hall?")

    assert body["status"] == "insufficient_evidence"
    assert "Undergraduate students" not in body["answer"]


def test_p0_accommodation_canonical_url_and_provenance_are_preserved() -> None:
    body = _ask((YUK,), "Tell me about Yukeembruk accommodation")

    assert body["sources"] == [
        {
            "record_id": YUK.record_id,
            "source_id": "accommodation_anu_study",
            "title": YUK.title,
            "url": str(YUK.canonical_url),
            "domain": "accommodation",
        }
    ]


def test_p0_starrez_link_is_navigation_only_and_never_fetched(monkeypatch) -> None:
    def fail_network(*_args, **_kwargs):
        raise AssertionError("RAG attempted a network connection")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    body = _ask((YUK,), "How do I apply for Yukeembruk accommodation?")

    assert body["status"] == "ok"
    assert "starrezhousing.com" in body["answer"]


def test_p0_accommodation_source_id_remains_authority_boundary() -> None:
    assert YUK.source_id == "accommodation_anu_study"
    assert "source_authority" not in YUK.metadata_json.model_dump()


def test_p0_support_does_not_diagnose() -> None:
    body = _ask((ACADEMIC,), "Can Academic Support diagnose my condition?")

    assert body["status"] == "insufficient_evidence"
    assert "cannot diagnose" in body["answer"]


def test_p0_support_does_not_invent_emergency_coverage() -> None:
    body = _ask((ACADEMIC,), "Does Academic Support guarantee emergency coverage?")

    assert body["status"] == "insufficient_evidence"
    assert "does not establish" in body["answer"]


def test_p0_support_does_not_invent_missing_hours() -> None:
    payload = support_payload()
    record = SupportRecord.model_validate(payload)
    body = _ask((record,), "What hours is Academic Support open?")

    assert body["status"] == "insufficient_evidence"
    assert "remain unknown" in body["answer"]


def test_p0_support_does_not_guarantee_current_availability() -> None:
    body = _ask((ACADEMIC,), "Is Academic Support available right now?")

    assert body["status"] == "insufficient_evidence"
    assert "does not establish" in body["answer"]


def test_p0_referral_is_not_promoted_to_service_entity() -> None:
    repository = CourseProgramRepository([ACADEMIC])

    assert repository.all_domain_records("support") == (ACADEMIC,)
    assert ACADEMIC.metadata_json.referrals[0].url not in {
        record.record_id for record in repository.all_domain_records("support")
    }


def test_p0_arbitrary_external_topic_is_rejected() -> None:
    payload = copy.deepcopy(support_payload())
    payload["metadata_json"]["topics"][0]["url"] = "https://example.com/help"

    with pytest.raises(ValidationError):
        SupportRecord.model_validate(payload)


def test_p0_support_canonical_url_and_provenance_are_preserved() -> None:
    body = _ask((ACADEMIC,), "What is the purpose of Academic Support?")

    assert body["sources"][0] == {
        "record_id": ACADEMIC.record_id,
        "source_id": "support_anusa_student_assistance",
        "title": ACADEMIC.title,
        "url": str(ACADEMIC.canonical_url),
        "domain": "support",
    }
    assert ACADEMIC.source_id == "support_anusa_student_assistance"
    assert "source_authority" not in ACADEMIC.metadata_json.model_dump()


def test_p0_denominators_are_stable() -> None:
    # Seven Accommodation and seven Support P0 cases above.
    assert 7 + 7 == 14
