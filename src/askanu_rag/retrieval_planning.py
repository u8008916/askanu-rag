"""Minimal Day 2 handoff from validated meaning to a retrieval contract."""

from askanu_rag.models import (
    QueryInterpretation,
    RetrievalPlan,
    RetrievalStep,
    RetrievalStrategy,
)


def build_retrieval_plan(
    interpretation: QueryInterpretation,
    *,
    plan_id: str,
    discovery_strategy: RetrievalStrategy = RetrievalStrategy.DETERMINISTIC_DISCOVERY,
) -> RetrievalPlan | None:
    """Describe deterministic filters before an explicitly selected discovery path.

    Day 2 meaning remains the authority for domain, identity and hard
    constraints.  Day 3 may select deterministic, semantic or hybrid discovery
    for measurement without allowing that choice to rewrite the interpretation.
    """

    if interpretation.domain is None or interpretation.intent is None:
        return None
    allowed_discovery = {
        RetrievalStrategy.DETERMINISTIC_DISCOVERY,
        RetrievalStrategy.SEMANTIC_VECTOR,
        RetrievalStrategy.HYBRID,
    }
    if discovery_strategy not in allowed_discovery:
        raise ValueError("discovery strategy must be deterministic, semantic or hybrid")
    steps: list[RetrievalStep] = []
    if interpretation.entity is not None:
        steps.append(
            RetrievalStep(
                strategy=RetrievalStrategy.EXACT_LOOKUP,
                purpose="resolve canonical entity from approved records",
            )
        )
    if interpretation.constraints.items:
        steps.append(
            RetrievalStep(
                strategy=RetrievalStrategy.STRUCTURED_FILTER,
                purpose="apply validated hard constraints",
            )
        )
    discovery_intent = interpretation.intent.name in {"discover", "compare"}
    if discovery_intent or not steps:
        steps.append(
            RetrievalStep(
                strategy=discovery_strategy,
                purpose=(
                    "rank candidates inside the approved filtered population"
                    if steps
                    else "discover candidates inside an approved population"
                ),
            )
        )
    return RetrievalPlan(
        plan_id=plan_id,
        domain=interpretation.domain,
        entity_kind=interpretation.entity.kind if interpretation.entity else None,
        intent=interpretation.intent,
        constraints=interpretation.constraints,
        steps=tuple(steps),
        originating_result_set_id=interpretation.referenced_result_set_id,
    )
