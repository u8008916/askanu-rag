"""Cheap domain routing must prevent unrelated repository reads."""

from pathlib import Path

from fastapi.testclient import TestClient

from askanu_rag.database import RepositoryUnavailableError
from askanu_rag.main import create_app
from askanu_rag.retrieval import CourseProgramRepository, load_course_program_records

FIXTURE = Path(__file__).parents[1] / "fixtures/day5_course_program_records.json"


class ReadSpyRepository(CourseProgramRepository):
    def __init__(self):
        super().__init__(load_course_program_records(FIXTURE))
        self.reads = {
            "courses": 0,
            "scholarships": 0,
            "jobs": 0,
            "accommodation": 0,
            "support": 0,
        }

    def all_records(self):
        self.reads["courses"] += 1
        return super().all_records()

    def all_scholarships(self):
        self.reads["scholarships"] += 1
        return super().all_scholarships()

    def current_job_candidates(self, today, employment_type=None):
        self.reads["jobs"] += 1
        return super().current_job_candidates(today, employment_type)

    def all_domain_records(self, domain):
        self.reads[domain] += 1
        return super().all_domain_records(domain)


def post(repository, question, pending=None):
    with TestClient(create_app(repository)) as client:
        return client.post(
            "/api/v1/ask",
            json={
                "question": question,
                "history": [],
                "conversation_state": {"pending_clarification": pending},
            },
        )


def test_course_request_does_not_read_other_domain_tables():
    repository = ReadSpyRepository()
    response = post(repository, "What are the prerequisites for COMP1110?")
    assert response.status_code == 200
    assert repository.reads["courses"] > 0
    assert {key: value for key, value in repository.reads.items() if key != "courses"} == {
        "scholarships": 0,
        "jobs": 0,
        "accommodation": 0,
        "support": 0,
    }


def test_each_non_course_route_reads_only_its_own_domain():
    cases = (
        ("Show scholarships", "scholarships"),
        ("What current jobs are open?", "jobs"),
        ("Show accommodation", "accommodation"),
        ("I need landlord support", "support"),
    )
    for question, expected in cases:
        repository = ReadSpyRepository()
        response = post(repository, question)
        assert response.status_code == 200
        assert repository.reads[expected] > 0
        assert all(
            value == 0
            for domain, value in repository.reads.items()
            if domain != expected
        )


def test_queried_domain_failure_is_not_masked_by_fallback_domains():
    class BrokenScholarships(ReadSpyRepository):
        def all_scholarships(self):
            self.reads["scholarships"] += 1
            raise RepositoryUnavailableError()

    repository = BrokenScholarships()
    response = post(repository, "Show scholarships")
    assert response.status_code == 500
    assert repository.reads == {
        "courses": 0,
        "scholarships": 1,
        "jobs": 0,
        "accommodation": 0,
        "support": 0,
    }


def test_explicit_course_switch_beats_stale_resource_clarification():
    repository = ReadSpyRepository()
    pending = {
        "id": "clar-accommodation-selection",
        "type": "accommodation_selection",
        "options": [
            {"id": "accommodation:accommodation:fenner-hall", "label": "Fenner Hall"}
        ],
        "allow_multiple": False,
    }

    response = post(
        repository,
        "What are the prerequisites for COMP1110?",
        pending,
    )

    assert response.status_code == 200
    assert repository.reads["courses"] > 0
    assert repository.reads["accommodation"] == 0
    assert repository.reads["support"] == 0
