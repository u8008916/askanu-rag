"""Deterministic V7 Day 1 state transitions and reference resolution.

These functions are the only supported write boundary for validated
``ConversationState``.  They do not retrieve facts and never promote client
state into evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Mapping, Sequence

from askanu_rag.models.conversation_state import (
    MAX_RETAINED_CONSTRAINTS,
    MAX_RETAINED_ENTITIES,
    MAX_RETAINED_RESULT_SETS,
    MAX_RETAINED_STUDENT_FACTS,
    ConstraintLifecycle,
    ConstraintSemanticType,
    ConstraintSet,
    ConversationState,
    Domain,
    EntityKind,
    PendingClarification,
    QueryInterpretation,
    ResolvedEntity,
    ResolvedIntent,
    ResolvedSlot,
    ResultSet,
    ResultSetStatus,
    ScalarValue,
    ScopedConstraint,
    SelectedResult,
    SemanticFocus,
    StateClarificationOption,
    StudentStatedFact,
)


class StateTransitionError(ValueError):
    """A transition would discard or contradict retained semantic state."""


def _replace(state: ConversationState, **updates: object) -> ConversationState:
    values = state.model_dump(mode="python")
    values.update(updates)
    return ConversationState.model_validate(values)


def advance_turn(state: ConversationState) -> ConversationState:
    """Advance the RAG-owned monotonic turn counter by exactly one."""

    return _replace(state, turn_index=state.turn_index + 1)


def canonicalize_conversation_state(
    state: ConversationState,
) -> ConversationState:
    """Ignore client collection order and restore deterministic recency order."""

    entities = tuple(
        sorted(
            state.recent_entities,
            key=lambda item: (
                -item.mentioned_turn,
                item.kind.value,
                item.canonical_id,
            ),
        )
    )
    result_sets = tuple(
        sorted(
            state.result_sets,
            key=lambda item: (
                -item.last_refined_turn,
                -item.created_turn,
                item.result_set_id,
            ),
        )
    )
    constraints = ConstraintSet(
        items=tuple(
            sorted(
                state.constraints.items,
                key=lambda item: (
                    -item.introduced_turn,
                    repr(_constraint_key(item)),
                ),
            )
        )
    )
    facts = tuple(
        sorted(
            state.student_facts,
            key=lambda item: (
                -item.stated_turn,
                item.semantic_type.value,
                item.domain_scope.value if item.domain_scope else "",
            ),
        )
    )
    return _replace(
        state,
        recent_entities=entities,
        result_sets=result_sets,
        constraints=constraints,
        student_facts=facts,
    )


def clear_conversation_state() -> ConversationState:
    """Return the complete structured-state reset used by Clear Chat."""

    return ConversationState()


def set_semantic_focus(
    state: ConversationState, focus: SemanticFocus | None
) -> ConversationState:
    """Set validated focus without changing any retained typed memory."""

    return _replace(state, focus=focus)


def set_constraints(
    state: ConversationState, constraints: ConstraintSet
) -> ConversationState:
    """Replace the validated constraint collection without changing other state."""

    return _replace(state, constraints=constraints)


def remember_entity(
    state: ConversationState,
    entity: ResolvedEntity,
    *,
    focus: bool = True,
) -> ConversationState:
    """Upsert one typed entity and evict the least-recent compatible entries."""

    retained = [
        item
        for item in state.recent_entities
        if (item.kind, item.canonical_id) != (entity.kind, entity.canonical_id)
    ]
    retained.append(entity)
    retained.sort(
        key=lambda item: (-item.mentioned_turn, item.kind.value, item.canonical_id)
    )
    retained = retained[:MAX_RETAINED_ENTITIES]
    updates: dict[str, object] = {"recent_entities": tuple(retained)}
    if focus:
        updates["focus"] = SemanticFocus(
            domain=entity.domain,
            entity_kind=entity.kind,
            canonical_entity_id=entity.canonical_id,
        )
        updates["selected_result"] = None
    return _replace(state, **updates)


def remember_student_fact(
    state: ConversationState, fact: StudentStatedFact
) -> ConversationState:
    """Replace the same scoped user assertion and evict oldest user context."""

    retained = [
        item
        for item in state.student_facts
        if (item.semantic_type, item.domain_scope)
        != (fact.semantic_type, fact.domain_scope)
    ]
    retained.append(fact)
    retained.sort(
        key=lambda item: (
            -item.stated_turn,
            item.semantic_type.value,
            item.domain_scope.value if item.domain_scope else "",
        )
    )
    return _replace(
        state, student_facts=tuple(retained[:MAX_RETAINED_STUDENT_FACTS])
    )


def _constraint_key(constraint: ScopedConstraint) -> tuple[object, ...]:
    scope = constraint.scope
    semantic_type = (
        ConstraintSemanticType.MAX_PRICE
        if constraint.semantic_type
        in {
            ConstraintSemanticType.MAX_PRICE,
            ConstraintSemanticType.MAX_PRICE_EXCLUSIVE,
        }
        else constraint.semantic_type
    )
    return (
        semantic_type,
        scope.domain,
        scope.entity_kind,
        scope.canonical_entity_id,
        scope.intent,
    )


def put_constraint(
    state: ConversationState, constraint: ScopedConstraint
) -> ConversationState:
    """Replace one semantic/scope key; never silently discard another hard rule."""

    key = _constraint_key(constraint)
    retained = [
        item for item in state.constraints.items if _constraint_key(item) != key
    ]
    if len(retained) >= MAX_RETAINED_CONSTRAINTS:
        raise StateTransitionError(
            "constraint limit reached; clarify or explicitly replace a constraint"
        )
    retained.append(constraint)
    retained.sort(
        key=lambda item: (-item.introduced_turn, repr(_constraint_key(item)))
    )
    return _replace(state, constraints=ConstraintSet(items=tuple(retained)))


def constraints_for(
    state: ConversationState,
    *,
    domain: Domain,
    entity_kind: EntityKind | None = None,
    canonical_entity_id: str | None = None,
    intent: str | None = None,
) -> ConstraintSet:
    """Return only constraints compatible with the requested semantic scope."""

    compatible: list[ScopedConstraint] = []
    for constraint in state.constraints.items:
        scope = constraint.scope
        if scope.domain != domain:
            continue
        if scope.entity_kind is not None and scope.entity_kind != entity_kind:
            continue
        if (
            scope.canonical_entity_id is not None
            and scope.canonical_entity_id != canonical_entity_id
        ):
            continue
        if scope.intent is not None and scope.intent != intent:
            continue
        if (
            constraint.lifecycle == ConstraintLifecycle.CURRENT_OPERATION
            and scope.intent != intent
        ):
            continue
        compatible.append(constraint)
    return ConstraintSet(items=tuple(compatible))


def remember_result_set(
    state: ConversationState,
    result_set: ResultSet,
    *,
    focus: bool = True,
) -> ConversationState:
    """Retain six newest typed sets; ordinal order inside each set is immutable."""

    retained = [
        item
        for item in state.result_sets
        if item.result_set_id != result_set.result_set_id
    ]
    retained.append(result_set)
    retained.sort(
        key=lambda item: (
            -item.last_refined_turn,
            -item.created_turn,
            item.result_set_id,
        )
    )
    retained = retained[:MAX_RETAINED_RESULT_SETS]
    updates: dict[str, object] = {"result_sets": tuple(retained)}
    if focus:
        updates["focus"] = SemanticFocus(
            domain=result_set.domain,
            entity_kind=result_set.entity_kind,
            result_set_id=result_set.result_set_id,
            intent_name=result_set.intent.name,
        )
        updates["selected_result"] = None
    return _replace(state, **updates)


def refine_result_set(
    parent: ResultSet,
    *,
    result_set_id: str,
    ordered_canonical_ids: Sequence[str],
    constraints: ConstraintSet,
    status: ResultSetStatus,
    turn: int,
    originating_query: str,
) -> ResultSet:
    """Create a child ResultSet; the original ordered set remains referencable."""

    return ResultSet(
        result_set_id=result_set_id,
        domain=parent.domain,
        entity_kind=parent.entity_kind,
        ordered_canonical_ids=tuple(ordered_canonical_ids),
        originating_query=originating_query,
        intent=parent.intent,
        constraints=constraints,
        created_turn=turn,
        last_refined_turn=turn,
        status=status,
        parent_result_set_id=parent.result_set_id,
    )


@dataclass(frozen=True)
class EntityReferenceResolution:
    entity: ResolvedEntity | None
    precedence: Literal[
        "explicit_entity",
        "explicit_type_or_domain",
        "compatible_focus",
        "compatible_recency",
        "clarification",
    ]
    clarification_required: bool


def _entity_matches(
    entity: ResolvedEntity,
    *,
    kind: EntityKind | None,
    domain: Domain | None,
) -> bool:
    return (kind is None or entity.kind == kind) and (
        domain is None or entity.domain == domain
    )


def resolve_entity_reference(
    state: ConversationState,
    *,
    explicit_entities: Sequence[ResolvedEntity] = (),
    explicit_kind: EntityKind | None = None,
    explicit_domain: Domain | None = None,
) -> EntityReferenceResolution:
    """Apply the frozen explicit > typed > focus > recency > clarify order."""

    explicit = tuple(explicit_entities)
    if len(explicit) == 1:
        return EntityReferenceResolution(explicit[0], "explicit_entity", False)
    if len(explicit) > 1:
        return EntityReferenceResolution(None, "clarification", True)

    retained = tuple(
        sorted(
            state.recent_entities,
            key=lambda item: (
                -item.mentioned_turn,
                item.kind.value,
                item.canonical_id,
            ),
        )
    )
    if explicit_kind is not None or explicit_domain is not None:
        matches = tuple(
            entity
            for entity in retained
            if _entity_matches(
                entity, kind=explicit_kind, domain=explicit_domain
            )
        )
        if matches:
            return EntityReferenceResolution(
                matches[0], "explicit_type_or_domain", False
            )
        return EntityReferenceResolution(None, "clarification", True)

    if state.focus is not None and state.focus.canonical_entity_id is not None:
        for entity in retained:
            if (
                entity.kind == state.focus.entity_kind
                and entity.canonical_id == state.focus.canonical_entity_id
            ):
                return EntityReferenceResolution(
                    entity, "compatible_focus", False
                )
    if retained:
        return EntityReferenceResolution(
            retained[0], "compatible_recency", False
        )
    return EntityReferenceResolution(None, "clarification", True)


@dataclass(frozen=True)
class ResultReferenceResolution:
    result_set: ResultSet | None
    canonical_ids: tuple[str, ...]
    clarification_required: bool


ResultReference = Literal["first", "second", "first_two", "those", "other"]


def resolve_result_reference(
    state: ConversationState,
    reference: ResultReference,
    *,
    entity_kind: EntityKind | None = None,
    domain: Domain | None = None,
) -> ResultReferenceResolution:
    """Resolve ordinals only inside the newest compatible retained ResultSet."""

    compatible = tuple(
        result_set
        for result_set in sorted(
            state.result_sets,
            key=lambda item: (
                -item.last_refined_turn,
                -item.created_turn,
                item.result_set_id,
            ),
        )
        if (entity_kind is None or result_set.entity_kind == entity_kind)
        and (domain is None or result_set.domain == domain)
    )
    if not compatible:
        return ResultReferenceResolution(None, (), True)
    result_set = compatible[0]
    if result_set.status != ResultSetStatus.RESULTS:
        return ResultReferenceResolution(result_set, (), True)
    identities = result_set.ordered_canonical_ids
    if reference == "those":
        return ResultReferenceResolution(result_set, identities, False)
    if reference == "first_two":
        if len(identities) < 2:
            return ResultReferenceResolution(result_set, (), True)
        return ResultReferenceResolution(result_set, identities[:2], False)
    if reference in {"first", "second"}:
        index = 0 if reference == "first" else 1
        if index >= len(identities):
            return ResultReferenceResolution(result_set, (), True)
        return ResultReferenceResolution(result_set, (identities[index],), False)

    selected = state.selected_result
    if selected is None or selected.result_set_id != result_set.result_set_id:
        return ResultReferenceResolution(result_set, (), True)
    others = tuple(
        identity for identity in identities if identity != selected.canonical_id
    )
    if len(others) != 1:
        return ResultReferenceResolution(result_set, (), True)
    return ResultReferenceResolution(result_set, others, False)


def select_result(
    state: ConversationState,
    resolution: ResultReferenceResolution,
) -> ConversationState:
    """Record a single stable ordinal selection after safe resolution."""

    if (
        resolution.clarification_required
        or resolution.result_set is None
        or len(resolution.canonical_ids) != 1
    ):
        raise StateTransitionError("a single resolved result is required")
    canonical_id = resolution.canonical_ids[0]
    ordinal = resolution.result_set.ordered_canonical_ids.index(canonical_id) + 1
    return _replace(
        state,
        selected_result=SelectedResult(
            result_set_id=resolution.result_set.result_set_id,
            canonical_id=canonical_id,
            ordinal=ordinal,
        ),
        focus=SemanticFocus(
            domain=resolution.result_set.domain,
            entity_kind=resolution.result_set.entity_kind,
            result_set_id=resolution.result_set.result_set_id,
            intent_name=resolution.result_set.intent.name,
        ),
    )


class ClarificationAction(str, Enum):
    NO_PENDING = "NO_PENDING"
    STILL_PENDING = "STILL_PENDING"
    RESUMED = "RESUMED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True)
class ClarificationResolution:
    state: ConversationState
    action: ClarificationAction
    intent: ResolvedIntent | None = None
    entities: tuple[ResolvedEntity, ...] = ()
    slots: tuple[ResolvedSlot, ...] = ()
    constraints: ConstraintSet = field(default_factory=ConstraintSet)


def set_pending_clarification(
    state: ConversationState, pending: PendingClarification | None
) -> ConversationState:
    return _replace(state, pending_clarification=pending)


def resolve_pending_clarification(
    state: ConversationState,
    *,
    supplied_slots: Mapping[str, ScalarValue] | None = None,
    explicit_interpretation: QueryInterpretation | None = None,
) -> ClarificationResolution:
    """Resume the saved operation, unless a new explicit request supersedes it."""

    pending = state.pending_clarification
    if explicit_interpretation is not None and explicit_interpretation.explicit_new_request:
        entities = (
            (explicit_interpretation.entity,)
            if explicit_interpretation.entity is not None
            else ()
        )
        return ClarificationResolution(
            _replace(state, pending_clarification=None),
            ClarificationAction.SUPERSEDED,
            explicit_interpretation.intent,
            entities,
            constraints=explicit_interpretation.constraints,
        )
    if pending is None:
        return ClarificationResolution(state, ClarificationAction.NO_PENDING)
    if pending.original_intent is None:
        return ClarificationResolution(state, ClarificationAction.STILL_PENDING)

    supplied = supplied_slots or {}
    existing = {slot.name: slot for slot in pending.resolved_slots}
    for name, value in supplied.items():
        existing[name] = ResolvedSlot(name=name, value=value)
    missing = tuple(name for name in pending.missing_slots if name not in existing)
    if missing:
        updated = pending.model_copy(
            update={
                "resolved_slots": tuple(existing.values()),
                "missing_slots": missing,
            }
        )
        updated = PendingClarification.model_validate(
            updated.model_dump(mode="python")
        )
        return ClarificationResolution(
            _replace(state, pending_clarification=updated),
            ClarificationAction.STILL_PENDING,
        )
    return ClarificationResolution(
        _replace(state, pending_clarification=None),
        ClarificationAction.RESUMED,
        pending.original_intent,
        pending.resolved_entities,
        tuple(existing.values()),
        pending.constraints,
    )


def pending_from_public_clarification(
    *,
    clarification_id: str,
    clarification_type: str,
    options: Sequence[tuple[str, str]],
    allow_multiple: bool,
    turn: int,
) -> PendingClarification:
    """Upgrade a V6 clarification response into bounded V7 state."""

    return PendingClarification(
        id=clarification_id,
        type=clarification_type,
        options=tuple(
            StateClarificationOption(id=identifier, label=label)
            for identifier, label in options
        ),
        allow_multiple=allow_multiple,
        original_intent=ResolvedIntent(
            name="legacy_clarification",
            operation="select_option",
            required_slots=("selection",),
        ),
        missing_slots=("selection",),
        created_turn=turn,
    )
