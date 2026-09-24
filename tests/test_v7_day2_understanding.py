"""V7 Day 2 deterministic context and understanding acceptance."""

from askanu_rag.conversation_orchestrator import orchestrate_turn
from askanu_rag.evidence_selection import build_evidence_bundle
from askanu_rag.models import (
    AnswerState,
    ConstraintSemanticType,
    ConversationState,
    Domain,
    EntityKind,
    EntityResolutionBasis,
    MissingEvidence,
    PendingClarification,
    ResolvedEntity,
    ResolvedIntent,
    ResultSet,
    ResultSetStatus,
    StudentFactType,
)
from askanu_rag.retrieval_planning import build_retrieval_plan
from askanu_rag.state_transitions import (
    advance_turn,
    clear_conversation_state,
    remember_entity,
    remember_result_set,
    set_pending_clarification,
)


def values(state: ConversationState, domain: Domain) -> dict[ConstraintSemanticType, object]:
    return {
        item.semantic_type: item.value
        for item in state.constraints.items
        if item.scope.domain == domain
    }


def test_external_v1_legacy_temporal_value_still_round_trips() -> None:
    state = ConversationState.model_validate(
        {
            "schema_version": 1,
            "turn_index": 1,
            "constraints": {
                "items": [
                    {
                        "semantic_type": "temporal_window",
                        "value": "today",
                        "scope": {"domain": "events"},
                        "lifecycle": "until_replaced",
                        "introduced_turn": 1,
                    }
                ]
            },
        }
    )

    dumped = state.model_dump(mode="json")
    assert dumped["constraints"]["items"][0]["semantic_type"] == "temporal_window"

    interpreted = orchestrate_turn("events tomorrow", (), ConversationState())
    assert {
        item.semantic_type for item in interpreted.interpretation.explicit_constraints.items
    } == {ConstraintSemanticType.DATE_WINDOW}


def retained_entity(kind: EntityKind, identifier: str, name: str, turn: int) -> ResolvedEntity:
    domain = {
        EntityKind.COURSE: Domain.COURSES,
        EntityKind.RESIDENCE: Domain.ACCOMMODATION,
        EntityKind.SCHOLARSHIP: Domain.SCHOLARSHIPS,
        EntityKind.EVENT: Domain.EVENTS,
    }[kind]
    return ResolvedEntity(
        domain=domain,
        kind=kind,
        canonical_id=identifier,
        canonical_name=name,
        resolution_basis=EntityResolutionBasis.EXPLICIT_IDENTIFIER,
        mentioned_turn=turn,
    )


def scholarship_results(turn: int = 1) -> ResultSet:
    return ResultSet(
        result_set_id="rs:scholarships:stable",
        domain=Domain.SCHOLARSHIPS,
        entity_kind=EntityKind.SCHOLARSHIP,
        ordered_canonical_ids=("scholarship-a", "scholarship-b", "scholarship-c"),
        originating_query="show scholarships",
        intent=ResolvedIntent(name="discover", operation="initial_discovery"),
        created_turn=turn,
        last_refined_turn=turn,
        status=ResultSetStatus.RESULTS,
    )


def event_results(turn: int = 1) -> ResultSet:
    return ResultSet(
        result_set_id="rs:events:today",
        domain=Domain.EVENTS,
        entity_kind=EntityKind.EVENT,
        ordered_canonical_ids=("event-a", "event-b", "event-c"),
        originating_query="events today",
        intent=ResolvedIntent(name="discover", operation="initial_discovery"),
        created_turn=turn,
        last_refined_turn=turn,
        status=ResultSetStatus.RESULTS,
    )


def test_temporal_date_and_time_refine_independently() -> None:
    state = ConversationState()
    first = orchestrate_turn("What events are on today?", (), state)
    second = orchestrate_turn("Only after 5pm", (), first.state)
    third = orchestrate_turn("Actually tomorrow", (), second.state)

    assert first.interpretation.intent.operation == "initial_discovery"
    assert second.interpretation.intent.operation == "refine_results"
    assert third.interpretation.intent.operation == "refine_results"
    assert values(third.state, Domain.EVENTS) == {
        ConstraintSemanticType.DATE_WINDOW: "tomorrow",
        ConstraintSemanticType.TIME_OF_DAY_WINDOW: "after 17:00",
    }
    assert third.interpretation.replaced_constraint_types == (
        ConstraintSemanticType.DATE_WINDOW,
    )
    assert third.interpretation.surviving_constraint_types == (
        ConstraintSemanticType.TIME_OF_DAY_WINDOW,
    )


def test_temporal_time_override_preserves_date() -> None:
    state = orchestrate_turn("events today", (), ConversationState()).state
    state = orchestrate_turn("after 5pm", (), state).state
    final = orchestrate_turn("before 2pm", (), state)

    assert values(final.state, Domain.EVENTS) == {
        ConstraintSemanticType.DATE_WINDOW: "today",
        ConstraintSemanticType.TIME_OF_DAY_WINDOW: "before 14:00",
    }


def test_event_constraints_do_not_leak_to_courses_and_restore_on_return() -> None:
    state = orchestrate_turn("events today", (), ConversationState()).state
    state = orchestrate_turn("after 5pm", (), state).state
    course = orchestrate_turn("Tell me about COMP1110", (), state)
    assert course.interpretation.domain == Domain.COURSES
    assert course.interpretation.constraints.items == ()

    returned = orchestrate_turn("back to the events", (), course.state)
    assert returned.interpretation.domain == Domain.EVENTS
    assert values(returned.state, Domain.EVENTS) == {
        ConstraintSemanticType.DATE_WINDOW: "today",
        ConstraintSemanticType.TIME_OF_DAY_WINDOW: "after 17:00",
    }


def test_course_alias_followups_and_explicit_override() -> None:
    state = orchestrate_turn("Tell me about Structured Programming", (), ConversationState()).state
    prereq = orchestrate_turn("What are its prerequisites?", (), state)
    units = orchestrate_turn("How many units is it?", (), prereq.state)
    override = orchestrate_turn("Actually, what about COMP2120?", (), units.state)
    final = orchestrate_turn("What are its prerequisites?", (), override.state)

    assert prereq.interpretation.entity.canonical_id == "COMP1110"
    assert units.interpretation.entity.canonical_id == "COMP1110"
    assert override.interpretation.entity.canonical_id == "COMP2120"
    assert final.interpretation.entity.canonical_id == "COMP2120"


def test_safe_alias_variants_include_spacing_case_and_bounded_typo() -> None:
    spaced = orchestrate_turn("tell me about comp 1110", (), ConversationState())
    typo = orchestrate_turn("Tell me about Structurd Programming", (), ConversationState())
    assert spaced.interpretation.entity.canonical_id == "COMP1110"
    assert typo.interpretation.entity.canonical_id == "COMP1110"


def test_accommodation_continuity_and_vacancy_remains_meaning_only() -> None:
    state = orchestrate_turn("Tell me about Warrumbul", (), ConversationState()).state
    for question in ("Is it catered?", "How much does it cost?", "How do I apply?", "Are rooms available?"):
        turn = orchestrate_turn(question, (), state)
        assert turn.interpretation.entity.canonical_id == "warrumbul-lodge"
        assert turn.interpretation.domain == Domain.ACCOMMODATION
        state = turn.state
    assert all(not hasattr(entity, "vacancy") for entity in state.recent_entities)


def test_scholarship_second_one_is_stable_across_followup() -> None:
    state = advance_turn(ConversationState())
    state = remember_result_set(state, scholarship_results())
    selected = orchestrate_turn("What about the second scholarship?", (), state)
    followup = orchestrate_turn("When does it close?", (), selected.state)

    assert selected.selected_canonical_ids == ("scholarship-b",)
    assert selected.state.selected_result.canonical_id == "scholarship-b"
    assert followup.interpretation.entity.canonical_id == "scholarship-b"


def test_typed_older_scholarship_set_outranks_newer_unrelated_set() -> None:
    state = advance_turn(ConversationState())
    state = remember_result_set(state, scholarship_results())
    state = remember_result_set(state, event_results())
    selected = orchestrate_turn("Tell me about the second scholarship", (), state)
    assert selected.selected_canonical_ids == ("scholarship-b",)
    assert selected.interpretation.referenced_result_set_id == "rs:scholarships:stable"


def test_continue_results_preserves_originating_population() -> None:
    state = advance_turn(ConversationState())
    state = remember_result_set(state, event_results())
    turn = orchestrate_turn("Any more?", (), state)
    plan = build_retrieval_plan(turn.interpretation, plan_id="plan:continue")

    assert turn.interpretation.intent.name == "discover"
    assert turn.interpretation.intent.operation == "continue_results"
    assert turn.interpretation.reference_origin == "prior_result_set"
    assert plan.originating_result_set_id == "rs:events:today"


def test_cross_domain_return_recovers_compatible_course() -> None:
    state = orchestrate_turn("COMP1110", (), ConversationState()).state
    state = orchestrate_turn("Tell me about Warrumbul", (), state).state
    turn = orchestrate_turn("Back to the course, how many units is it?", (), state)
    assert turn.interpretation.domain == Domain.COURSES
    assert turn.interpretation.entity.canonical_id == "COMP1110"
    assert turn.interpretation.intent.operation == "return_topic"


def test_explicit_correction_replaces_current_entity_focus() -> None:
    state = orchestrate_turn("Tell me about Warrumbul", (), ConversationState()).state
    corrected = orchestrate_turn("Actually, I meant Bruce Hall", (), state)
    followup = orchestrate_turn("Where is it?", (), corrected.state)
    assert corrected.interpretation.entity.canonical_id == "bruce-hall"
    assert followup.interpretation.entity.canonical_id == "bruce-hall"


def test_ten_turn_cross_domain_understanding_journey() -> None:
    questions = (
        "Structured Programming",
        "What are its prerequisites?",
        "Tell me about Warrumbul",
        "Is it catered?",
        "What events are on today?",
        "Only after 5pm",
        "Back to the course",
        "How many units is it?",
        "Back to the events",
        "Actually tomorrow",
    )
    state = ConversationState()
    turns = []
    for question in questions:
        turn = orchestrate_turn(question, (), state)
        turns.append(turn)
        state = turn.state

    assert state.turn_index == 10
    assert turns[6].interpretation.entity.canonical_id == "COMP1110"
    assert turns[7].interpretation.entity.canonical_id == "COMP1110"
    assert values(state, Domain.EVENTS) == {
        ConstraintSemanticType.DATE_WINDOW: "tomorrow",
        ConstraintSemanticType.TIME_OF_DAY_WINDOW: "after 17:00",
    }


def test_explicit_request_interrupts_pending_clarification() -> None:
    state = advance_turn(ConversationState())
    state = set_pending_clarification(
        state,
        PendingClarification(
            id="clar:course",
            type="entity_selection",
            options=(),
            allow_multiple=False,
            original_intent=ResolvedIntent(name="lookup", operation="lookup"),
            missing_slots=("selection",),
            created_turn=1,
        ),
    )
    turn = orchestrate_turn("Actually, tell me about Warrumbul Lodge", (), state)
    assert turn.clarification_action.value == "SUPERSEDED"
    assert turn.state.pending_clarification is None
    assert turn.interpretation.entity.canonical_id == "warrumbul-lodge"


def test_clarification_yes_resumes_original_intent() -> None:
    course = retained_entity(EntityKind.COURSE, "COMP1110", "Structured Programming", 1)
    state = advance_turn(ConversationState())
    state = set_pending_clarification(
        state,
        PendingClarification(
            id="clar:confirm",
            type="confirmation",
            options=(),
            allow_multiple=False,
            original_intent=ResolvedIntent(name="lookup", operation="lookup", required_slots=("selection",)),
            resolved_entities=(course,),
            missing_slots=("selection",),
            created_turn=1,
        ),
    )
    turn = orchestrate_turn("Yes", (), state)
    assert turn.clarification_action.value == "RESUMED"
    assert turn.interpretation.intent.name == "lookup"
    assert turn.interpretation.entity.canonical_id == "COMP1110"


def test_clear_chat_and_evicted_result_reference_clarify() -> None:
    state = advance_turn(ConversationState())
    state = remember_result_set(state, scholarship_results())
    cleared = orchestrate_turn("Clear Chat", (), state)
    unresolved = orchestrate_turn("Where is the second one?", (), cleared.state)
    assert cleared.state == clear_conversation_state()
    assert unresolved.interpretation.requires_clarification is True
    assert unresolved.interpretation.ambiguity == "missing_reference"


def test_user_stated_context_is_bounded_and_marked_user_stated() -> None:
    turn = orchestrate_turn(
        "I'm an international Bachelor of Computing student.", (), ConversationState()
    )
    assert {fact.semantic_type for fact in turn.state.student_facts} == {
        StudentFactType.INTERNATIONAL,
        StudentFactType.PROGRAM,
    }
    assert {fact.authority for fact in turn.state.student_facts} == {"user_stated"}
    assert next(
        fact.value
        for fact in turn.state.student_facts
        if fact.semantic_type == StudentFactType.PROGRAM
    ) == "Bachelor Of Computing"


def test_retrieval_plan_is_contract_only_and_authoritative_first() -> None:
    turn = orchestrate_turn("Tell me about COMP1110", (), ConversationState())
    plan = build_retrieval_plan(turn.interpretation, plan_id="plan:course")
    assert [step.strategy.value for step in plan.steps] == ["exact_lookup"]
    assert plan.evidence_selection_required is True


def test_resolved_vacancy_meaning_does_not_become_factual_evidence() -> None:
    state = orchestrate_turn("Tell me about Warrumbul", (), ConversationState()).state
    turn = orchestrate_turn("Are rooms available?", (), state)
    plan = build_retrieval_plan(turn.interpretation, plan_id="plan:vacancy")
    assert plan is not None

    bundle = build_evidence_bundle(
        plan,
        bundle_id="evidence:vacancy",
        missing_evidence=(
            MissingEvidence(field="live_vacancy", reason="not_retrieved"),
        ),
        answer_state=AnswerState.UNKNOWN,
    )

    assert turn.interpretation.entity.canonical_id == "warrumbul-lodge"
    assert bundle.selected_evidence == ()
    assert bundle.answer_state == AnswerState.UNKNOWN
