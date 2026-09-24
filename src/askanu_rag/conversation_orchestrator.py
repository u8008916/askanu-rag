"""V7 Day 2 deterministic interpretation-to-state orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from askanu_rag.domain_resolution import (
    DEFAULT_PROBLEM_DOMAIN_RESOLVER,
    ProblemDomainResolver,
)
from askanu_rag.entity_resolution import (
    DEFAULT_ENTITY_CATALOGUE,
    DEFAULT_SAFE_ENTITY_ALIASES,
    EntityCatalogue,
    SafeEntityAlias,
)
from askanu_rag.interpretation import (
    extract_student_facts,
    interpret_turn,
    result_reference_for,
)
from askanu_rag.models import (
    ConversationState,
    PendingClarification,
    QueryInterpretation,
    SemanticFocus,
)
from askanu_rag.models.contracts import HistoryTurn
from askanu_rag.state_transitions import (
    ClarificationAction,
    advance_turn,
    canonicalize_conversation_state,
    clear_conversation_state,
    put_constraint,
    remember_entity,
    remember_student_fact,
    resolve_pending_clarification,
    resolve_result_reference,
    select_result,
    set_constraints,
    set_pending_clarification,
    set_semantic_focus,
)
from askanu_rag.temporal_compatibility import (
    normalise_legacy_temporal_constraints,
)


@dataclass(frozen=True)
class ConversationTurn:
    interpretation: QueryInterpretation
    state: ConversationState
    clarification_action: ClarificationAction
    selected_canonical_ids: tuple[str, ...] = ()


def _clarification_for(
    interpretation: QueryInterpretation, turn: int
) -> PendingClarification:
    intent = interpretation.intent
    return PendingClarification(
        id=f"clar:v7:{turn}",
        type="reference_resolution",
        options=(),
        allow_multiple=False,
        original_intent=intent,
        resolved_entities=(interpretation.entity,) if interpretation.entity else (),
        missing_slots=interpretation.missing_slots or ("reference",),
        constraints=interpretation.constraints,
        created_turn=turn,
    )


def orchestrate_turn(
    question: str,
    history: Sequence[HistoryTurn],
    state: ConversationState,
    *,
    entity_catalogue: EntityCatalogue = DEFAULT_ENTITY_CATALOGUE,
    entity_aliases: Sequence[SafeEntityAlias] = DEFAULT_SAFE_ENTITY_ALIASES,
    problem_domain_resolver: ProblemDomainResolver = DEFAULT_PROBLEM_DOMAIN_RESOLVER,
) -> ConversationTurn:
    """Validate, interpret and deterministically update one conversational turn."""

    if question.casefold().strip() == "clear chat":
        empty = clear_conversation_state()
        interpretation = QueryInterpretation(
            intent=None,
            explicit_new_request=True,
        )
        return ConversationTurn(
            interpretation=interpretation,
            state=empty,
            clarification_action=ClarificationAction.SUPERSEDED,
        )

    updated = advance_turn(canonicalize_conversation_state(state))
    interpretation = interpret_turn(
        question,
        history,
        updated,
        entity_catalogue=entity_catalogue,
        entity_aliases=entity_aliases,
        problem_domain_resolver=problem_domain_resolver,
    )
    temporal_normalisation = normalise_legacy_temporal_constraints(
        updated.constraints,
        interpretation.explicit_constraints,
    )
    if temporal_normalisation.removed_legacy:
        updated = set_constraints(updated, temporal_normalisation.constraints)
    action = ClarificationAction.NO_PENDING

    if updated.pending_clarification is not None:
        if interpretation.intent and interpretation.intent.name == "clarification_response":
            normalised = question.casefold().strip()
            supplied: dict[str, object] = {}
            if normalised in {"yes", "first", "second", "both"}:
                supplied["selection"] = normalised
                supplied["reference"] = normalised
            resolution = resolve_pending_clarification(updated, supplied_slots=supplied)
            updated = resolution.state
            action = resolution.action
            if resolution.action == ClarificationAction.RESUMED:
                interpretation = interpretation.model_copy(
                    update={
                        "intent": resolution.intent,
                        "entity": resolution.entities[0] if resolution.entities else None,
                        "entity_origin": "retained_state" if resolution.entities else "none",
                        "reference_origin": "pending_clarification",
                    }
                )
        elif interpretation.explicit_new_request:
            resolution = resolve_pending_clarification(
                updated, explicit_interpretation=interpretation
            )
            updated = resolution.state
            action = resolution.action

    if interpretation.entity is not None:
        updated = remember_entity(updated, interpretation.entity)

    selected: tuple[str, ...] = ()
    reference = result_reference_for(question)
    if reference is not None and interpretation.reference_origin == "prior_result_set":
        resolution = resolve_result_reference(
            updated,
            reference,  # type: ignore[arg-type]
            entity_kind=interpretation.entity.kind if interpretation.entity else None,
            domain=interpretation.domain,
        )
        selected = resolution.canonical_ids
        if len(selected) == 1:
            updated = select_result(updated, resolution)

    for constraint in interpretation.explicit_constraints.items:
        updated = put_constraint(updated, constraint)
    for fact in extract_student_facts(question, updated.turn_index):
        updated = remember_student_fact(updated, fact)

    if interpretation.requires_clarification:
        updated = set_pending_clarification(
            updated, _clarification_for(interpretation, updated.turn_index)
        )
        action = ClarificationAction.STILL_PENDING
    elif interpretation.domain is not None and interpretation.entity is None and reference is None:
        updated = set_semantic_focus(
            updated,
            SemanticFocus(
                domain=interpretation.domain,
                intent_name=interpretation.intent.name if interpretation.intent else None,
            ),
        )

    return ConversationTurn(
        interpretation=interpretation,
        state=updated,
        clarification_action=action,
        selected_canonical_ids=selected,
    )
