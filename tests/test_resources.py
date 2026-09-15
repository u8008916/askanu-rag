"""Approved Accommodation and Support retrieval and claims boundaries."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from askanu_rag.main import create_app
from askanu_rag.models import (
    AccommodationMetadata,
    AccommodationRecord,
    SupportMetadata,
    SupportRecord,
)
from askanu_rag.retrieval import CourseProgramRepository
from askanu_rag.retrieval.vector import VectorHit


def accommodation(
    entity_id: str = "fenner-hall",
    *,
    title: str = "Fenner Hall",
    advertised_rate: str | None = "$350 per week for the advertised 2026 term",
    facilities: list[str] | None = None,
) -> AccommodationRecord:
    content = (
        f"{title} is a self-catered residence near campus with quiet study spaces."
    )
    observed = datetime(2026, 9, 15, tzinfo=timezone.utc)
    return AccommodationRecord(
        record_id=f"accommodation:accommodation:{entity_id}",
        source_id="accommodation_anu_study",
        entity_id=entity_id,
        domain="accommodation",
        title=title,
        content=content,
        canonical_url=(
            f"https://study.anu.edu.au/accommodation/our-residences/{entity_id}"
        ),
        status="NEW",
        effective_from=None,
        effective_to=None,
        collected_at=observed,
        last_seen_at=observed,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        embedding_version=None,
        index_status="PENDING",
        metadata_json=AccommodationMetadata(
            entity_type="accommodation",
            source_authority="official_anu",
            accommodation_type="Residence hall",
            location="Acton campus",
            catering="Self-catered",
            audience=["Undergraduate students"],
            room_types=["Single room"],
            advertised_rate=advertised_rate,
            rate_inclusions=["Utilities"],
            rate_exclusions=["Meals"],
            facilities=facilities or ["Quiet study spaces", "Shared kitchen"],
            application_information="Apply through the ANU accommodation portal.",
            eligibility=None,
            contract_term="Academic year",
            contact="Accommodation Services",
        ),
    )


def support(
    entity_id: str = "legal-service",
    *,
    title: str = "ANUSA Legal Service",
    hours: str | None = None,
    content: str = "Provides source-published help with tenancy and landlord problems.",
    categories: list[str] | None = None,
) -> SupportRecord:
    observed = datetime(2026, 9, 15, tzinfo=timezone.utc)
    return SupportRecord(
        record_id=f"support:support_service:{entity_id}",
        source_id="support_anusa_student_assistance",
        entity_id=entity_id,
        domain="support",
        title=title,
        content=content,
        canonical_url=f"https://anusa.com.au/student-assistance/{entity_id}/",
        status="NEW",
        effective_from=None,
        effective_to=None,
        collected_at=observed,
        last_seen_at=observed,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        embedding_version=None,
        index_status="PENDING",
        metadata_json=SupportMetadata(
            entity_type="support_service",
            source_authority="approved_anusa",
            categories=categories or ["Accommodation support", "Advocacy"],
            contact="legal@anusa.com.au",
            location="ANU campus",
            hours=hours,
            audience=["ANU students"],
            access_instructions="Use the official service enquiry form.",
            cost="Free for ANU students",
        ),
    )


def ask(repo, question: str, *, vector=None, pending=None):
    with TestClient(create_app(repo, vector_retriever=vector)) as client:
        response = client.post(
            "/api/v1/ask",
            json={
                "question": question,
                "history": [],
                "conversation_state": {"pending_clarification": pending},
            },
        )
    assert response.status_code == 200
    return response.json()


def test_specific_residence_cost_uses_advertised_wording_and_source():
    record = accommodation()
    body = ask(CourseProgramRepository([record]), "How much does Fenner Hall cost?")

    assert body["status"] == "ok"
    assert "advertised rate wording" in body["answer"]
    assert "not live vacancy or a guaranteed price" in body["answer"]
    assert body["sources"][0]["record_id"] == record.record_id


def test_live_vacancy_remains_unknown_even_with_application_information():
    record = accommodation()
    body = ask(CourseProgramRepository([record]), "Is Fenner Hall available now?")

    assert body["status"] == "insufficient_evidence"
    assert "do not establish live vacancy" in body["answer"]
    assert body["sources"][0]["url"] == str(record.canonical_url)


def test_fuzzy_accommodation_suitability_uses_shared_vector_candidates():
    record = accommodation()

    class FixedVector:
        def search(self, _question, *, domain, allowed_records, **_kwargs):
            assert domain == "accommodation"
            assert record in allowed_records
            return (VectorHit(record, 0.92, ("whole",)),)

    body = ask(
        CourseProgramRepository([record]),
        "I want a quiet self-catered residence close to campus",
        vector=FixedVector(),
    )

    assert body["status"] == "ok"
    assert "Fenner Hall" in body["answer"]
    assert body["sources"][0]["domain"] == "accommodation"


def test_fuzzy_landlord_problem_routes_to_approved_support_service():
    record = support()

    class FixedVector:
        def search(self, _question, *, domain, allowed_records, **_kwargs):
            assert domain == "support"
            return (VectorHit(allowed_records[0], 0.95, ("whole",)),)

    body = ask(
        CourseProgramRepository([record]),
        "I'm having problems with my landlord and I don't know who at ANU can help",
        vector=FixedVector(),
    )

    assert body["status"] == "ok"
    assert "ANUSA Legal Service" in body["answer"]
    assert "cannot diagnose" in body["answer"]
    assert body["sources"][0]["record_id"] == record.record_id


def test_missing_support_hours_are_not_invented():
    record = support(hours=None)
    body = ask(
        CourseProgramRepository([record]),
        "What hours is the ANUSA Legal Service open?",
    )

    assert body["status"] == "insufficient_evidence"
    assert "does not publish" in body["answer"]
    assert body["sources"][0]["record_id"] == record.record_id


def test_resource_pending_selection_is_validated_against_current_records():
    first = accommodation()
    second = accommodation("ursula-hall", title="Ursula Hall")
    repository = CourseProgramRepository([first, second])

    broad = ask(repository, "Tell me about accommodation")
    assert broad["status"] == "needs_clarification"

    selected = ask(
        repository,
        "first",
        pending=broad["clarification"],
    )

    assert selected["status"] == "ok"
    assert selected["sources"][0]["record_id"] == first.record_id


def test_compare_residences_returns_bounded_grounded_sources():
    first = accommodation()
    second = accommodation("ursula-hall", title="Ursula Hall")

    class FixedVector:
        def search(self, _question, *, allowed_records, **_kwargs):
            return tuple(
                VectorHit(record, 0.9 - index / 10, ("whole",))
                for index, record in enumerate(allowed_records)
            )

    body = ask(
        CourseProgramRepository([first, second]),
        "Compare residences for quiet study",
        vector=FixedVector(),
    )

    assert body["status"] == "ok"
    assert {source["record_id"] for source in body["sources"]} == {
        first.record_id,
        second.record_id,
    }


def test_accommodation_facilities_and_application_are_source_projected():
    record = accommodation()

    facilities = ask(
        CourseProgramRepository([record]),
        "What facilities does Fenner Hall have?",
    )
    application = ask(
        CourseProgramRepository([record]),
        "How do I apply for Fenner Hall accommodation?",
    )

    assert facilities["status"] == "ok"
    assert "Quiet study spaces" in facilities["answer"]
    assert application["status"] == "ok"
    assert "ANU accommodation portal" in application["answer"]


def test_support_published_hours_and_contact_are_not_generalized():
    record = support(hours="Monday to Friday, 9 am to 5 pm")
    body = ask(
        CourseProgramRepository([record]),
        "What hours is the ANUSA Legal Service open and how do I contact it?",
    )

    assert body["status"] == "ok"
    assert "Monday to Friday, 9 am to 5 pm" in body["answer"]
    assert "legal@anusa.com.au" in body["answer"]


def test_specific_resource_fuzzy_miss_abstains_without_catalog_clarification():
    repository = CourseProgramRepository([accommodation(), accommodation("ursula-hall", title="Ursula Hall")])
    body = ask(repository, "Tell me about Imaginary Hall accommodation")

    assert body["status"] == "insufficient_evidence"
    assert body["clarification"] is None


def test_mental_health_routing_remains_conservative_and_source_grounded():
    record = support(
        "wellbeing-service",
        title="Student Wellbeing Service",
        content="Published wellbeing support and referral information for ANU students.",
        categories=["Mental health and wellbeing routing"],
    )

    class FixedVector:
        def search(self, _question, *, allowed_records, **_kwargs):
            return (VectorHit(allowed_records[0], 0.94, ("whole",)),)

    body = ask(
        CourseProgramRepository([record]),
        "I need mental health support and don't know which service can assist",
        vector=FixedVector(),
    )

    assert body["status"] == "ok"
    assert "cannot diagnose" in body["answer"]
    assert "promise professional availability" in body["answer"]
    assert body["sources"][0]["record_id"] == record.record_id
