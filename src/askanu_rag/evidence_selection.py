"""Shared candidate-to-evidence and epistemic-state policy boundary."""

from collections.abc import Sequence

from askanu_rag.models import (
    AnswerState,
    EvidenceBundle,
    EvidenceItem,
    EntityKind,
    MissingEvidence,
    ResultSet,
    ResultSetStatus,
    RetrievalPlan,
)


def classify_result_set_status(
    ordered_canonical_ids: Sequence[str], *, population_complete: bool
) -> ResultSetStatus:
    """Keep retrieval completeness separate from answer certainty."""

    if ordered_canonical_ids:
        return ResultSetStatus.RESULTS
    return (
        ResultSetStatus.EMPTY
        if population_complete
        else ResultSetStatus.INCOMPLETE
    )


def classify_answer_state(
    *,
    selected_evidence: Sequence[EvidenceItem],
    missing_evidence: Sequence[MissingEvidence],
    derived: bool = False,
) -> AnswerState:
    """Classify what the selected approved evidence can actually support."""

    if not selected_evidence:
        if not missing_evidence:
            raise ValueError("no selected evidence requires an explicit missing reason")
        return AnswerState.UNKNOWN
    if missing_evidence:
        return AnswerState.PARTIAL
    return AnswerState.DERIVED if derived else AnswerState.CONFIRMED


def build_result_set(
    plan: RetrievalPlan,
    *,
    result_set_id: str,
    entity_kind: EntityKind,
    ordered_canonical_ids: Sequence[str],
    originating_query: str,
    created_turn: int,
    population_complete: bool,
    parent_result_set_id: str | None = None,
) -> ResultSet:
    """Create one stable ordered ResultSet without rerunning retrieval later."""

    return ResultSet(
        result_set_id=result_set_id,
        domain=plan.domain,
        entity_kind=entity_kind,
        ordered_canonical_ids=tuple(ordered_canonical_ids),
        originating_query=originating_query,
        intent=plan.intent,
        constraints=plan.constraints,
        created_turn=created_turn,
        last_refined_turn=created_turn,
        status=classify_result_set_status(
            ordered_canonical_ids, population_complete=population_complete
        ),
        parent_result_set_id=parent_result_set_id,
    )


def build_evidence_bundle(
    plan: RetrievalPlan,
    *,
    bundle_id: str,
    selected_evidence: Sequence[EvidenceItem] = (),
    missing_evidence: Sequence[MissingEvidence] = (),
    answer_state: AnswerState,
    result_set_id: str | None = None,
) -> EvidenceBundle:
    """Validate already-selected approved evidence against the Day 1 contract."""

    return EvidenceBundle(
        bundle_id=bundle_id,
        plan_id=plan.plan_id,
        result_set_id=result_set_id,
        selected_evidence=tuple(selected_evidence),
        missing_evidence=tuple(missing_evidence),
        answer_state=answer_state,
    )


def build_reasoned_evidence_bundle(
    plan: RetrievalPlan,
    *,
    bundle_id: str,
    selected_evidence: Sequence[EvidenceItem] = (),
    missing_evidence: Sequence[MissingEvidence] = (),
    derived: bool = False,
    result_set_id: str | None = None,
) -> EvidenceBundle:
    """Build a bundle whose certainty is derived from evidence, not state."""

    return build_evidence_bundle(
        plan,
        bundle_id=bundle_id,
        selected_evidence=selected_evidence,
        missing_evidence=missing_evidence,
        answer_state=classify_answer_state(
            selected_evidence=selected_evidence,
            missing_evidence=missing_evidence,
            derived=derived,
        ),
        result_set_id=result_set_id,
    )
