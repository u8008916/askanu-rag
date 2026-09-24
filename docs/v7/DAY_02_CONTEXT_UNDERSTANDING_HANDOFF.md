# V7 Day 2 context and understanding handoff

Status: **HOLD PENDING PM RE-REVIEW**. The accepted core Day 2 architecture is
unchanged; the four targeted PR #35 corrections are implemented and awaiting
Qasim's confirmation. Day 3 remains HOLD.

## Architecture

`interpret_turn(question, history, state)` produces a validated
`QueryInterpretation` with separate domain, entity, intent and constraints.
It preserves explicit and inherited constraint provenance, entity/reference
origin, ambiguity, and constraint replacement/survival information.

`orchestrate_turn(...)` is the only Day 2 meaning-to-state path. It advances and
canonicalises state, applies explicit entity and constraint updates, retains
bounded user-stated context, resolves stable ResultSet ordinals, resumes or
supersedes clarification, and performs the complete Clear Chat reset.

Canonical identities enter through an injected `EntityCatalogue`; exact
identifiers and canonical names are therefore supplied by the approved data
boundary rather than an exhaustive Python alias table. Bounded safe aliases and
typos remain separate understanding-layer configuration. An injected
`ProblemDomainResolver` complements strong lexical signals with deterministic
problem-language rules and returns ambiguity for clarification.

## Deterministic rules

- Exact identifiers and canonical names such as `Structured Programming`
  outrank retained state. Approved spacing/case variants and explicitly tested
  bounded aliases resolve without an open-ended fuzzy synonym system.
- Typed references resolve only compatible retained entities. Evicted or absent
  references clarify.
- Result ordinals use the stored retained order. `CONTINUE_RESULTS` carries the
  originating ResultSet ID; it does not rerun an unrelated discovery.
- `DATE_WINDOW` and `TIME_OF_DAY_WINDOW` inherit and replace independently.
  Domain-scoped constraints never leak across a switch.
- Explicit split temporal information removes overlapping legacy
  `temporal_window` authority. A recognised independent legacy date or time is
  converted to its split form and preserved.
- User-stated international/program context is marked `user_stated`; it cannot
  become institutional evidence.
- An explicit new entity/request supersedes pending clarification. A bounded
  clarification response resumes the saved operation.

## Retrieval handoff

Day 2 constructs only the existing `RetrievalPlan` contract using exact,
structured or deterministic-discovery steps. `EvidenceBundle` construction
accepts only already-selected approved evidence. Candidate ranking, Top-K,
BM25/FTS, embedding/provider changes, reranking and framework/service migration
are intentionally deferred to Day 3.

## Unsupported or ambiguous cases

- No open-ended fuzzy matching or model-authored permanent aliases.
- No reconstruction of evicted entities or ResultSets.
- No factual claim from conversation state or user-stated context.
- No full scholarship eligibility engine.
- No new retrieval algorithm or source authority.

## Targeted correction acceptance

- Injected canonical catalogue coverage spans Course, Scholarship, Job,
  Residence, Event and Support without changing the safe-alias fixtures.
- "I think I was graded unfairly on an assignment, who should I talk to?"
  resolves to Support; conflicting problem-language signals clarify.
- The existing 10-turn journey and a new deterministic 20-turn lifecycle both
  exercise the accepted shared state semantics.
- Legacy combined temporal state normalises deterministically when explicit
  split date/time information arrives, with no duplicate temporal authority.

## Safety and scope

No database schema, production write, deployment, indexing, scraper change,
live Rubric call, persistent profile or server-side session is introduced.

## Verification evidence

- Focused Day 2 interpretation/state/evidence tests: 27 passed, 3 existing
  dependency deprecation warnings.
- Frozen Day 1 state and external-wire regressions: 36 passed, 3 existing
  dependency deprecation warnings.
- Existing ask/history/routing and six-domain behavioural regressions: 268
  passed, 3 existing dependency deprecation warnings.
- Full RAG suite: 884 passed, 89 skipped, 3 existing dependency deprecation
  warnings. The skips are 88 PostgreSQL integration tests because
  `ASKANU_TEST_DATABASE_URL` was not configured and one Windows symlink test
  because the current account lacks symlink permission. Day 2 changes no DB
  contract, migration or PostgreSQL path.
- `pip check`: PASS (`No broken requirements found`).
- `compileall` for `src`, `tests` and `migrations`: PASS.
- Alembic: exactly one head, `20260921_0010`.
- `git diff --check`: PASS; Git emitted only existing LF/CRLF conversion
  notices, not whitespace errors.
