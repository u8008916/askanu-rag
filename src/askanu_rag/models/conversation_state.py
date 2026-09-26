"""Versioned, client-carried V7 conversational state contracts.

The state is untrusted semantic context.  It never supplies institutional facts
and it is deliberately separate from the bounded natural-language history.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    model_validator,
)

STATE_SCHEMA_VERSION = 1
MAX_RETAINED_ENTITIES = 12
MAX_RETAINED_RESULT_SETS = 6
MAX_RESULT_IDENTITIES = 20
MAX_RETAINED_CONSTRAINTS = 16
MAX_RETAINED_STUDENT_FACTS = 12
MAX_CLARIFICATION_OPTIONS = 20

ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
    ),
]
SemanticName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    ),
]
ScalarText = Annotated[
    StrictStr,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
BoundedInt = Annotated[StrictInt, Field(ge=-1_000_000_000, le=1_000_000_000)]
BoundedFloat = Annotated[
    StrictFloat,
    Field(ge=-1_000_000_000, le=1_000_000_000, allow_inf_nan=False),
]
ScalarValue = ScalarText | StrictBool | BoundedInt | BoundedFloat
TurnIndex = Annotated[StrictInt, Field(ge=0, le=1_000_000)]


class StateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Domain(str, Enum):
    COURSES = "courses"
    SCHOLARSHIPS = "scholarships"
    JOBS = "jobs"
    ACCOMMODATION = "accommodation"
    SUPPORT = "support"
    EVENTS = "events"


class EntityKind(str, Enum):
    COURSE = "course"
    PROGRAM = "program"
    MAJOR = "major"
    MINOR = "minor"
    SPECIALISATION = "specialisation"
    SCHOLARSHIP = "scholarship"
    JOB = "job"
    RESIDENCE = "residence"
    EVENT = "event"
    SUPPORT_SERVICE = "support_service"
    SUPPORT_TOPIC = "support_topic"


ENTITY_DOMAIN: dict[EntityKind, Domain] = {
    EntityKind.COURSE: Domain.COURSES,
    EntityKind.PROGRAM: Domain.COURSES,
    EntityKind.MAJOR: Domain.COURSES,
    EntityKind.MINOR: Domain.COURSES,
    EntityKind.SPECIALISATION: Domain.COURSES,
    EntityKind.SCHOLARSHIP: Domain.SCHOLARSHIPS,
    EntityKind.JOB: Domain.JOBS,
    EntityKind.RESIDENCE: Domain.ACCOMMODATION,
    EntityKind.EVENT: Domain.EVENTS,
    EntityKind.SUPPORT_SERVICE: Domain.SUPPORT,
    EntityKind.SUPPORT_TOPIC: Domain.SUPPORT,
}


class EntityResolutionBasis(str, Enum):
    EXPLICIT_IDENTIFIER = "explicit_identifier"
    CANONICAL_NAME = "canonical_name"
    SAFE_ALIAS = "safe_alias"
    TYPED_REFERENCE = "typed_reference"
    RETAINED_STATE = "retained_state"


class ResolvedEntity(StateModel):
    domain: Domain
    kind: EntityKind
    canonical_id: Identifier
    canonical_name: ShortText
    source_record_id: Identifier | None = None
    resolution_basis: EntityResolutionBasis
    mentioned_turn: TurnIndex

    @model_validator(mode="after")
    def domain_matches_kind(self) -> "ResolvedEntity":
        if ENTITY_DOMAIN[self.kind] != self.domain:
            raise ValueError("entity kind is incompatible with domain")
        return self


class ResolvedIntent(StateModel):
    name: SemanticName
    operation: SemanticName
    required_slots: tuple[SemanticName, ...] = Field(
        default_factory=tuple, max_length=12
    )
    resolved_slots: tuple[SemanticName, ...] = Field(
        default_factory=tuple, max_length=12
    )

    @model_validator(mode="after")
    def slots_are_unique_and_known(self) -> "ResolvedIntent":
        if len(set(self.required_slots)) != len(self.required_slots):
            raise ValueError("required slots must be unique")
        if len(set(self.resolved_slots)) != len(self.resolved_slots):
            raise ValueError("resolved slots must be unique")
        if not set(self.resolved_slots).issubset(self.required_slots):
            raise ValueError("resolved slots must be required slots")
        return self


class ConstraintSemanticType(str, Enum):
    # Inclusive upper bound (<=). Kept as the existing serialized name for
    # backwards-compatible schema-version-1 state.
    MAX_PRICE = "max_price"
    # Strict upper bound (<). Day 4 preserves wording such as "under" rather
    # than collapsing it into the inclusive MAX_PRICE meaning.
    MAX_PRICE_EXCLUSIVE = "max_price_exclusive"
    # Accepted only so existing schema-version-1 client state still validates.
    # Day 2 interpretation never emits this legacy combined dimension.
    LEGACY_TEMPORAL_WINDOW = "temporal_window"
    DATE_WINDOW = "date_window"
    TIME_OF_DAY_WINDOW = "time_of_day_window"
    STUDENT_TYPE = "student_type"
    PROGRAM = "program"
    STUDY_LEVEL = "study_level"
    LOCATION = "location"
    CATEGORY = "category"
    EMPLOYMENT_TYPE = "employment_type"
    ACCESSIBILITY = "accessibility"


class ConstraintLifecycle(str, Enum):
    CURRENT_OPERATION = "current_operation"
    UNTIL_REPLACED = "until_replaced"
    SESSION = "session"


class ConstraintScope(StateModel):
    domain: Domain
    entity_kind: EntityKind | None = None
    canonical_entity_id: Identifier | None = None
    intent: SemanticName | None = None

    @model_validator(mode="after")
    def scope_is_consistent(self) -> "ConstraintScope":
        if self.entity_kind is not None and ENTITY_DOMAIN[self.entity_kind] != self.domain:
            raise ValueError("constraint entity kind is incompatible with domain")
        if self.canonical_entity_id is not None and self.entity_kind is None:
            raise ValueError("entity-scoped constraint requires entity kind")
        return self


class ScopedConstraint(StateModel):
    semantic_type: ConstraintSemanticType
    value: ScalarValue
    scope: ConstraintScope
    lifecycle: ConstraintLifecycle
    hard: StrictBool = True
    introduced_turn: TurnIndex

    @model_validator(mode="after")
    def operation_constraint_has_intent_scope(self) -> "ScopedConstraint":
        if (
            self.lifecycle == ConstraintLifecycle.CURRENT_OPERATION
            and self.scope.intent is None
        ):
            raise ValueError("current-operation constraint requires intent scope")
        return self


class ConstraintSet(StateModel):
    items: tuple[ScopedConstraint, ...] = Field(
        default_factory=tuple, max_length=MAX_RETAINED_CONSTRAINTS
    )

    @model_validator(mode="after")
    def constraint_keys_are_unique(self) -> "ConstraintSet":
        price_types = {
            ConstraintSemanticType.MAX_PRICE,
            ConstraintSemanticType.MAX_PRICE_EXCLUSIVE,
        }
        keys = [
            (
                (
                    ConstraintSemanticType.MAX_PRICE
                    if item.semantic_type in price_types
                    else item.semantic_type
                ),
                item.scope.domain,
                item.scope.entity_kind,
                item.scope.canonical_entity_id,
                item.scope.intent,
            )
            for item in self.items
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("constraint semantic/scope keys must be unique")
        return self


class StudentFactType(str, Enum):
    INTERNATIONAL = "international"
    PROGRAM = "program"
    STUDY_LEVEL = "study_level"
    STUDENT_TYPE = "student_type"


class StudentStatedFact(StateModel):
    semantic_type: StudentFactType
    value: ScalarValue
    domain_scope: Domain | None = None
    stated_turn: TurnIndex
    authority: Literal["user_stated"] = "user_stated"


class ResultSetStatus(str, Enum):
    RESULTS = "RESULTS"
    EMPTY = "EMPTY"
    INCOMPLETE = "INCOMPLETE"


class ResultSet(StateModel):
    result_set_id: Identifier
    domain: Domain
    entity_kind: EntityKind
    ordered_canonical_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=MAX_RESULT_IDENTITIES
    )
    originating_query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    ]
    intent: ResolvedIntent
    constraints: ConstraintSet = Field(default_factory=ConstraintSet)
    created_turn: TurnIndex
    last_refined_turn: TurnIndex
    status: ResultSetStatus
    parent_result_set_id: Identifier | None = None

    @model_validator(mode="after")
    def result_shape_matches_status(self) -> "ResultSet":
        if ENTITY_DOMAIN[self.entity_kind] != self.domain:
            raise ValueError("result entity kind is incompatible with domain")
        if len(set(self.ordered_canonical_ids)) != len(self.ordered_canonical_ids):
            raise ValueError("result identities must be unique")
        if self.status == ResultSetStatus.RESULTS and not self.ordered_canonical_ids:
            raise ValueError("RESULTS requires at least one identity")
        if self.status == ResultSetStatus.EMPTY and self.ordered_canonical_ids:
            raise ValueError("EMPTY cannot contain identities")
        if self.last_refined_turn < self.created_turn:
            raise ValueError("result refinement cannot predate creation")
        return self


class StateClarificationOption(StateModel):
    id: Identifier
    label: ShortText


class ResolvedSlot(StateModel):
    name: SemanticName
    value: ScalarValue


class PendingClarification(StateModel):
    id: Identifier
    type: SemanticName
    options: tuple[StateClarificationOption, ...] = Field(
        default_factory=tuple, max_length=MAX_CLARIFICATION_OPTIONS
    )
    allow_multiple: StrictBool
    original_intent: ResolvedIntent | None = None
    resolved_entities: tuple[ResolvedEntity, ...] = Field(
        default_factory=tuple, max_length=6
    )
    resolved_slots: tuple[ResolvedSlot, ...] = Field(
        default_factory=tuple, max_length=12
    )
    missing_slots: tuple[SemanticName, ...] = Field(
        default_factory=tuple, max_length=12
    )
    constraints: ConstraintSet = Field(default_factory=ConstraintSet)
    created_turn: TurnIndex = 0

    @model_validator(mode="after")
    def rich_pending_state_is_consistent(self) -> "PendingClarification":
        option_ids = [option.id for option in self.options]
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("clarification option IDs must be unique")
        names = [slot.name for slot in self.resolved_slots]
        if len(set(names)) != len(names):
            raise ValueError("resolved clarification slots must be unique")
        if len(set(self.missing_slots)) != len(self.missing_slots):
            raise ValueError("missing clarification slots must be unique")
        if set(names).intersection(self.missing_slots):
            raise ValueError("a clarification slot cannot be resolved and missing")
        return self


class SemanticFocus(StateModel):
    domain: Domain
    entity_kind: EntityKind | None = None
    canonical_entity_id: Identifier | None = None
    intent_name: SemanticName | None = None
    result_set_id: Identifier | None = None

    @model_validator(mode="after")
    def focus_is_consistent(self) -> "SemanticFocus":
        if self.entity_kind is not None and ENTITY_DOMAIN[self.entity_kind] != self.domain:
            raise ValueError("focus entity kind is incompatible with domain")
        if self.canonical_entity_id is not None and self.entity_kind is None:
            raise ValueError("entity focus requires entity kind")
        return self


class SelectedResult(StateModel):
    result_set_id: Identifier
    canonical_id: Identifier
    ordinal: Annotated[StrictInt, Field(ge=1, le=MAX_RESULT_IDENTITIES)]


class ConversationState(StateModel):
    schema_version: Literal[STATE_SCHEMA_VERSION] = STATE_SCHEMA_VERSION
    turn_index: TurnIndex = 0
    recent_entities: tuple[ResolvedEntity, ...] = Field(
        default_factory=tuple, max_length=MAX_RETAINED_ENTITIES
    )
    focus: SemanticFocus | None = None
    student_facts: tuple[StudentStatedFact, ...] = Field(
        default_factory=tuple, max_length=MAX_RETAINED_STUDENT_FACTS
    )
    constraints: ConstraintSet = Field(default_factory=ConstraintSet)
    result_sets: tuple[ResultSet, ...] = Field(
        default_factory=tuple, max_length=MAX_RETAINED_RESULT_SETS
    )
    selected_result: SelectedResult | None = None
    pending_clarification: PendingClarification | None = None

    @model_validator(mode="after")
    def references_are_retained(self) -> "ConversationState":
        if any(
            entity.mentioned_turn > self.turn_index
            for entity in self.recent_entities
        ):
            raise ValueError("entity mention cannot be in a future turn")
        if any(fact.stated_turn > self.turn_index for fact in self.student_facts):
            raise ValueError("student fact cannot be in a future turn")
        if any(
            constraint.introduced_turn > self.turn_index
            for constraint in self.constraints.items
        ):
            raise ValueError("constraint cannot be introduced in a future turn")
        if any(
            result_set.created_turn > self.turn_index
            or result_set.last_refined_turn > self.turn_index
            for result_set in self.result_sets
        ):
            raise ValueError("result set cannot be created or refined in a future turn")
        if (
            self.pending_clarification is not None
            and self.pending_clarification.created_turn > self.turn_index
        ):
            raise ValueError("clarification cannot be created in a future turn")
        entities = {
            (entity.kind, entity.canonical_id) for entity in self.recent_entities
        }
        if len(entities) != len(self.recent_entities):
            raise ValueError("retained entity identities must be unique")
        fact_keys = {
            (fact.semantic_type, fact.domain_scope) for fact in self.student_facts
        }
        if len(fact_keys) != len(self.student_facts):
            raise ValueError("student fact semantic/scope keys must be unique")
        result_sets = {item.result_set_id: item for item in self.result_sets}
        if len(result_sets) != len(self.result_sets):
            raise ValueError("result set IDs must be unique")
        if self.focus is not None:
            if (
                self.focus.canonical_entity_id is not None
                and (self.focus.entity_kind, self.focus.canonical_entity_id)
                not in entities
            ):
                raise ValueError("focus must reference a retained entity")
            if (
                self.focus.result_set_id is not None
                and self.focus.result_set_id not in result_sets
            ):
                raise ValueError("focus must reference a retained result set")
        if self.selected_result is not None:
            result_set = result_sets.get(self.selected_result.result_set_id)
            if result_set is None:
                raise ValueError("selected result must reference a retained result set")
            index = self.selected_result.ordinal - 1
            if (
                index >= len(result_set.ordered_canonical_ids)
                or result_set.ordered_canonical_ids[index]
                != self.selected_result.canonical_id
            ):
                raise ValueError("selected result ordinal and identity must agree")
        return self


class RetrievalStrategy(str, Enum):
    EXACT_LOOKUP = "exact_lookup"
    STRUCTURED_FILTER = "structured_filter"
    DETERMINISTIC_DISCOVERY = "deterministic_discovery"
    SEMANTIC_VECTOR = "semantic_vector"
    HYBRID = "hybrid"


class RetrievalStep(StateModel):
    strategy: RetrievalStrategy
    purpose: ShortText


class RetrievalPlan(StateModel):
    plan_id: Identifier
    domain: Domain
    entity_kind: EntityKind | None = None
    intent: ResolvedIntent
    constraints: ConstraintSet = Field(default_factory=ConstraintSet)
    steps: tuple[RetrievalStep, ...] = Field(min_length=1, max_length=5)
    originating_result_set_id: Identifier | None = None
    evidence_selection_required: Literal[True] = True

    @model_validator(mode="after")
    def plan_is_deterministic_first(self) -> "RetrievalPlan":
        if self.entity_kind is not None and ENTITY_DOMAIN[self.entity_kind] != self.domain:
            raise ValueError("plan entity kind is incompatible with domain")
        strategies = [step.strategy for step in self.steps]
        if len(set(strategies)) != len(strategies):
            raise ValueError("retrieval strategies must be unique")
        discovery = {
            RetrievalStrategy.SEMANTIC_VECTOR,
            RetrievalStrategy.HYBRID,
        }
        authoritative = {
            RetrievalStrategy.EXACT_LOOKUP,
            RetrievalStrategy.STRUCTURED_FILTER,
            RetrievalStrategy.DETERMINISTIC_DISCOVERY,
        }
        first_discovery = next(
            (index for index, strategy in enumerate(strategies) if strategy in discovery),
            None,
        )
        if first_discovery is not None and any(
            strategy in authoritative
            for strategy in strategies[first_discovery + 1 :]
        ):
            raise ValueError("authoritative retrieval must precede semantic discovery")
        return self


class AnswerState(str, Enum):
    CONFIRMED = "CONFIRMED"
    DERIVED = "DERIVED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class EvidenceItem(StateModel):
    record_id: Identifier
    source_id: Identifier
    domain: Domain
    canonical_url: HttpUrl
    evidence_text: Annotated[str, StringConstraints(min_length=1, max_length=4_000)]
    selected_fields: tuple[SemanticName, ...] = Field(
        default_factory=tuple, max_length=20
    )
    authority: Literal["approved_persisted_record"] = "approved_persisted_record"


class MissingEvidence(StateModel):
    field: SemanticName
    reason: Literal["absent", "null", "not_retrieved", "incomplete_population"]


class EvidenceBundle(StateModel):
    bundle_id: Identifier
    plan_id: Identifier
    result_set_id: Identifier | None = None
    selected_evidence: tuple[EvidenceItem, ...] = Field(
        default_factory=tuple, max_length=MAX_RESULT_IDENTITIES
    )
    missing_evidence: tuple[MissingEvidence, ...] = Field(
        default_factory=tuple, max_length=MAX_RESULT_IDENTITIES
    )
    answer_state: AnswerState

    @model_validator(mode="after")
    def unknown_requires_missing_evidence(self) -> "EvidenceBundle":
        if self.answer_state == AnswerState.UNKNOWN and not self.missing_evidence:
            raise ValueError("UNKNOWN requires an explicit missing-evidence reason")
        return self


class QueryInterpretation(StateModel):
    domain: Domain | None = None
    possible_domains: tuple[Domain, ...] = Field(default_factory=tuple, max_length=6)
    entity: ResolvedEntity | None = None
    possible_entities: tuple[ResolvedEntity, ...] = Field(
        default_factory=tuple, max_length=MAX_CLARIFICATION_OPTIONS
    )
    intent: ResolvedIntent | None = None
    explicit_constraints: ConstraintSet = Field(default_factory=ConstraintSet)
    inherited_constraints: ConstraintSet = Field(default_factory=ConstraintSet)
    constraints: ConstraintSet = Field(default_factory=ConstraintSet)
    entity_origin: Literal[
        "none", "explicit", "typed_reference", "retained_state", "result_set"
    ] = "none"
    reference_origin: Literal[
        "none", "prior_typed_state", "prior_result_set", "pending_clarification"
    ] = "none"
    referenced_result_set_id: Identifier | None = None
    ambiguity: Literal[
        "none", "domain", "entity", "result_set", "missing_reference", "missing_slot"
    ] = "none"
    replaced_constraint_types: tuple[ConstraintSemanticType, ...] = Field(
        default_factory=tuple, max_length=MAX_RETAINED_CONSTRAINTS
    )
    surviving_constraint_types: tuple[ConstraintSemanticType, ...] = Field(
        default_factory=tuple, max_length=MAX_RETAINED_CONSTRAINTS
    )
    missing_slots: tuple[SemanticName, ...] = Field(
        default_factory=tuple, max_length=12
    )
    requires_clarification: StrictBool = False
    explicit_new_request: StrictBool = False

    @model_validator(mode="after")
    def ambiguity_is_explicit(self) -> "QueryInterpretation":
        if len(set(self.possible_domains)) != len(self.possible_domains):
            raise ValueError("possible domains must be unique")
        if (self.possible_domains or self.possible_entities or self.missing_slots) and not self.requires_clarification:
            raise ValueError("unresolved alternatives or slots require clarification")
        if self.ambiguity != "none" and not self.requires_clarification:
            raise ValueError("ambiguity requires clarification")
        explicit_types = {
            item.semantic_type for item in self.explicit_constraints.items
        }
        inherited_types = {
            item.semantic_type for item in self.inherited_constraints.items
        }
        if explicit_types.intersection(inherited_types):
            raise ValueError(
                "explicit constraints must replace inherited constraints of the same type"
            )
        return self
