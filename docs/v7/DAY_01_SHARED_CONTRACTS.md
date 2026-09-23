# V7 Day 1 shared conversational contract review candidate

Date: 2026-09-22
Repository: `askanu-rag`
Branch: `carmen/v7-day1-shared-contracts`
Base: `91109b2268671bfc2b8f98c8fb0ef79f1c53325f`

This artifact records Carmen's implementation-complete candidate for the
RAG-owned semantic schema and deterministic state transitions for V7. It is
ready for PM review; Qasim owns the final shared-contract freeze, the Day 1
GO/HOLD decision and authorization to begin Day 2. It is deliberately not the
Day 2 natural-language resolver or production orchestration implementation.

## V6 to V7 gap inventory

| Classification | V6 observation | Day 1 contract consequence |
|---|---|---|
| state-model gap | The public state contained only `pending_clarification`; other meaning was re-read from at most ten history turns. | Add a versioned, bounded, client-carried structured state independent of history. |
| entity-resolution gap | Course, Job, Accommodation and Support follow-ups used separate regex/history paths. There was no shared six-domain typed memory. | Retain typed entities and resolve only compatible kinds/domains. |
| intent/constraint gap | Intent and filters were embedded in individual domain planners. Constraints had no common scope/lifecycle. | Keep DOMAIN, ENTITY, INTENT and CONSTRAINTS distinct; constraints use typed scope and replacement keys. |
| clarification gap | V6 pending options supported first/second/both safely, but did not carry a complete original operation, resolved slots and scoped constraints. | Pending state carries all information required to resume, and explicit new work supersedes it. |
| result-set gap | Ordered response lists were not reusable typed conversation objects. | Retain bounded typed ResultSets with stable ordinals and separate result status. |
| retrieval-planning gap | Deterministic-first behavior existed, but each service represented plans differently. | Freeze a shared RetrievalPlan without changing retrieval algorithms. |
| evidence/reasoning-state gap | Stored provenance and safe synthesis existed, but there was no shared EvidenceBundle or epistemic state. | Candidate retrieval and evidence selection become separate; AnswerState is explicit. |
| already-supported | Current-session isolation, fresh reads, exact/structured precedence, programmatic URLs, source boundaries, explicit topic-switch priority, controlled abstention and no live Rubric request. | Preserve these V6 invariants unchanged. |

## Wire contract

`POST /api/v1/ask` remains the existing endpoint. The only Day 1 wire change is
additive:

```text
request  = question + bounded history + optional conversation_state
response = existing response envelope + authoritative conversation_state
```

- Omitted state becomes an empty schema-version-1 state.
- The old `{pending_clarification: ...}` shape remains valid; omitted V7 fields
  receive safe defaults.
- RAG validates incoming state as untrusted input, increments the monotonic turn
  counter and returns the authoritative state.
- The App stores the returned object for the current chat and sends it back
  unchanged. Ben/App owns transport/storage only, not semantic mutation.
- RAG remains stateless between requests. There is no session ID, server store,
  Redis/cache, sticky session, profile or account memory.
- State is context, never institutional evidence. Every factual answer still
  requires approved persisted records.

Malformed state, an incompatible schema version, unknown fields, coercive scalar
types, duplicate semantic keys, dangling references or exceeded bounds returns
the existing controlled HTTP 400 envelope. RAG does not partially salvage an
invalid object.

## Shared primitives ready for PM review

### ConversationState

Schema version: integer literal `1`.

| Field | Type | Purpose |
|---|---|---|
| `schema_version` | literal `1` | Reject incompatible clients deterministically. |
| `turn_index` | strict integer | RAG-owned monotonic session turn. |
| `recent_entities` | `ResolvedEntity[]` | Typed per-domain memory; not one global entity. |
| `focus` | `SemanticFocus?` | Current semantic focus while older typed entries remain available. |
| `student_facts` | `StudentStatedFact[]` | Explicitly marked user claims, never ANU facts. |
| `constraints` | `ConstraintSet` | Active scoped structured constraints. |
| `result_sets` | `ResultSet[]` | Typed, ordered retained result populations. |
| `selected_result` | `SelectedResult?` | Stable selection within a retained ResultSet. |
| `pending_clarification` | `PendingClarification?` | One resumable unresolved operation. |

Clear Chat returns exactly the empty schema-version-1 state and the App clears
visible history at the same time.

### ResolvedEntity

Fields: `domain`, `kind`, `canonical_id`, `canonical_name`, optional
`source_record_id`, `resolution_basis`, and `mentioned_turn`.

Kinds cover Course, Program/Major/Minor/Specialisation, Scholarship, Job,
Residence, Event, Support Service and Support Topic. Kind/domain combinations
are validated. The entity contains identity only; no vacancy, price,
eligibility, hours, status or other institutional claim can be stored here.

### ResolvedIntent and interpretation

`ResolvedIntent` contains a semantic `name`, `operation`, required slots and
resolved slots. `QueryInterpretation` keeps these separate:

- resolved or possible domain;
- resolved or possible entity;
- intent;
- `ConstraintSet`;
- missing slots;
- explicit ambiguity/clarification state; and
- whether the turn is an explicit new request.

The interpreter may later use deterministic logic or a constrained model, but
model output must validate into `QueryInterpretation`; it never receives a raw
state-write API.

### ConstraintSet

Each constraint has:

- an allowed semantic type;
- a bounded scalar value;
- scope: domain plus optional entity kind/identity and intent;
- lifecycle: `CURRENT_OPERATION`, `UNTIL_REPLACED`, or `SESSION`;
- hard/soft marking; and
- introduction turn.

The replacement key is semantic type plus the complete scope. A new explicit
value with the same key replaces the old value, so `closing this week` followed
by `actually next month` leaves one temporal constraint. Domain, entity and
intent compatibility is required for inheritance. An Accommodation budget
cannot enter a Jobs, Scholarship, Course, Event or Support plan.

Hard constraints are never evicted silently. If 16 distinct active keys exist,
a seventeenth distinct key is rejected so the caller can clarify, explicitly
replace, or reset state.

### PendingClarification

Fields preserve the public clarification ID/type/options and also:

- original intent/operation;
- resolved entities;
- resolved slots;
- missing slots;
- relevant constraints; and
- creation turn.

A complete slot response resumes the saved intent. A validated explicit new
request clears the pending object and supersedes it. Legacy V6 clarification
objects are accepted and upgraded with a bounded `select_option` operation.

### ResultSet

Fields: stable ID, domain, entity kind, ordered canonical IDs, originating
query, intent, applicable constraints, creation/refinement turns, status and
optional parent ResultSet ID.

Statuses are independent of answer evidence:

- `RESULTS`: a supported evaluation returned at least one ordered identity.
- `EMPTY`: the supported population was fully evaluated and has zero matches.
- `INCOMPLETE`: evidence/population was insufficient for a complete result.

Refinement creates a new child ResultSet and leaves the parent order unchanged
until normal eviction. It never mutates the meaning of an earlier ordinal.

Reference rules:

- `first` and `second` are one-based positions in the newest compatible typed
  `RESULTS` set;
- `those` means all identities in that set, in stored order;
- `other` resolves only when exactly one alternative remains after an explicit
  selection; otherwise clarify;
- unrelated newer ResultSets are skipped when the reference is typed;
- `EMPTY`, `INCOMPLETE`, out-of-range and evicted references clarify rather
  than guess.

### RetrievalPlan

The plan records domain, optional entity kind, intent, constraints, originating
ResultSet and ordered candidate strategies:

- exact lookup;
- structured filter;
- deterministic discovery;
- semantic/vector discovery; and
- hybrid discovery.

When authoritative and semantic strategies coexist, authoritative steps must
come first. Every plan fixes `evidence_selection_required = true`: Top-K
candidates are not automatically answer evidence. Day 1 changes no provider,
ranking algorithm, Top-K, BM25/FTS, embeddings or framework.

### EvidenceBundle and AnswerState

`EvidenceBundle` contains its plan/ResultSet relationship, selected evidence
from approved persisted records, explicit missing evidence and `AnswerState`.
Every selected item preserves record ID, source ID, domain, stored canonical
URL, selected fields and bounded source text. Its authority is the literal
`approved_persisted_record`.

- `CONFIRMED`: selected approved evidence directly establishes the answer.
- `DERIVED`: a documented deterministic rule was applied to confirmed evidence.
- `PARTIAL`: only part of the requested answer is established; missing parts
  stay explicit.
- `UNKNOWN`: approved evidence cannot establish the answer and at least one
  missing-evidence reason is required.

`UNKNOWN` never means false, no match, ineligible, unavailable, free, online or
cancelled. ResultSet `EMPTY` can coexist with a `CONFIRMED` conclusion when a
complete supported population was evaluated.

## Resolver precedence and ambiguity

Proposed resolver order for PM review:

1. explicit exact entity/name/identifier in the current turn;
2. explicit compatible entity type/domain in the current turn;
3. compatible current structured focus;
4. newest compatible retained entity/ResultSet;
5. clarification.

Current explicit information always wins. Incompatible older state is never
selected because it is recent. Multiple explicit candidates, a missing typed
candidate, an invalid ordinal, an incomplete/empty set reference or a reference
outside retention requires clarification.

## Bounds and deterministic eviction

| Collection | Limit | Rule |
|---|---:|---|
| typed entities | 12 | Upsert by `(kind, canonical_id)`; newest `mentioned_turn` first; deterministic kind/ID tie-break; evict oldest. |
| ResultSets | 6 | Upsert by ResultSet ID; newest refinement/creation first; deterministic ID tie-break; evict oldest. |
| identities per ResultSet | 20 | Preserve source evaluation order; duplicates invalid. |
| constraints | 16 | Replace same semantic/scope key; refuse a distinct 17th key rather than silently drop a hard rule. |
| student-stated facts | 12 | Replace same semantic/domain key; newest first; evict oldest. |
| clarification | 1 | A new clarification replaces the prior pending operation; 20 options maximum. |

All retained turns and scalar/string values have explicit bounds. Incoming
array order is not trusted; RAG canonicalises recency ordering. After eviction,
references clarify.

The executable 20-turn test retains COMP1110 and Warrumbul while multiple
Scholarship ResultSets and unrelated turns occur. Both typed identities remain
recoverable after the relevant wording would have fallen outside ten-turn raw
history.

## Executable spikes and golden transitions

The shared primitives prove both required journeys without a global topic:

```text
COMP1110 -> Warrumbul -> back to the course = COMP1110

Warrumbul -> it = Warrumbul
-> international + Bachelor of Computing (user-stated)
-> Scholarship ResultSet -> second = stable member 2
-> back to accommodation = Warrumbul
-> Clear Chat -> it = clarification, never Warrumbul
```

Golden semantic transitions cover:

1. exact Course follow-up;
2. Course -> Accommodation -> Course;
3. Accommodation -> Course -> Accommodation;
4. Scholarship second ordinal;
5. older typed ResultSet after unrelated newer results;
6. compatible constraint inheritance;
7. explicit constraint replacement;
8. no cross-domain constraint leakage;
9. clarification completion/resume;
10. explicit-request clarification interruption;
11. evicted entity clarification;
12. complete Clear Chat reset;
13. explicit entity overriding retained focus;
14. EMPTY versus INCOMPLETE;
15. child refinement preserving parent ordinals;
16. unambiguous `other` selection;
17. full Warrumbul/Scholarship/Clear spike; and
18. canonical 20-turn retention journey.

Additional tests cover deterministic ResultSet eviction, constraint overflow,
state-not-evidence, UNKNOWN missing-evidence requirements, authoritative-first
RetrievalPlan order and wire validation. The wire suite also performs 20
sequential `/api/v1/ask` requests through fresh app instances: the first omits
state, every later request sends the preceding authoritative state unchanged,
and every response is schema-validated while exercising the exact collection
bounds and deterministic entity/ResultSet eviction.

## Clear Chat

The App clears visible history and discards the client-carried object. RAG's
structured reset clears typed entities, focus, student facts, constraints,
ResultSets, selected result and pending clarification together. The next
request either omits state or sends the empty v1 state. A phrase such as `Is it
catered?` then has no Warrumbul referent and must clarify or fail safely.

## Security and authority

- Unknown fields are forbidden at every state layer.
- State version must be exactly 1.
- Types, strings, scalar ranges and collection lengths are bounded.
- Duplicate semantic identities and dangling focus/selections are invalid.
- Client ordering is canonicalised before resolution.
- Student facts carry authority `user_stated` and cannot validate as evidence.
- Evidence requires approved persisted record identity and provenance.
- The model can propose a bounded interpretation but cannot write arbitrary
  state, source authority, URLs or institutional facts.
- State/history remain excluded from factual authority and default raw logs.

## Known unsupported Day 1 cases

- Natural-language parsing into these primitives is not implemented today.
- The existing six domain query services are not yet orchestrated through the
  new state transitions, except additive validation/round-trip and pending
  clarification adaptation at the HTTP boundary.
- Legacy clarification adaptation uses a generic `select_option` intent; Day 2
  orchestration must populate the precise originating intent/slots.
- Full multi-domain alias catalogs, clarification generation, ResultSet
  production and constraint extraction remain Day 2+ work.
- No retrieval optimization, BM25/FTS, embedding change, reranking, framework
  migration, schema migration, deployment or production action is included.

## Day 2 implementation handoff candidate

Day 2 remains on hold pending PM review/freeze. After that approval, it should
implement these exact interfaces without changing the reviewed Day 1
contracts:

1. `src/askanu_rag/interpretation.py`
   - `interpret_turn(question, history, state) -> QueryInterpretation`
   - deterministic explicit identifiers first; constrained model output only
     through validated `QueryInterpretation`.
2. `src/askanu_rag/conversation_orchestrator.py`
   - `apply_interpretation(state, interpretation) -> ConversationTurn`
   - use `state_transitions.py` for all state writes, pending lifecycle,
     typed references and ResultSet selection.
3. `src/askanu_rag/retrieval_planning.py`
   - `build_retrieval_plan(interpretation, state) -> RetrievalPlan`
   - preserve exact/structured authority over semantic discovery.
4. `src/askanu_rag/evidence_selection.py`
   - `select_evidence(plan, candidates, result_set) -> EvidenceBundle`
   - rehydrate approved records and preserve canonical provenance.
5. `src/askanu_rag/main.py`
   - replace the Day 1 boundary-only state advancement with the orchestrated
     transition while preserving the additive request/response contract.
6. Extend behavioural tests rather than replacing
   `tests/test_v7_day1_state.py` and `tests/test_v7_day1_wire_contract.py`.

The App integration contract is intentionally narrow: store current-chat state,
return it unchanged, and discard it with Clear Chat. Any App-specific storage or
transport detail is Ben-owned and cannot alter these semantics.

## Author-side status

- V7 Day 1 RAG implementation: **READY FOR PM REVIEW**
- Shared conversational contracts: **READY FOR PM REVIEW**
- Day 2 RAG implementation: **HOLD pending PM review/freeze**
- Carmen-owned blockers: none identified

Passing implementation evidence does not self-approve the shared contract.
Qasim owns the final freeze, Day 1 GO/HOLD and Day 2 GO decisions.
