"""Deterministic V7 Day 2 turn interpretation.

This module resolves conversational meaning only.  It neither retrieves nor
asserts institutional facts, and every output validates against the shared Day
1/Day 2 contracts.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from askanu_rag.domain_resolution import (
    DEFAULT_PROBLEM_DOMAIN_RESOLVER,
    ProblemDomainResolver,
)
from askanu_rag.entity_resolution import (
    DEFAULT_ENTITY_CATALOGUE,
    DEFAULT_SAFE_ENTITY_ALIASES,
    EntityCatalogue,
    SafeEntityAlias,
    resolve_explicit_entity,
)
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
from askanu_rag.temporal_compatibility import (
    normalise_legacy_temporal_constraints,
)

_SPACE_RE = re.compile(r"\s+")
_EXCLUSIVE_PRICE_RE = re.compile(
    r"\b(?:under|below|less than)\b\s*(?:A?\$)?\s*(?P<amount>\d{2,6})",
    re.IGNORECASE,
)
_INCLUSIVE_PRICE_RE = re.compile(
    r"\b(?:no more than|up to|max(?:imum)?)\b"
    r"\s*(?:A?\$)?\s*(?P<amount>\d{2,6})",
    re.IGNORECASE,
)
_AFTER_RE = re.compile(r"\bafter\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_BEFORE_RE = re.compile(r"\bbefore\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_BETWEEN_RE = re.compile(
    r"\bbetween\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+and\s+"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
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


def _price_constraint(
    question: str,
) -> tuple[ConstraintSemanticType, int] | None:
    """Preserve strict versus inclusive upper-bound wording."""

    exclusive = _EXCLUSIVE_PRICE_RE.search(question)
    inclusive = _INCLUSIVE_PRICE_RE.search(question)
    if exclusive is None and inclusive is None:
        return None
    if exclusive is not None and (
        inclusive is None or exclusive.start() <= inclusive.start()
    ):
        return ConstraintSemanticType.MAX_PRICE_EXCLUSIVE, int(
            exclusive.group("amount")
        )
    assert inclusive is not None
    return ConstraintSemanticType.MAX_PRICE, int(inclusive.group("amount"))


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
        (("accommodation", "housing", "residence", "hall", "lodge", "catered", "vacancy", "rooms available", "place to live", "places to live", "somewhere to live"), Domain.ACCOMMODATION),
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
            r"\b(?:back|return|go back) to (?:the )?(?:courses|scholarships|jobs|events|services|"
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

    price = _price_constraint(question)
    if price:
        found.append(ScopedConstraint(
            semantic_type=price[0],
            value=price[1],
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
    price_types = {
        ConstraintSemanticType.MAX_PRICE,
        ConstraintSemanticType.MAX_PRICE_EXCLUSIVE,
    }

    def family(item: ConstraintSemanticType) -> object:
        return ConstraintSemanticType.MAX_PRICE if item in price_types else item

    explicit_types = {item.semantic_type for item in explicit.items}
    explicit_families = {family(item) for item in explicit_types}
    survivors = tuple(
        item
        for item in inherited.items
        if family(item.semantic_type) not in explicit_families
    )
    merged = ConstraintSet(items=tuple(explicit.items) + survivors)
    replaced = tuple(
        sorted(
            {
                item.semantic_type
                for item in inherited.items
                if family(item.semantic_type) in explicit_families
            },
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
    if re.search(r"\b(?:the )?first (?:two|2)\b", normalised):
        return "first_two"
    if "second" in normalised:
        return "second"
    if "first" in normalised:
        return "first"
    if "other" in normalised:
        return "other"
    if "those" in normalised:
        return "those"
    return None


def _is_continue_results_phrase(normalised: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:show(?: me)? more|any more|more results|what else)[?.!]*",
            normalised,
        )
    )


def _is_accommodation_result_preference(
    normalised: str, domain: Domain | None
) -> bool:
    return domain == Domain.ACCOMMODATION and bool(
        re.search(
            r"\b(?:self[- ]catered|catered|meal plan|cook for myself)\b",
            normalised,
        )
    )


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
    if any(phrase in normalised for phrase in ("back to", "return to", "go back to")):
        family = "fact_lookup" if any(word in normalised for word in ("where", "cost", "units", "prerequisite", "catered")) else "lookup"
        return ResolvedIntent(name=family, operation="return_topic")
    if _is_continue_results_phrase(normalised):
        return ResolvedIntent(name="discover", operation="continue_results")
    if "compare" in normalised:
        return ResolvedIntent(name="compare", operation="compare")
    if result_reference:
        family = "fact_lookup" if any(word in normalised for word in ("where", "when", "close", "cost")) else "lookup"
        return ResolvedIntent(name=family, operation="lookup")
    if refining and not explicit_entity:
        return ResolvedIntent(name="discover", operation="refine_results")
    if any(
        word in normalised
        for word in (
            "prerequisite", "units", "where", "cost", "price", "rate",
            "catered", "catering", "meal", "apply", "application",
            "available", "availability", "vacancy", "close",
        )
    ):
        return ResolvedIntent(name="fact_lookup", operation="lookup")
    if has_constraints or any(word in normalised for word in ("show", "list", "find", "what events", "which")):
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


def interpret_turn(
    question: str,
    history: Sequence[HistoryTurn],
    state: ConversationState,
    *,
    entity_catalogue: EntityCatalogue = DEFAULT_ENTITY_CATALOGUE,
    entity_aliases: Sequence[SafeEntityAlias] = DEFAULT_SAFE_ENTITY_ALIASES,
    problem_domain_resolver: ProblemDomainResolver = DEFAULT_PROBLEM_DOMAIN_RESOLVER,
) -> QueryInterpretation:
    """Interpret one already-numbered turn without mutating structured state."""

    del history  # bounded language history is intentionally not factual authority
    turn = state.turn_index
    normalised = _normalise(question)
    explicit_resolution = resolve_explicit_entity(
        question,
        turn,
        catalogue=entity_catalogue,
        aliases=entity_aliases,
    )
    explicit = explicit_resolution.entity
    typed = _typed_reference(question)
    domain_return = _is_domain_return(question)
    if domain_return:
        typed = None
    lexical_domain = _domain_from_words(question)
    problem_resolution = (
        problem_domain_resolver.resolve(question)
        if explicit is None and lexical_domain is None
        else None
    )
    domain = (
        explicit.domain
        if explicit
        else lexical_domain
        or (problem_resolution.domain if problem_resolution is not None else None)
    )
    possible_domains = (
        problem_resolution.possible_domains
        if problem_resolution is not None
        else ()
    )
    if (
        domain is None
        and not possible_domains
        and state.focus is not None
        and any(
        token in normalised
        for token in (
            "after ", "before ", "today", "tomorrow", "any more",
            "show more", "show me more", "what else",
            "cost", "apply", "available", "availability", "vacancy",
            "prerequisite", "units",
            "where", "when", "close", "catered", "catering", "meal", "application",
            "price", "rate", "room", "is it", "its ",
            "under ", "below ", "less than", "no more than", "up to ",
            "budget", "maximum", " max",
        )
        )
    ):
        domain = state.focus.domain
    result_reference = _result_reference(question)
    result_resolution = None
    entity = explicit
    entity_origin = "explicit" if explicit else "none"
    reference_origin = "none"
    referenced_result_set_id = None
    requires_clarification = bool(
        explicit_resolution.possible_entities or possible_domains
    )
    ambiguity = (
        "entity"
        if explicit_resolution.possible_entities
        else "domain" if possible_domains else "none"
    )

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

    result_preference = _is_accommodation_result_preference(normalised, domain)
    refining_result_set_reference = bool(
        (_price_constraint(question) or result_preference)
        and domain is not None
        and any(item.domain == domain for item in state.result_sets)
    )
    if entity is None and result_reference is None and not refining_result_set_reference and (
        typed is not None
        or (domain_return and domain == Domain.ACCOMMODATION)
        or any(
            word in normalised
            for word in (
                " it", "its ", "is it", "cost", "apply", "available",
                "availability",
                "vacancy", "prerequisite", "units", "catered", "catering",
                "meal", "application", "price", "rate", "room", "how much",
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
    temporal_normalisation = normalise_legacy_temporal_constraints(
        inherited_before_override,
        explicit_constraints,
    )
    inherited_before_override = temporal_normalisation.constraints
    explicit_types = {item.semantic_type for item in explicit_constraints.items}
    inherited = ConstraintSet(
        items=tuple(
            item
            for item in inherited_before_override.items
            if item.semantic_type not in explicit_types
        )
    )
    merged, replaced, surviving = _merge_constraints(
        explicit_constraints,
        inherited_before_override,
    )
    if temporal_normalisation.removed_legacy:
        replaced = tuple(
            sorted(
                set(replaced)
                | {ConstraintSemanticType.LEGACY_TEMPORAL_WINDOW},
                key=lambda item: item.value,
            )
        )
    refining = bool(explicit_constraints.items or result_preference) and (
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

    if refining and referenced_result_set_id is None:
        compatible = next(
            (
                item
                for item in state.result_sets
                if item.domain == domain
                and (entity is None or item.entity_kind == entity.kind)
            ),
            None,
        )
        if compatible is not None:
            reference_origin = "prior_result_set"
            referenced_result_set_id = compatible.result_set_id

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
        explicit is not None
        or domain is not None
        or bool(possible_domains)
        or bool(explicit_resolution.possible_entities)
        or "actually" in normalised
    )
    if clarification_response:
        reference_origin = "pending_clarification"

    return QueryInterpretation(
        domain=domain,
        possible_domains=possible_domains,
        entity=entity,
        possible_entities=explicit_resolution.possible_entities,
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
