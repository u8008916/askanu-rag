"""Minimal Day 2 EvidenceBundle construction boundary.

Candidate discovery remains separate and no ranking/evidence optimisation is
implemented here.
"""

from collections.abc import Sequence

from askanu_rag.models import (
    AnswerState,
    EvidenceBundle,
    EvidenceItem,
    MissingEvidence,
    RetrievalPlan,
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
