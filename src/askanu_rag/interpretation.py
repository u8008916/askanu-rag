"""Deterministic V7 Day 2 turn interpretation.

This module resolves conversational meaning only.  It neither retrieves nor
asserts institutional facts, and every output validates against the shared Day
1/Day 2 contracts.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from askanu_rag.models import (
    ConstraintLifecycle,
    ConstraintScope,
    ConstraintSemanticType,
    ConstraintSet,
    ConversationState,
    Domain,
    EntityKind,
    EntityResolutionBasis,
    QueryInterpretation,
    ResolvedEntity,
    ResolvedIntent,
    ResultSetStatus,
    ScopedConstraint,
    StudentFactType,
    StudentStatedFact,
)
from askanu_rag.models.contracts import HistoryTurn
from askanu_rag.state_transitions import (
    constraints_for,
    resolve_entity_reference,
    resolve_result_reference,
)

_SPACE_RE = re.compile(r"\s+")
_COURSE_CODE_RE = re.compile(r"\bCOMP\s*(\d{4}[A-Z]?)\b", re.IGNORECASE)
_PRICE_RE = re.compile(r"(?:under|below|less than|max(?:imum)?(?: of)?|<)\s*\$?\s*(\d{2,6})", re.IGNORECASE)
_AFTER_RE = re.compile(r"\bafter\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_BEFORE_RE = re.compile(r"\bbefore\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_BETWEEN_RE = re.compile(
    r"\bbetween\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+and\s+"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
)

_ALIASES: tuple[tuple[tuple[str, ...], Domain, EntityKind, str, str], ...] = (
    (
        ("structured programming", "structurd programming", "structured programing"),
        Domain.COURSES,
        EntityKind.COURSE,
        "COMP1110",
        "Structured Programming",
    ),
    (
        ("warrumbul lodge", "warrumbul"),
        Domain.ACCOMMODATION,
        EntityKind.RESIDENCE,
        "warrumbul-lodge",
        "Warrumbul Lodge",
    ),
    (
        ("bruce hall",),
        Domain.ACCOMMODATION,
        EntityKind.RESIDENCE,
        "bruce-hall",
        "Bruce Hall",
    ),
)

_TYPED_REFERENCES: tuple[tuple[tuple[str, ...], Domain, EntityKind], ...] = (
    (("course",), Domain.COURSES, EntityKind.COURSE),
    (("residence", "accommodation"), Domain.ACCOMMODATION, EntityKind.RESIDENCE),
    (("scholarship",), Domain.SCHOLARSHIPS, EntityKind.SCHOLARSHIP),
    (("job",), Domain.JOBS, EntityKind.JOB),
    (("event",), Domain.EVENTS, EntityKind.EVENT),
    (("service", "support"), Domain.SUPPORT, EntityKind.SUPPORT_SERVICE),
)


def _normalise(value: str) -> str:
    return _SPACE_RE.sub(" ", value.casefold().strip())


def _entity(
    *, domain: Domain, kind: EntityKind, canonical_id: str, name: str, turn: int,
    basis: EntityResolutionBasis,
) -> ResolvedEntity:
    return ResolvedEntity(
        domain=domain,
        kind=kind,
        canonical_id=canonical_id,
        canonical_name=name,
        resolution_basis=basis,
        mentioned_turn=turn,
    )


def _explicit_entity(question: str, turn: int) -> ResolvedEntity | None:
    code = _COURSE_CODE_RE.search(question)
    if code:
        canonical = f"COMP{code.group(1).upper()}"
        return _entity(
            domain=Domain.COURSES,
            kind=EntityKind.COURSE,
            canonical_id=canonical,
            name=canonical,
            turn=turn,
            basis=EntityResolutionBasis.EXPLICIT_IDENTIFIER,
        )
    normalised = _normalise(question)
    for aliases, domain, kind, canonical_id, name in _ALIASES:
        if any(alias in normalised for alias in aliases):
            return _entity(
                domain=domain,
                kind=kind,
                canonical_id=canonical_id,
                name=name,
                turn=turn,
                basis=EntityResolutionBasis.SAFE_ALIAS,
            )
    return None


def _typed_reference(question: str) -> tuple[Domain, EntityKind] | None:
    normalised = _normalise(question)
    for words, domain, kind in _TYPED_REFERENCES:
        for word in words:
            if any(
                re.search(pattern, normalised)
                for pattern in (
                    rf"\b(?:the|that|this|first|second)\s+{re.escape(word)}\b",
                    rf"\bback to (?:the )?{re.escape(word)}s?\b",
                )
            ):
                return domain, kind
    return None


def _domain_from_words(question: str) -> Domain | None:
    normalised = _normalise(question)
    mapping = (
        (("course", "prerequisite", "units"), Domain.COURSES),
        (("scholarship",), Domain.SCHOLARSHIPS),
        (("job", "role"), Domain.JOBS),
        (("accommodation", "residence", "hall", "lodge", "catered", "vacancy", "rooms available"), Domain.ACCOMMODATION),
        (("event",), Domain.EVENTS),
        (("support", "service"), Domain.SUPPORT),
    )
    for words, domain in mapping:
        if any(word in normalised for word in words):
            return domain
    return None


def _is_domain_return(question: str) -> bool:
    return bool(
        re.search(
            r"\bback to (?:the )?(?:courses|scholarships|jobs|events|services|"
            r"residences|accommodation|support)\b",
            _normalise(question),
        )
    )


def _clock(hour: str, minute: str | None, meridiem: str | None) -> str:
    value = int(hour)
    if meridiem and meridiem.casefold() == "pm" and value != 12:
        value += 12
    if meridiem and meridiem.casefold() == "am" and value == 12:
        value = 0
    return f"{value:02d}:{int(minute or 0):02d}"


def _explicit_constraints(question: str, domain: Domain | None, turn: int) -> ConstraintSet:
    if domain is None:
        return ConstraintSet()
    normalised = _normalise(question)
    found: list[ScopedConstraint] = []

    price = _PRICE_RE.search(question)
    if price:
        found.append(ScopedConstraint(
            semantic_type=ConstraintSemanticType.MAX_PRICE,
            value=int(price.group(1)),
            scope=ConstraintScope(domain=domain),
            lifecycle=ConstraintLifecycle.UNTIL_REPLACED,
            introduced_turn=turn,
        ))

    date_value = next((value for value in ("today", "tomorrow", "this friday", "next week", "this weekend") if value in normalised), None)
    if date_value:
        found.append(ScopedConstraint(
            semantic_type=ConstraintSemanticType.DATE_WINDOW,
            value=date_value,
            scope=ConstraintScope(domain=domain),
            lifecycle=ConstraintLifecycle.UNTIL_REPLACED,
            introduced_turn=turn,
        ))

    between = _BETWEEN_RE.search(question)
    after = _AFTER_RE.search(question)
    before = _BEFORE_RE.search(question)
    time_value: str | None = None
    if between:
        time_value = f"between {_clock(*between.groups()[:3])} and {_clock(*between.groups()[3:])}"
    elif after:
        time_value = f"after {_clock(*after.groups())}"
    elif before:
        time_value = f"before {_clock(*before.groups())}"
    elif "evening" in normalised:
        time_value = "evening"
    if time_value:
        found.append(ScopedConstraint(
            semantic_type=ConstraintSemanticType.TIME_OF_DAY_WINDOW,
            value=time_value,
            scope=ConstraintScope(domain=domain),
            lifecycle=ConstraintLifecycle.UNTIL_REPLACED,
            introduced_turn=turn,
        ))
    return ConstraintSet(items=tuple(found))


def _merge_constraints(
    explicit: ConstraintSet,
    inherited: ConstraintSet,
) -> tuple[
    ConstraintSet,
    tuple[ConstraintSemanticType, ...],
    tuple[ConstraintSemanticType, ...],
]:
    explicit_types = {item.semantic_type for item in explicit.items}
    survivors = tuple(item for item in inherited.items if item.semantic_type not in explicit_types)
    merged = ConstraintSet(items=tuple(explicit.items) + survivors)
    replaced = tuple(
        sorted(
            explicit_types.intersection(
                {item.semantic_type for item in inherited.items}
            ),
            key=lambda item: item.value,
        )
    )
    surviving_types = tuple(
        sorted(
            {item.semantic_type for item in survivors},
            key=lambda item: item.value,
        )
    )
    return merged, replaced, surviving_types


def _result_reference(question: str) -> str | None:
    normalised = _normalise(question)
    if "second" in normalised:
        return "second"
    if "first" in normalised:
        return "first"
    if "other" in normalised:
        return "other"
    if "those" in normalised:
        return "those"
    return None


def _intent(
    question: str,
    *,
    explicit_entity: bool,
    result_reference: str | None,
    pending: bool,
    has_constraints: bool,
    refining: bool,
) -> ResolvedIntent:
    normalised = _normalise(question)
    if pending and normalised in {"yes", "no", "first", "second", "both"}:
        return ResolvedIntent(name="clarification_response", operation="clarification_response")
    if "back to" in normalised:
        family = "fact_lookup" if any(word in normalised for word in ("where", "cost", "units", "prerequisite", "catered")) else "lookup"
        return ResolvedIntent(name=family, operation="return_topic")
    if "any more" in normalised or "more results" in normalised:
        return ResolvedIntent(name="discover", operation="continue_results")
    if result_reference:
        family = "fact_lookup" if any(word in normalised for word in ("where", "when", "close", "cost")) else "lookup"
        return ResolvedIntent(name=family, operation="lookup")
    if "compare" in normalised:
        return ResolvedIntent(name="compare", operation="compare")
    if refining and not explicit_entity:
        return ResolvedIntent(name="discover", operation="refine_results")
    if any(word in normalised for word in ("prerequisite", "units", "where", "cost", "catered", "apply", "available", "vacancy", "close")):
        return ResolvedIntent(name="fact_lookup", operation="lookup")
    if has_constraints or any(word in normalised for word in ("show", "find", "what events", "which")):
        return ResolvedIntent(name="discover", operation="initial_discovery")
    return ResolvedIntent(name="lookup", operation="lookup")


def extract_student_facts(question: str, turn: int) -> tuple[StudentStatedFact, ...]:
    normalised = _normalise(question)
    facts: list[StudentStatedFact] = []
    if "international" in normalised:
        facts.append(StudentStatedFact(semantic_type=StudentFactType.INTERNATIONAL, value=True, stated_turn=turn))
    program = re.search(
        r"\b(?:bachelor|master) of [a-z]+(?: [a-z]+)*?(?= student\b|[.,]|$)",
        normalised,
    )
    if program:
        facts.append(StudentStatedFact(semantic_type=StudentFactType.PROGRAM, value=program.group(0).title(), stated_turn=turn))
    return tuple(facts)


def interpret_turn(question: str, history: Sequence[HistoryTurn], state: ConversationState) -> QueryInterpretation:
    """Interpret one already-numbered turn without mutating structured state."""

    del history  # bounded language history is intentionally not factual authority
    turn = state.turn_index
    normalised = _normalise(question)
    explicit = _explicit_entity(question, turn)
    typed = _typed_reference(question)
    domain_return = _is_domain_return(question)
    if domain_return:
        typed = None
    domain = explicit.domain if explicit else _domain_from_words(question)
    if domain is None and state.focus is not None and any(
        token in normalised
        for token in (
            "after ", "before ", "today", "tomorrow", "any more",
            "cost", "apply", "available", "vacancy", "prerequisite", "units",
            "where", "when", "close", "catered", "is it", "its ",
        )
    ):
        domain = state.focus.domain
    result_reference = _result_reference(question)
    result_resolution = None
    entity = explicit
    entity_origin = "explicit" if explicit else "none"
    reference_origin = "none"
    referenced_result_set_id = None
    requires_clarification = False
    ambiguity = "none"

    if result_reference is not None:
        expected_kind = typed[1] if typed else None
        expected_domain = typed[0] if typed else domain
        result_resolution = resolve_result_reference(
            state,
            result_reference,
            entity_kind=expected_kind,
            domain=expected_domain,
        )
        if result_resolution.clarification_required or result_resolution.result_set is None:
            requires_clarification = True
            ambiguity = (
                "missing_reference"
                if result_resolution.result_set is None
                else "result_set"
            )
        else:
            result_set = result_resolution.result_set
            domain = result_set.domain
            reference_origin = "prior_result_set"
            referenced_result_set_id = result_set.result_set_id
            entity_origin = "result_set"
            if len(result_resolution.canonical_ids) == 1:
                canonical_id = result_resolution.canonical_ids[0]
                entity = _entity(
                    domain=result_set.domain,
                    kind=result_set.entity_kind,
                    canonical_id=canonical_id,
                    name=canonical_id,
                    turn=turn,
                    basis=EntityResolutionBasis.RETAINED_STATE,
                )

    if entity is None and result_reference is None and (
        typed is not None
        or ("back to" in normalised and not domain_return)
        or any(
            word in normalised
            for word in (
                " it", "its ", "is it", "cost", "apply", "available",
                "vacancy", "prerequisite", "units", "catered",
            )
        )
    ):
        typed_domain, typed_kind = typed if typed is not None else (domain, None)
        resolution = resolve_entity_reference(
            state,
            explicit_kind=typed_kind,
            explicit_domain=typed_domain,
        )
        if resolution.entity is None:
            requires_clarification = True
            ambiguity = "missing_reference"
        else:
            entity = resolution.entity
            domain = entity.domain
            entity_origin = "typed_reference" if typed is not None else "retained_state"
            reference_origin = "prior_typed_state"

    if domain is None and state.focus is not None and result_reference is not None:
        domain = state.focus.domain

    explicit_constraints = _explicit_constraints(question, domain, turn)
    inherited_before_override = (
        constraints_for(
            state,
            domain=domain,
            entity_kind=entity.kind if entity else None,
            canonical_entity_id=entity.canonical_id if entity else None,
        )
        if domain is not None
        else ConstraintSet()
    )
    explicit_types = {item.semantic_type for item in explicit_constraints.items}
    inherited = ConstraintSet(
        items=tuple(
            item
            for item in inherited_before_override.items
            if item.semantic_type not in explicit_types
        )
    )
    merged, replaced, surviving = _merge_constraints(explicit_constraints, inherited_before_override)
    refining = bool(explicit_constraints.items) and (
        bool(inherited_before_override.items)
        or any(item.domain == domain for item in state.result_sets)
    )
    intent = _intent(
        question,
        explicit_entity=explicit is not None,
        result_reference=result_reference,
        pending=state.pending_clarification is not None,
        has_constraints=bool(explicit_constraints.items),
        refining=refining,
    )

    if intent.operation == "continue_results":
        compatible = next(
            (
                item
                for item in state.result_sets
                if domain is None or item.domain == domain
            ),
            None,
        )
        if compatible is None or compatible.status != ResultSetStatus.RESULTS:
            requires_clarification = True
            ambiguity = "missing_reference"
        else:
            domain = compatible.domain
            reference_origin = "prior_result_set"
            referenced_result_set_id = compatible.result_set_id

    clarification_response = intent.name == "clarification_response"
    explicit_new = not clarification_response and (
        explicit is not None or domain is not None or "actually" in normalised
    )
    if clarification_response:
        reference_origin = "pending_clarification"

    return QueryInterpretation(
        domain=domain,
        entity=entity,
        intent=intent,
        explicit_constraints=explicit_constraints,
        inherited_constraints=inherited,
        constraints=merged,
        entity_origin=entity_origin,
        reference_origin=reference_origin,
        referenced_result_set_id=referenced_result_set_id,
        ambiguity=ambiguity,
        replaced_constraint_types=replaced,
        surviving_constraint_types=surviving,
        missing_slots=("reference",) if requires_clarification else (),
        requires_clarification=requires_clarification,
        explicit_new_request=explicit_new,
    )


def result_reference_for(question: str) -> str | None:
    return _result_reference(question)
