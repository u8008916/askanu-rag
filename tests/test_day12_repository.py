"""Repository loading for the frozen richer Day 12 records."""

from askanu_rag.models import AccommodationRecord, CommonRecord, SupportRecord
from askanu_rag.retrieval import CourseProgramRepository, PostgresCourseProgramRepository
from test_day12_contracts import accommodation_payload, support_payload


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, _query, _parameters=()):
        return None

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return Cursor(self.rows)


def _postgres_row(payload):
    record = CommonRecord.model_validate(payload)
    values = record.model_dump(mode="python")
    values["canonical_url"] = str(record.canonical_url)
    values["metadata_json"] = record.metadata_json.model_dump(mode="python")
    return values


def test_in_memory_repository_preserves_all_accommodation_relationships() -> None:
    record = CommonRecord.model_validate(accommodation_payload())
    loaded = CourseProgramRepository([record]).all_domain_records("accommodation")[0]

    assert isinstance(loaded, AccommodationRecord)
    metadata = loaded.metadata_json
    assert metadata.category == "Self-catered residence"
    assert metadata.location == "Acton campus"
    assert metadata.catering_options == ["Self-catered"]
    assert metadata.audiences == ["Undergraduate students", "Postgraduate students"]
    assert metadata.advertised_rate == "From $340 per week"
    assert metadata.cost_period == "2026 academic year"
    assert metadata.rooms[0].model_dump() == {
        "name": "Single studio",
        "rate": "$340 per week",
        "contract": "44 weeks",
        "inclusions": "Utilities and internet",
        "other_fees": "Refundable deposit applies",
    }
    assert metadata.features == ["Study rooms", "Shared kitchen"]
    assert metadata.overview == "A self-catered ANU residence."
    assert metadata.accessibility == "Accessible rooms are published."
    assert metadata.application_text == "Apply through the published portal."
    assert metadata.application_url.startswith("https://anu.starrezhousing.com/")
    assert metadata.eligibility == "Open to enrolled ANU students."
    assert metadata.contact.location == "Accommodation Services reception"
    assert metadata.vacancy_status is None


def test_in_memory_repository_preserves_support_topics_and_referrals_nested() -> None:
    record = CommonRecord.model_validate(support_payload())
    repository = CourseProgramRepository([record])
    loaded = repository.all_domain_records("support")[0]

    assert isinstance(loaded, SupportRecord)
    metadata = loaded.metadata_json
    assert metadata.category == "Academic"
    assert metadata.purpose == "ANUSA can help with academic issues."
    assert metadata.audiences == ["all ANU Students"]
    assert metadata.contact.email == "sa.assistance@anu.edu.au"
    assert metadata.hours is None
    assert metadata.access is None
    assert metadata.cost == "The service is free."
    assert metadata.topics[0].title == "Grade Appeal"
    assert metadata.referrals[0].label == "ANU assessment guidance"
    assert repository.all_domain_records("support") == (loaded,)


def test_postgres_repository_deserializes_frozen_accommodation_row() -> None:
    row = _postgres_row(accommodation_payload())
    repository = PostgresCourseProgramRepository(lambda: Connection([row]))

    records = repository.all_domain_records("accommodation")

    assert len(records) == 1
    assert isinstance(records[0], AccommodationRecord)
    assert records[0].metadata_json.rooms[0].other_fees == "Refundable deposit applies"


def test_postgres_repository_deserializes_frozen_support_row_without_promotion() -> None:
    row = _postgres_row(support_payload())
    repository = PostgresCourseProgramRepository(lambda: Connection([row]))

    records = repository.all_domain_records("support")

    assert len(records) == 1
    assert isinstance(records[0], SupportRecord)
    assert records[0].metadata_json.referrals[0].url.startswith("https://www.anu.edu.au/")
