# V7 Day 2 context and understanding handoff

Status: **READY FOR PM REVIEW**. Final Day 2 acceptance and Day 3 GO remain
Qasim-owned.

## Architecture

`interpret_turn(question, history, state)` produces a validated
`QueryInterpretation` with separate domain, entity, intent and constraints.
It preserves explicit and inherited constraint provenance, entity/reference
origin, ambiguity, and constraint replacement/survival information.

`orchestrate_turn(...)` is the only Day 2 meaning-to-state path. It advances and
canonicalises state, applies explicit entity and constraint updates, retains
bounded user-stated context, resolves stable ResultSet ordinals, resumes or
supersedes clarification, and performs the complete Clear Chat reset.

## Deterministic rules

- Exact identifiers and the bounded safe alias `Structured Programming` outrank
  retained state. Approved spacing/case variants and explicitly tested minor
  spellings resolve without an open-ended fuzzy synonym system.
- Typed references resolve only compatible retained entities. Evicted or absent
  references clarify.
- Result ordinals use the stored retained order. `CONTINUE_RESULTS` carries the
  originating ResultSet ID; it does not rerun an unrelated discovery.
- `DATE_WINDOW` and `TIME_OF_DAY_WINDOW` inherit and replace independently.
  Domain-scoped constraints never leak across a switch.
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

## Safety and scope

No database schema, production write, deployment, indexing, scraper change,
live Rubric call, persistent profile or server-side session is introduced.

## Verification evidence

- Focused Day 2 interpretation/state/evidence tests: 19 passed.
- Frozen Day 1 state and external-wire regressions: 36 passed, 3 existing
  dependency deprecation warnings.
- Existing ask/history/routing and six-domain behavioural regressions: 268
  passed, 3 existing dependency deprecation warnings.
- Full RAG suite: 876 passed, 89 skipped, 3 existing dependency deprecation
  warnings. The skips are 88 PostgreSQL integration tests because
  `ASKANU_TEST_DATABASE_URL` was not configured and one Windows symlink test
  because the current account lacks symlink permission. Day 2 changes no DB
  contract, migration or PostgreSQL path.
- `pip check`: PASS (`No broken requirements found`).
- `compileall` for `src`, `tests` and `migrations`: PASS.
- Alembic: exactly one head, `20260921_0010`.
- `git diff --check`: PASS; Git emitted only existing LF/CRLF conversion
  notices, not whitespace errors.
