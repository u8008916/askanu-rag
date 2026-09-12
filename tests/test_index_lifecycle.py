"""V5 index lifecycle policy and exact-retrieval independence."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from askanu_rag.hybrid_queries import HybridQueryService
from askanu_rag.index_lifecycle import (
    IndexAction,
    IndexTaskIdentity,
    LifecycleContractError,
    index_is_stale,
    plan_index_action,
    resolve_index_result,
)
from askanu_rag.main import create_app
from askanu_rag.models import CourseProgramRecord
from askanu_rag.query_planner import plan_query
from askanu_rag.retrieval import CourseProgramRepository, load_course_program_records
from askanu_rag.retrieval.semantic import SemanticHit


FIXTURE = Path(__file__).parents[1] / "fixtures/day5_course_program_records.json"


def record(**updates) -> CourseProgramRecord:
    base = load_course_program_records(FIXTURE)[0]
    return base.model_copy(update=updates)


def ask_payload(question: str) -> dict[str, object]:
    return {
        "question": question,
        "history": [],
        "conversation_state": {"pending_clarification": None},
    }


def test_unchanged_hash_emits_no_duplicate_index_action_and_preserves_state():
    pending = record(status="UNCHANGED", index_status="PENDING")
    failed = record(
        status="UNCHANGED", index_status="FAILED", embedding_version="old-v1"
    )

    pending_decision = plan_index_action(pending)
    failed_decision = plan_index_action(failed)

    assert pending_decision.action is IndexAction.NONE
    assert (pending_decision.index_status, pending_decision.embedding_version) == (
        "PENDING",
        None,
    )
    assert failed_decision.action is IndexAction.NONE
    assert (failed_decision.index_status, failed_decision.embedding_version) == (
        "FAILED",
        "old-v1",
    )


@pytest.mark.parametrize("source_status", ["NEW", "CHANGED"])
def test_new_or_changed_content_requires_pending_index_with_no_old_version(source_status):
    current = record(
        status=source_status, index_status="PENDING", embedding_version=None
    )
    decision = plan_index_action(current)

    assert decision.action is IndexAction.INDEX_CONTENT_CHANGE
    assert decision.index_status == "PENDING"
    assert decision.embedding_version is None

    with pytest.raises(LifecycleContractError):
        plan_index_action(
            record(
                status=source_status,
                index_status="INDEXED",
                embedding_version="old-v1",
            )
        )


def test_matching_success_failure_and_explicit_recovery_are_distinct_transitions():
    current = record(status="UNCHANGED", index_status="PENDING")
    task = IndexTaskIdentity(current.record_id, current.content_hash, "embed-v2")

    success = resolve_index_result(
        current, task, succeeded=True, produced_version="embed-v2"
    )
    failure = resolve_index_result(current, task, succeeded=False)
    failed = current.model_copy(update={"index_status": "FAILED"})
    retry = plan_index_action(failed, explicit_retry=True)
    recovered = resolve_index_result(
        failed, task, succeeded=True, produced_version="embed-v2"
    )

    assert (success.action, success.index_status, success.embedding_version) == (
        IndexAction.APPLY_SUCCESS,
        "INDEXED",
        "embed-v2",
    )
    assert (failure.action, failure.index_status) == (
        IndexAction.APPLY_FAILURE,
        "FAILED",
    )
    assert retry.action is IndexAction.RETRY
    assert (recovered.action, recovered.index_status, recovered.embedding_version) == (
        IndexAction.APPLY_SUCCESS,
        "INDEXED",
        "embed-v2",
    )


def test_invalid_success_and_late_old_task_cannot_be_reported_as_indexed():
    current = record(status="CHANGED", content_hash="b" * 64)
    old_task = IndexTaskIdentity(current.record_id, "a" * 64, "embed-v1")

    stale = resolve_index_result(
        current, old_task, succeeded=True, produced_version="embed-v1"
    )

    assert stale.action is IndexAction.DISCARD_STALE_RESULT
    assert stale.index_status == "PENDING"
    with pytest.raises(LifecycleContractError):
        resolve_index_result(
            current,
            IndexTaskIdentity(current.record_id, current.content_hash, "embed-v2"),
            succeeded=True,
            produced_version="wrong-version",
        )


def test_stale_is_derived_without_last_seen_ttl_or_new_schema_state():
    assert index_is_stale(record(status="UNCHANGED", index_status="PENDING"))
    assert index_is_stale(
        record(
            status="UNCHANGED",
            index_status="FAILED",
            embedding_version="embed-v1",
        )
    )
    indexed = record(
        status="UNCHANGED",
        index_status="INDEXED",
        embedding_version="embed-v1",
    )
    assert not index_is_stale(indexed)
    assert index_is_stale(indexed, target_version="embed-v2")


def test_missing_observation_does_not_delete_or_reembed():
    missing = record(
        status="MISSING", index_status="FAILED", embedding_version="embed-v1"
    )
    decision = plan_index_action(missing, explicit_retry=True, target_version="embed-v2")
    assert (decision.action, decision.index_status, decision.embedding_version) == (
        IndexAction.NONE,
        "FAILED",
        "embed-v1",
    )


class UnavailablePersistentVectors:
    uses_persistent_index = True

    def __init__(self):
        self.calls = 0

    def search(self, *_args, **_kwargs):
        self.calls += 1
        raise RuntimeError("vector provider unavailable secret details")


@pytest.mark.parametrize(
    ("index_status", "embedding_version"),
    [("PENDING", None), ("FAILED", None), ("INDEXED", None)],
)
def test_comp1110_exact_retrieval_works_without_usable_vector_index(
    index_status, embedding_version
):
    current = record(
        status="UNCHANGED",
        index_status=index_status,
        embedding_version=embedding_version,
    )
    vectors = UnavailablePersistentVectors()
    app = create_app(
        CourseProgramRepository([current]), semantic_retriever=vectors
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ask", json=ask_payload("Prerequisites for COMP1110 in 2026")
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["sources"][0]["record_id"] == current.record_id
    assert vectors.calls == 0


def test_persistent_semantic_boundary_excludes_stale_records():
    pending = record(status="UNCHANGED", index_status="PENDING")
    values = pending.model_dump(mode="python")
    values.update(
        record_id="courses:course:COMP2200_2026",
        entity_id="COMP2200_2026",
        title="Systems Networks and Concurrency",
        content_hash="c" * 64,
        index_status="INDEXED",
        embedding_version="embed-v1",
    )
    values["metadata_json"] = {
        **values["metadata_json"],
        "course_code": "COMP2200",
        "prerequisites": "COMP1110",
    }
    indexed = CourseProgramRecord.model_validate(values)

    class PersistentVectors:
        uses_persistent_index = True

        def __init__(self):
            self.candidates = ()

        def search(self, _query, candidates, **_kwargs):
            self.candidates = candidates
            return (SemanticHit(indexed.record_id, 1.0),)

    vectors = PersistentVectors()
    repository = CourseProgramRepository([pending, indexed])
    service = HybridQueryService(repository, semantic_retriever=vectors)
    plan = plan_query("Which ANU course teaches programming?", repository)

    assert service.retrieve(plan) == (indexed,)
    assert vectors.candidates == (indexed,)
