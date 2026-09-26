"""V7 Day 1 executable shared-state and golden-transition contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from askanu_rag.models import (
    AnswerState,
    ConstraintLifecycle,
    ConstraintScope,
    ConstraintSemanticType,
    ConstraintSet,
    ConversationState,
    Domain,
    EntityKind,
    EntityResolutionBasis,
    EvidenceBundle,
    PendingClarification,
    QueryInterpretation,
    ResolvedEntity,
    ResolvedIntent,
    ResultSet,
    ResultSetStatus,
    RetrievalPlan,
    RetrievalStep,
    RetrievalStrategy,
    ScopedConstraint,
    StudentFactType,
    StudentStatedFact,
)
from askanu_rag.models.conversation_state import (
    MAX_RETAINED_CONSTRAINTS,
    MAX_RETAINED_ENTITIES,
    MAX_RETAINED_RESULT_SETS,
    MissingEvidence,
    ResolvedSlot,
    StateClarificationOption,
)
from askanu_rag.state_transitions import (
    ClarificationAction,
    StateTransitionError,
    advance_turn,
    clear_conversation_state,
    constraints_for,
    put_constraint,
    refine_result_set,
    remember_entity,
    remember_result_set,
    remember_student_fact,
    resolve_entity_reference,
    resolve_pending_clarification,
    resolve_result_reference,
    select_result,
    set_pending_clarification,
)


def entity(
    kind: EntityKind,
    canonical_id: str,
    name: str,
    turn: int,
    *,
    basis: EntityResolutionBasis = EntityResolutionBasis.EXPLICIT_IDENTIFIER,
) -> ResolvedEntity:
    domains = {
        EntityKind.COURSE: Domain.COURSES,
        EntityKind.SCHOLARSHIP: Domain.SCHOLARSHIPS,
        EntityKind.JOB: Domain.JOBS,
        EntityKind.RESIDENCE: Domain.ACCOMMODATION,
        EntityKind.EVENT: Domain.EVENTS,
        EntityKind.SUPPORT_SERVICE: Domain.SUPPORT,
    }
    return ResolvedEntity(
        domain=domains[kind],
        kind=kind,
        canonical_id=canonical_id,
        canonical_name=name,
        source_record_id=f"{domains[kind].value}:{kind.value}:{canonical_id}",
        resolution_basis=basis,
        mentioned_turn=turn,
    )


def intent(name: str = "discover") -> ResolvedIntent:
    return ResolvedIntent(name=name, operation=name)


def result_set(
    result_set_id: str,
    domain: Domain,
    kind: EntityKind,
    identities: tuple[str, ...],
    turn: int,
    *,
    status: ResultSetStatus = ResultSetStatus.RESULTS,
    constraints: ConstraintSet | None = None,
) -> ResultSet:
    return ResultSet(
        result_set_id=result_set_id,
        domain=domain,
        entity_kind=kind,
        ordered_canonical_ids=identities,
        originating_query=f"query for {domain.value}",
        intent=intent(),
        constraints=constraints or ConstraintSet(),
        created_turn=turn,
        last_refined_turn=turn,
        status=status,
    )


def at_turn(state: ConversationState, turn: int) -> ConversationState:
    while state.turn_index < turn:
        state = advance_turn(state)
    return state


def scoped_constraint(
    semantic_type: ConstraintSemanticType,
    value: str | int | float | bool,
    domain: Domain,
    turn: int,
    *,
    kind: EntityKind | None = None,
    intent_name: str | None = None,
) -> ScopedConstraint:
    return ScopedConstraint(
        semantic_type=semantic_type,
        value=value,
        scope=ConstraintScope(
            domain=domain,
            entity_kind=kind,
            intent=intent_name,
        ),
        lifecycle=ConstraintLifecycle.UNTIL_REPLACED,
        introduced_turn=turn,
    )


def test_golden_01_exact_course_then_compatible_follow_up() -> None:
    state = at_turn(ConversationState(), 1)
    comp1110 = entity(EntityKind.COURSE, "COMP1110", "Structured Programming", 1)
    state = remember_entity(state, comp1110)

    resolution = resolve_entity_reference(state, explicit_kind=EntityKind.COURSE)

    assert resolution.entity == comp1110
    assert resolution.precedence == "explicit_type_or_domain"


def test_golden_02_course_accommodation_back_to_course_spike() -> None:
    state = at_turn(ConversationState(), 1)
    comp1110 = entity(EntityKind.COURSE, "COMP1110", "Structured Programming", 1)
    state = remember_entity(state, comp1110)
    state = at_turn(state, 2)
    warrumbul = entity(EntityKind.RESIDENCE, "warrumbul-lodge", "Warrumbul Lodge", 2)
    state = remember_entity(state, warrumbul)

    resolution = resolve_entity_reference(state, explicit_kind=EntityKind.COURSE)

    assert {item.kind for item in state.recent_entities} == {
        EntityKind.COURSE,
        EntityKind.RESIDENCE,
    }
    assert resolution.entity == comp1110
    assert resolution.entity != warrumbul


def test_golden_03_accommodation_course_back_to_accommodation() -> None:
    state = at_turn(ConversationState(), 1)
    warrumbul = entity(EntityKind.RESIDENCE, "warrumbul-lodge", "Warrumbul Lodge", 1)
    state = remember_entity(state, warrumbul)
    state = at_turn(state, 2)
    state = remember_entity(
        state, entity(EntityKind.COURSE, "COMP1110", "Structured Programming", 2)
    )

    resolution = resolve_entity_reference(state, explicit_domain=Domain.ACCOMMODATION)

    assert resolution.entity == warrumbul


def test_golden_04_scholarship_result_set_second_is_stable() -> None:
    state = at_turn(ConversationState(), 3)
    scholarships = result_set(
        "rs:scholarships:3",
        Domain.SCHOLARSHIPS,
        EntityKind.SCHOLARSHIP,
        ("scholarship-a", "scholarship-b", "scholarship-c"),
        3,
    )
    state = remember_result_set(state, scholarships)

    resolution = resolve_result_reference(
        state, "second", entity_kind=EntityKind.SCHOLARSHIP
    )

    assert resolution.canonical_ids == ("scholarship-b",)


def test_golden_05_typed_older_result_set_survives_unrelated_newer_set() -> None:
    state = at_turn(ConversationState(), 1)
    older = result_set(
        "rs:scholarships:1",
        Domain.SCHOLARSHIPS,
        EntityKind.SCHOLARSHIP,
        ("scholarship-a", "scholarship-b"),
        1,
    )
    state = remember_result_set(state, older)
    state = at_turn(state, 2)
    state = remember_result_set(
        state,
        result_set(
            "rs:jobs:2",
            Domain.JOBS,
            EntityKind.JOB,
            ("job-1", "job-2"),
            2,
        ),
    )

    resolution = resolve_result_reference(
        state, "second", entity_kind=EntityKind.SCHOLARSHIP
    )

    assert resolution.result_set == older
    assert resolution.canonical_ids == ("scholarship-b",)


def test_golden_06_constraint_inherits_only_inside_compatible_scope() -> None:
    state = at_turn(ConversationState(), 1)
    state = put_constraint(
        state,
        scoped_constraint(
            ConstraintSemanticType.MAX_PRICE,
            400,
            Domain.ACCOMMODATION,
            1,
            kind=EntityKind.RESIDENCE,
        ),
    )

    inherited = constraints_for(
        state, domain=Domain.ACCOMMODATION, entity_kind=EntityKind.RESIDENCE
    )

    assert [(item.semantic_type, item.value) for item in inherited.items] == [
        (ConstraintSemanticType.MAX_PRICE, 400)
    ]


def test_golden_07_explicit_constraint_replaces_conflicting_value() -> None:
    state = at_turn(ConversationState(), 1)
    state = put_constraint(
        state,
        scoped_constraint(
            ConstraintSemanticType.DATE_WINDOW,
            "this_week",
            Domain.JOBS,
            1,
        ),
    )
    state = at_turn(state, 2)
    state = put_constraint(
        state,
        scoped_constraint(
            ConstraintSemanticType.DATE_WINDOW,
            "next_month",
            Domain.JOBS,
            2,
        ),
    )

    assert len(state.constraints.items) == 1
    assert state.constraints.items[0].value == "next_month"


def test_golden_08_constraint_never_leaks_to_unrelated_domain() -> None:
    state = at_turn(ConversationState(), 1)
    state = put_constraint(
        state,
        scoped_constraint(
            ConstraintSemanticType.MAX_PRICE,
            400,
            Domain.ACCOMMODATION,
            1,
        ),
    )

    assert not constraints_for(state, domain=Domain.JOBS).items
    assert not constraints_for(state, domain=Domain.SCHOLARSHIPS).items


def test_golden_09_pending_clarification_resumes_original_operation() -> None:
    state = at_turn(ConversationState(), 1)
    pending_intent = ResolvedIntent(
        name="compare_scholarships",
        operation="compare",
        required_slots=("student_type",),
    )
    pending = PendingClarification(
        id="clar:student-type:1",
        type="missing_slot",
        options=(),
        allow_multiple=False,
        original_intent=pending_intent,
        missing_slots=("student_type",),
        created_turn=1,
    )
    state = set_pending_clarification(state, pending)

    resolution = resolve_pending_clarification(
        state, supplied_slots={"student_type": "international"}
    )

    assert resolution.action == ClarificationAction.RESUMED
    assert resolution.intent == pending_intent
    assert resolution.slots == (
        ResolvedSlot(name="student_type", value="international"),
    )
    assert resolution.state.pending_clarification is None


def test_golden_10_explicit_new_request_supersedes_pending_clarification() -> None:
    state = at_turn(ConversationState(), 1)
    state = set_pending_clarification(
        state,
        PendingClarification(
            id="clar:scholarship:1",
            type="missing_slot",
            options=(),
            allow_multiple=False,
            original_intent=intent("discover_scholarships"),
            missing_slots=("student_type",),
            created_turn=1,
        ),
    )
    state = at_turn(state, 2)
    comp1110 = entity(EntityKind.COURSE, "COMP1110", "Structured Programming", 2)
    explicit = QueryInterpretation(
        domain=Domain.COURSES,
        entity=comp1110,
        intent=intent("course_prerequisites"),
        explicit_new_request=True,
    )

    resolution = resolve_pending_clarification(
        state, explicit_interpretation=explicit
    )

    assert resolution.action == ClarificationAction.SUPERSEDED
    assert resolution.entities == (comp1110,)
    assert resolution.state.pending_clarification is None


def test_golden_11_reference_to_evicted_entity_requires_clarification() -> None:
    state = at_turn(ConversationState(), 1)
    state = remember_entity(
        state, entity(EntityKind.COURSE, "COMP1110", "Structured Programming", 1)
    )
    kinds = (
        EntityKind.RESIDENCE,
        EntityKind.SCHOLARSHIP,
        EntityKind.JOB,
        EntityKind.EVENT,
        EntityKind.SUPPORT_SERVICE,
    )
    for turn in range(2, MAX_RETAINED_ENTITIES + 2):
        state = at_turn(state, turn)
        kind = kinds[(turn - 2) % len(kinds)]
        state = remember_entity(
            state, entity(kind, f"entity-{turn}", f"Entity {turn}", turn)
        )

    resolution = resolve_entity_reference(state, explicit_kind=EntityKind.COURSE)

    assert all(item.canonical_id != "COMP1110" for item in state.recent_entities)
    assert resolution.clarification_required is True
    assert resolution.entity is None


def test_golden_12_clear_chat_removes_every_structured_reference() -> None:
    state = at_turn(ConversationState(), 1)
    state = remember_entity(
        state, entity(EntityKind.RESIDENCE, "warrumbul-lodge", "Warrumbul Lodge", 1)
    )
    state = remember_student_fact(
        state,
        StudentStatedFact(
            semantic_type=StudentFactType.INTERNATIONAL,
            value=True,
            domain_scope=Domain.SCHOLARSHIPS,
            stated_turn=1,
        ),
    )
    state = remember_result_set(
        state,
        result_set(
            "rs:scholarships:1",
            Domain.SCHOLARSHIPS,
            EntityKind.SCHOLARSHIP,
            ("scholarship-a", "scholarship-b"),
            1,
        ),
    )
    state = set_pending_clarification(
        state,
        PendingClarification(
            id="clar:1",
            type="entity_selection",
            options=(StateClarificationOption(id="a", label="A"),),
            allow_multiple=False,
            created_turn=1,
        ),
    )

    cleared = clear_conversation_state()
    stale = resolve_entity_reference(cleared, explicit_kind=EntityKind.RESIDENCE)

    assert cleared == ConversationState()
    assert stale.clarification_required is True


def test_golden_13_explicit_current_entity_overrides_retained_focus() -> None:
    state = at_turn(ConversationState(), 1)
    retained = entity(EntityKind.COURSE, "COMP1110", "Structured Programming", 1)
    state = remember_entity(state, retained)
    state = at_turn(state, 2)
    explicit = entity(EntityKind.COURSE, "COMP2200", "Algorithms", 2)

    resolution = resolve_entity_reference(state, explicit_entities=(explicit,))

    assert resolution.entity == explicit
    assert resolution.precedence == "explicit_entity"


def test_golden_14_empty_and_incomplete_are_distinct_result_states() -> None:
    empty = result_set(
        "rs:empty:1",
        Domain.SCHOLARSHIPS,
        EntityKind.SCHOLARSHIP,
        (),
        1,
        status=ResultSetStatus.EMPTY,
    )
    incomplete = result_set(
        "rs:incomplete:1",
        Domain.SCHOLARSHIPS,
        EntityKind.SCHOLARSHIP,
        (),
        1,
        status=ResultSetStatus.INCOMPLETE,
    )

    assert empty.status == ResultSetStatus.EMPTY
    assert incomplete.status == ResultSetStatus.INCOMPLETE
    assert empty.status != incomplete.status


def test_golden_15_refinement_creates_child_and_preserves_parent_ordinals() -> None:
    parent = result_set(
        "rs:scholarships:1",
        Domain.SCHOLARSHIPS,
        EntityKind.SCHOLARSHIP,
        ("a", "b", "c"),
        1,
    )
    child = refine_result_set(
        parent,
        result_set_id="rs:scholarships:2",
        ordered_canonical_ids=("b", "c"),
        constraints=ConstraintSet(),
        status=ResultSetStatus.RESULTS,
        turn=2,
        originating_query="refined scholarships",
    )

    assert parent.ordered_canonical_ids == ("a", "b", "c")
    assert child.ordered_canonical_ids == ("b", "c")
    assert child.parent_result_set_id == parent.result_set_id


def test_golden_16_other_requires_unambiguous_prior_selection() -> None:
    state = at_turn(ConversationState(), 1)
    state = remember_result_set(
        state,
        result_set(
            "rs:scholarships:1",
            Domain.SCHOLARSHIPS,
            EntityKind.SCHOLARSHIP,
            ("a", "b"),
            1,
        ),
    )
    first = resolve_result_reference(
        state, "first", entity_kind=EntityKind.SCHOLARSHIP
    )
    state = select_result(state, first)

    other = resolve_result_reference(
        state, "other", entity_kind=EntityKind.SCHOLARSHIP
    )

    assert other.canonical_ids == ("b",)
    assert other.clarification_required is False


def test_warrumbul_scholarship_second_back_and_clear_executable_spike() -> None:
    state = at_turn(ConversationState(), 1)
    warrumbul = entity(EntityKind.RESIDENCE, "warrumbul-lodge", "Warrumbul Lodge", 1)
    state = remember_entity(state, warrumbul)
    assert resolve_entity_reference(
        state, explicit_kind=EntityKind.RESIDENCE
    ).entity == warrumbul

    state = at_turn(state, 3)
    state = remember_student_fact(
        state,
        StudentStatedFact(
            semantic_type=StudentFactType.INTERNATIONAL,
            value=True,
            domain_scope=Domain.SCHOLARSHIPS,
            stated_turn=3,
        ),
    )
    state = remember_student_fact(
        state,
        StudentStatedFact(
            semantic_type=StudentFactType.PROGRAM,
            value="Bachelor of Computing",
            domain_scope=Domain.SCHOLARSHIPS,
            stated_turn=3,
        ),
    )
    state = remember_result_set(
        state,
        result_set(
            "rs:scholarships:3",
            Domain.SCHOLARSHIPS,
            EntityKind.SCHOLARSHIP,
            ("scholarship-a", "scholarship-b"),
            3,
        ),
    )
    second = resolve_result_reference(
        state, "second", entity_kind=EntityKind.SCHOLARSHIP
    )
    state = select_result(state, second)
    assert state.selected_result is not None
    assert state.selected_result.canonical_id == "scholarship-b"

    back = resolve_entity_reference(state, explicit_domain=Domain.ACCOMMODATION)
    assert back.entity == warrumbul

    cleared = clear_conversation_state()
    after_clear = resolve_entity_reference(
        cleared, explicit_kind=EntityKind.RESIDENCE
    )
    assert after_clear.clarification_required is True


def test_canonical_twenty_turn_journey_retains_typed_meaning_beyond_history() -> None:
    state = ConversationState()
    comp1110 = None
    warrumbul = None
    for turn in range(1, 21):
        state = advance_turn(state)
        if turn == 1:
            comp1110 = entity(
                EntityKind.COURSE, "COMP1110", "Structured Programming", turn
            )
            state = remember_entity(state, comp1110)
        elif turn == 2:
            warrumbul = entity(
                EntityKind.RESIDENCE,
                "warrumbul-lodge",
                "Warrumbul Lodge",
                turn,
            )
            state = remember_entity(state, warrumbul)
        elif turn in {5, 9, 13, 17}:
            state = remember_result_set(
                state,
                result_set(
                    f"rs:scholarships:{turn}",
                    Domain.SCHOLARSHIPS,
                    EntityKind.SCHOLARSHIP,
                    (f"scholarship-{turn}-a", f"scholarship-{turn}-b"),
                    turn,
                ),
            )

    assert state.turn_index == 20
    assert resolve_entity_reference(
        state, explicit_kind=EntityKind.COURSE
    ).entity == comp1110
    assert resolve_entity_reference(
        state, explicit_kind=EntityKind.RESIDENCE
    ).entity == warrumbul


def test_result_set_eviction_is_deterministic_and_old_reference_clarifies() -> None:
    state = ConversationState()
    for turn in range(1, MAX_RETAINED_RESULT_SETS + 2):
        state = advance_turn(state)
        state = remember_result_set(
            state,
            result_set(
                f"rs:jobs:{turn}",
                Domain.JOBS,
                EntityKind.JOB,
                (f"job-{turn}-a", f"job-{turn}-b"),
                turn,
            ),
        )

    assert len(state.result_sets) == MAX_RETAINED_RESULT_SETS
    assert all(item.result_set_id != "rs:jobs:1" for item in state.result_sets)
    assert resolve_result_reference(
        clear_conversation_state(), "first", entity_kind=EntityKind.JOB
    ).clarification_required


def test_constraint_limit_refuses_silent_hard_constraint_eviction() -> None:
    state = at_turn(ConversationState(), 1)
    # Inclusive and exclusive price bounds are one replacement family, so use
    # only one representative while filling distinct hard-constraint slots.
    semantic_types = tuple(
        item
        for item in ConstraintSemanticType
        if item != ConstraintSemanticType.MAX_PRICE_EXCLUSIVE
    )
    for index in range(MAX_RETAINED_CONSTRAINTS):
        semantic = semantic_types[index % len(semantic_types)]
        domain = tuple(Domain)[index // len(semantic_types)]
        state = put_constraint(
            state,
            scoped_constraint(semantic, f"value-{index}", domain, 1),
        )

    with pytest.raises(StateTransitionError, match="constraint limit reached"):
        put_constraint(
            state,
            scoped_constraint(
                ConstraintSemanticType.MAX_PRICE,
                999,
                Domain.EVENTS,
                1,
                kind=EntityKind.EVENT,
            ),
        )


def test_exclusive_price_bound_replaces_inclusive_bound_in_shared_state() -> None:
    state = at_turn(ConversationState(), 1)
    state = put_constraint(
        state,
        scoped_constraint(
            ConstraintSemanticType.MAX_PRICE,
            450,
            Domain.ACCOMMODATION,
            1,
        ),
    )
    state = at_turn(state, 2)
    state = put_constraint(
        state,
        scoped_constraint(
            ConstraintSemanticType.MAX_PRICE_EXCLUSIVE,
            400,
            Domain.ACCOMMODATION,
            2,
        ),
    )

    assert [
        (item.semantic_type, item.value) for item in state.constraints.items
    ] == [(ConstraintSemanticType.MAX_PRICE_EXCLUSIVE, 400)]

def test_state_is_context_not_institutional_evidence() -> None:
    fact = StudentStatedFact(
        semantic_type=StudentFactType.INTERNATIONAL,
        value=True,
        domain_scope=Domain.SCHOLARSHIPS,
        stated_turn=1,
    )
    assert fact.authority == "user_stated"
    with pytest.raises(ValidationError):
        EvidenceBundle.model_validate(
            {
                "bundle_id": "bundle:1",
                "plan_id": "plan:1",
                "selected_evidence": [fact.model_dump(mode="json")],
                "missing_evidence": [],
                "answer_state": "CONFIRMED",
            }
        )


def test_unknown_answer_state_requires_explicit_missing_evidence() -> None:
    with pytest.raises(ValidationError, match="UNKNOWN requires"):
        EvidenceBundle(
            bundle_id="bundle:1",
            plan_id="plan:1",
            answer_state=AnswerState.UNKNOWN,
        )
    bundle = EvidenceBundle(
        bundle_id="bundle:1",
        plan_id="plan:1",
        missing_evidence=(MissingEvidence(field="vacancy", reason="null"),),
        answer_state=AnswerState.UNKNOWN,
    )
    assert bundle.answer_state == AnswerState.UNKNOWN


def test_retrieval_plan_separates_candidates_from_evidence_selection() -> None:
    plan = RetrievalPlan(
        plan_id="plan:course:1",
        domain=Domain.COURSES,
        entity_kind=EntityKind.COURSE,
        intent=intent("course_prerequisites"),
        steps=(
            RetrievalStep(strategy=RetrievalStrategy.EXACT_LOOKUP, purpose="identity"),
            RetrievalStep(
                strategy=RetrievalStrategy.SEMANTIC_VECTOR,
                purpose="candidate discovery",
            ),
        ),
    )
    assert plan.evidence_selection_required is True
    with pytest.raises(ValidationError, match="authoritative retrieval must precede"):
        RetrievalPlan(
            plan_id="plan:bad:1",
            domain=Domain.COURSES,
            intent=intent(),
            steps=(
                RetrievalStep(
                    strategy=RetrievalStrategy.SEMANTIC_VECTOR,
                    purpose="discovery",
                ),
                RetrievalStep(
                    strategy=RetrievalStrategy.EXACT_LOOKUP,
                    purpose="identity",
                ),
            ),
        )
