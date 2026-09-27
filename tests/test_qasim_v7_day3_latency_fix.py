from __future__ import annotations

from askanu_rag.conversation import (
    _records_for_codes,
)
from askanu_rag.hybrid_queries import (
    HybridQueryService,
)
from askanu_rag.query_planner import (
    plan_query,
)
from test_grounded_synthesis import record


class NoCatalogueScan:
    def all_records(self):
        raise AssertionError(
            "full catalogue scan was not expected"
        )


def test_explicit_course_plan_avoids_catalogue_scan():
    plan = plan_query(
        "Tell me about COMP1110 in 2026",
        NoCatalogueScan(),
    )

    assert plan.route == "exact"
    assert plan.identifiers == (
        ("course", "COMP1110"),
    )
    assert plan.academic_year == "2026"


def test_course_topic_plan_avoids_catalogue_scan():
    plan = plan_query(
        (
            "Which ANU course covers graphs, "
            "data structures and analysing complexity?"
        ),
        NoCatalogueScan(),
    )

    assert plan.route == "semantic"
    assert plan.entity_type == "course"
    assert plan.semantic_allowed


def test_unique_retained_course_uses_direct_lookup():
    source = record(
        year="2026"
    )

    class DirectRepository:
        def find_course_by_code(
            self,
            identifier,
            academic_year=None,
        ):
            assert identifier == "COMP1110"
            assert academic_year == "2026"
            return source

        def all_records(self):
            raise AssertionError(
                "full catalogue scan was not expected"
            )

    assert _records_for_codes(
        DirectRepository(),
        ("COMP1110",),
        ("2026",),
    ) == (source,)


class EmptySparse:
    uses_persistent_index = False

    def search(
        self,
        query,
        candidates,
        *,
        top_k,
        min_score,
    ):
        return ()


class CapturingVector:
    def __init__(self):
        self.allowed = None

    def search(
        self,
        query,
        *,
        domain,
        allowed_records,
        top_k,
    ):
        self.allowed = tuple(
            allowed_records
        )
        return ()


class OneRecordRepository:
    def __init__(self, source):
        self.source = source

    def all_records(self):
        return (
            self.source,
        )


def test_semantic_full_population_does_not_send_redundant_allowlist():
    source = record()

    vector = CapturingVector()

    service = HybridQueryService(
        OneRecordRepository(source),
        semantic_retriever=EmptySparse(),
        vector_retriever=vector,
    )

    plan = plan_query(
        (
            "Which ANU course covers "
            "algorithms and complexity?"
        ),
        OneRecordRepository(source),
    )

    service.retrieve(plan)

    assert vector.allowed == ()


def test_hard_year_filter_keeps_vector_allowlist():
    source_2025 = record(
        year="2025"
    )

    source_2026 = record(
        year="2026"
    )

    class TwoRecordRepository:
        def all_records(self):
            return (
                source_2025,
                source_2026,
            )

    vector = CapturingVector()

    service = HybridQueryService(
        TwoRecordRepository(),
        semantic_retriever=EmptySparse(),
        vector_retriever=vector,
    )

    plan = plan_query(
        (
            "Which ANU course in 2026 "
            "covers algorithms and complexity?"
        ),
        TwoRecordRepository(),
    )

    service.retrieve(plan)

    assert vector.allowed == (
        source_2026,
    )
