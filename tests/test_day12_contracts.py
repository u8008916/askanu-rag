"""Frozen Day 12 Accommodation and Support serialized-contract tests."""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from askanu_rag.models import (
    AccommodationRecord,
    SupportRecord,
    SupportReferral,
    SupportTopic,
)
from askanu_rag.retrieval import CourseProgramRepository


OBSERVED = datetime(2026, 9, 16, tzinfo=timezone.utc)


def _envelope(
    *,
    record_id: str,
    source_id: str,
    entity_id: str,
    domain: str,
    title: str,
    canonical_url: str,
    metadata_json: dict[str, object],
) -> dict[str, object]:
    content = f"Published source content for {title}."
    return {
        "record_id": record_id,
        "source_id": source_id,
        "entity_id": entity_id,
        "domain": domain,
        "title": title,
        "content": content,
        "canonical_url": canonical_url,
        "status": "NEW",
        "effective_from": None,
        "effective_to": None,
        "collected_at": OBSERVED,
        "last_seen_at": OBSERVED,
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "embedding_version": None,
        "index_status": "PENDING",
        "metadata_json": metadata_json,
    }


def accommodation_payload() -> dict[str, object]:
    return _envelope(
        record_id="accommodation:residence:yukeembruk",
        source_id="accommodation_anu_study",
        entity_id="yukeembruk",
        domain="accommodation",
        title="Yukeembruk",
        canonical_url=(
            "https://study.anu.edu.au/accommodation/our-residences/yukeembruk"
        ),
        metadata_json={
            "entity_type": "residence",
            "category": "Self-catered residence",
            "location": "Acton campus",
            "catering_options": ["Self-catered"],
            "audiences": ["Undergraduate students", "Postgraduate students"],
            "advertised_rate": "From $340 per week",
            "cost_period": "2026 academic year",
            "rooms": [
                {
                    "name": "Single studio",
                    "rate": "$340 per week",
                    "contract": "44 weeks",
                    "inclusions": "Utilities and internet",
                    "other_fees": "Refundable deposit applies",
                }
            ],
            "features": ["Study rooms", "Shared kitchen"],
            "overview": "A self-catered ANU residence.",
            "accessibility": "Accessible rooms are published.",
            "application_text": "Apply through the published portal.",
            "application_url": "https://anu.starrezhousing.com/StarRezPortalX",
            "eligibility": "Open to enrolled ANU students.",
            "contact": {
                "email": "accommodation@anu.edu.au",
                "phone": "02 6125 0000",
                "location": "Accommodation Services reception",
                "hours": "Monday to Friday, 9 am to 5 pm",
            },
            "vacancy_status": None,
        },
    )


def support_payload() -> dict[str, object]:
    return _envelope(
        record_id="support:support_service:academic",
        source_id="support_anusa_student_assistance",
        entity_id="academic",
        domain="support",
        title="Academic Support",
        canonical_url="https://anusa.com.au/student-assistance/academic/",
        metadata_json={
            "entity_type": "support_service",
            "category": "Academic",
            "purpose": "ANUSA can help with academic issues.",
            "audiences": ["all ANU Students"],
            "contact": {
                "email": "sa.assistance@anu.edu.au",
                "phone": "02 6125 2444",
                "location": "Level 2, Di Riddell Student Centre, Kambri",
            },
            "hours": None,
            "access": None,
            "cost": "The service is free.",
            "topics": [
                {
                    "title": "Grade Appeal",
                    "description": "Advice about appealing a grade.",
                    "url": (
                        "https://anusa.com.au/student-assistance/academic/"
                        "grade-appeal/"
                    ),
                }
            ],
            "referrals": [
                {
                    "label": "ANU assessment guidance",
                    "url": (
                        "https://www.anu.edu.au/students/"
                        "program-administration/assessments-exams"
                    ),
                }
            ],
        },
    )


def _invalid(model, payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_valid_frozen_accommodation_representative_validates() -> None:
    record = AccommodationRecord.model_validate(accommodation_payload())

    assert record.metadata_json.entity_type == "residence"
    assert record.record_id == "accommodation:residence:yukeembruk"
    assert record.metadata_json.rooms[0].contract == "44 weeks"


def test_accommodation_requires_residence_entity_type() -> None:
    payload = accommodation_payload()
    payload["metadata_json"]["entity_type"] = "accommodation"
    _invalid(AccommodationRecord, payload)


def test_accommodation_exact_record_id_is_enforced() -> None:
    payload = accommodation_payload()
    payload["record_id"] = "accommodation:accommodation:yukeembruk"
    _invalid(AccommodationRecord, payload)


def test_accommodation_record_id_entity_mismatch_is_rejected() -> None:
    payload = accommodation_payload()
    payload["record_id"] = "accommodation:residence:bruce-hall"
    _invalid(AccommodationRecord, payload)


def test_accommodation_canonical_entity_mismatch_is_rejected() -> None:
    payload = accommodation_payload()
    payload["canonical_url"] = (
        "https://study.anu.edu.au/accommodation/our-residences/bruce-hall"
    )
    _invalid(AccommodationRecord, payload)


def test_accommodation_wrong_source_is_rejected() -> None:
    payload = accommodation_payload()
    payload["source_id"] = "support_anusa_student_assistance"
    _invalid(AccommodationRecord, payload)


def test_accommodation_extra_metadata_is_rejected() -> None:
    payload = accommodation_payload()
    payload["metadata_json"]["source_authority"] = "official_anu"
    _invalid(AccommodationRecord, payload)


def test_accommodation_room_relationships_survive_validation() -> None:
    room = AccommodationRecord.model_validate(
        accommodation_payload()
    ).metadata_json.rooms[0]

    assert room.model_dump() == {
        "name": "Single studio",
        "rate": "$340 per week",
        "contract": "44 weeks",
        "inclusions": "Utilities and internet",
        "other_fees": "Refundable deposit applies",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        {"name": "Single", "rate": "$1"},
        {
            "name": "Single",
            "rate": 340,
            "contract": None,
            "inclusions": None,
            "other_fees": None,
        },
    ],
)
def test_malformed_accommodation_room_is_rejected(mutation) -> None:
    payload = accommodation_payload()
    payload["metadata_json"]["rooms"] = [mutation]
    _invalid(AccommodationRecord, payload)


def test_accommodation_contact_is_strict() -> None:
    payload = accommodation_payload()
    payload["metadata_json"]["contact"]["team"] = "Housing"
    _invalid(AccommodationRecord, payload)


def test_residence_and_contact_locations_remain_independent() -> None:
    record = AccommodationRecord.model_validate(accommodation_payload())

    assert record.metadata_json.location == "Acton campus"
    assert record.metadata_json.contact.location == "Accommodation Services reception"


def test_vacancy_status_null_remains_unknown() -> None:
    record = AccommodationRecord.model_validate(accommodation_payload())

    assert record.metadata_json.vacancy_status is None


def test_source_backed_vacancy_status_survives() -> None:
    payload = accommodation_payload()
    payload["metadata_json"]["vacancy_status"] = "No vacancies published"

    record = AccommodationRecord.model_validate(payload)
    assert record.metadata_json.vacancy_status == "No vacancies published"


@pytest.mark.parametrize(
    "url",
    [
        "https://starrezhousing.com/StarRezPortalX",
        "https://anu.starrezhousing.com.evil.example/StarRezPortalX",
        "https://example.com/StarRezPortalX",
    ],
)
def test_invalid_application_host_is_rejected(url: str) -> None:
    payload = accommodation_payload()
    payload["metadata_json"]["application_url"] = url
    _invalid(AccommodationRecord, payload)


def test_https_starrez_subdomain_is_accepted() -> None:
    record = AccommodationRecord.model_validate(accommodation_payload())

    assert record.metadata_json.application_url.startswith(
        "https://anu.starrezhousing.com/"
    )


def test_https_starrez_host_only_destination_is_accepted() -> None:
    payload = accommodation_payload()
    payload["metadata_json"]["application_url"] = "https://anu.starrezhousing.com"

    record = AccommodationRecord.model_validate(payload)
    assert record.metadata_json.application_url == "https://anu.starrezhousing.com"


def test_http_starrez_is_rejected() -> None:
    payload = accommodation_payload()
    payload["metadata_json"]["application_url"] = (
        "http://anu.starrezhousing.com/StarRezPortalX"
    )
    _invalid(AccommodationRecord, payload)


def test_unknown_nested_accommodation_field_is_rejected() -> None:
    payload = accommodation_payload()
    payload["metadata_json"]["rooms"][0]["available"] = True
    _invalid(AccommodationRecord, payload)


@pytest.mark.parametrize(
    "field",
    [
        "category",
        "location",
        "advertised_rate",
        "cost_period",
        "overview",
        "accessibility",
        "application_text",
        "eligibility",
        "vacancy_status",
    ],
)
def test_accommodation_nullable_strings_reject_whitespace(field: str) -> None:
    payload = accommodation_payload()
    payload["metadata_json"][field] = "   "
    _invalid(AccommodationRecord, payload)


@pytest.mark.parametrize("field", ["catering_options", "audiences", "features"])
def test_accommodation_arrays_reject_blank_items(field: str) -> None:
    payload = accommodation_payload()
    payload["metadata_json"][field] = ["   "]
    _invalid(AccommodationRecord, payload)


@pytest.mark.parametrize(
    "field", ["name", "rate", "contract", "inclusions", "other_fees"]
)
def test_accommodation_room_strings_reject_whitespace(field: str) -> None:
    payload = accommodation_payload()
    payload["metadata_json"]["rooms"][0][field] = "   "
    _invalid(AccommodationRecord, payload)


@pytest.mark.parametrize("field", ["email", "phone", "location", "hours"])
def test_accommodation_contact_strings_reject_whitespace(field: str) -> None:
    payload = accommodation_payload()
    payload["metadata_json"]["contact"][field] = "   "
    _invalid(AccommodationRecord, payload)


def test_valid_frozen_support_representative_validates() -> None:
    record = SupportRecord.model_validate(support_payload())

    assert record.record_id == "support:support_service:academic"
    assert record.metadata_json.entity_type == "support_service"


def test_support_requires_exact_entity_type() -> None:
    payload = support_payload()
    payload["metadata_json"]["entity_type"] = "service"
    _invalid(SupportRecord, payload)


def test_support_frozen_record_id_is_accepted() -> None:
    record = SupportRecord.model_validate(support_payload())

    assert record.record_id == "support:support_service:academic"


def test_old_support_service_record_id_is_rejected() -> None:
    payload = support_payload()
    payload["record_id"] = "support:service:academic"
    _invalid(SupportRecord, payload)


def test_support_canonical_entity_mismatch_is_rejected() -> None:
    payload = support_payload()
    payload["canonical_url"] = (
        "https://anusa.com.au/student-assistance/financial/"
    )
    _invalid(SupportRecord, payload)


def test_support_extra_metadata_is_rejected() -> None:
    payload = support_payload()
    payload["metadata_json"]["source_authority"] = "approved_anusa"
    _invalid(SupportRecord, payload)


def test_support_contact_is_strict() -> None:
    payload = support_payload()
    payload["metadata_json"]["contact"]["hours"] = "9 to 5"
    _invalid(SupportRecord, payload)


def test_support_missing_hours_and_access_stay_null() -> None:
    metadata = SupportRecord.model_validate(support_payload()).metadata_json

    assert metadata.hours is None
    assert metadata.access is None


def test_internal_student_assistance_topic_is_accepted() -> None:
    topic = SupportRecord.model_validate(
        support_payload()
    ).metadata_json.topics[0]

    assert isinstance(topic, SupportTopic)


def test_external_topic_url_is_rejected() -> None:
    payload = support_payload()
    payload["metadata_json"]["topics"][0]["url"] = "https://example.com/topic"
    _invalid(SupportRecord, payload)


def test_topic_url_requires_a_nested_student_assistance_topic_path() -> None:
    payload = support_payload()
    payload["metadata_json"]["topics"][0]["url"] = (
        "https://anusa.com.au/student-assistance/academic/"
    )
    _invalid(SupportRecord, payload)


def test_external_referral_http_url_is_accepted() -> None:
    payload = support_payload()
    payload["metadata_json"]["referrals"][0]["url"] = (
        "http://www.anu.edu.au/students"
    )

    referral = SupportRecord.model_validate(payload).metadata_json.referrals[0]
    assert isinstance(referral, SupportReferral)


@pytest.mark.parametrize(
    "url",
    [
        "https://anusa.com.au/student-assistance/academic/other/",
        "https://user:secret@example.com/referral",
    ],
)
def test_referral_must_be_external_and_credential_free(url: str) -> None:
    payload = support_payload()
    payload["metadata_json"]["referrals"][0]["url"] = url
    _invalid(SupportRecord, payload)


def test_referral_is_not_promoted_to_topic() -> None:
    metadata = SupportRecord.model_validate(support_payload()).metadata_json

    assert isinstance(metadata.referrals[0], SupportReferral)
    assert not isinstance(metadata.referrals[0], SupportTopic)


def test_referral_is_not_promoted_to_support_entity() -> None:
    record = SupportRecord.model_validate(support_payload())
    repository = CourseProgramRepository([record])

    assert repository.all_domain_records("support") == (record,)
    assert all(
        item.record_id != record.metadata_json.referrals[0].url
        for item in repository.all_domain_records("support")
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("topics", [{"title": "Appeal", "url": "https://anusa.com.au/student-assistance/academic/appeal/"}]),
        ("referrals", [{"label": "ANU"}]),
        ("audiences", "all ANU Students"),
    ],
)
def test_malformed_support_nested_structures_are_rejected(field, value) -> None:
    payload = copy.deepcopy(support_payload())
    payload["metadata_json"][field] = value
    _invalid(SupportRecord, payload)


@pytest.mark.parametrize("field", ["category", "purpose", "hours", "access", "cost"])
def test_support_nullable_strings_reject_whitespace(field: str) -> None:
    payload = support_payload()
    payload["metadata_json"][field] = "   "
    _invalid(SupportRecord, payload)


def test_support_audiences_reject_blank_items() -> None:
    payload = support_payload()
    payload["metadata_json"]["audiences"] = ["   "]
    _invalid(SupportRecord, payload)


@pytest.mark.parametrize("field", ["email", "phone", "location"])
def test_support_contact_strings_reject_whitespace(field: str) -> None:
    payload = support_payload()
    payload["metadata_json"]["contact"][field] = "   "
    _invalid(SupportRecord, payload)


@pytest.mark.parametrize("field", ["title", "description"])
def test_support_topic_strings_reject_whitespace(field: str) -> None:
    payload = support_payload()
    payload["metadata_json"]["topics"][0][field] = "   "
    _invalid(SupportRecord, payload)


def test_support_referral_label_rejects_whitespace() -> None:
    payload = support_payload()
    payload["metadata_json"]["referrals"][0]["label"] = "   "
    _invalid(SupportRecord, payload)
