# AskANU V7 Day 3 — Retrieval and Reasoning Handoff

Status: ready for PM review; no release threshold is self-frozen here.

## Git and scope

- Branch: `carmen/v7-day3-retrieval-reasoning`
- Base: `52e84ac084433b8eb55741c3d3a55fbe2a39ae4f`
- Base includes merged RAG PRs #35 and #36.
- Alembic head: `20260921_0010`
- No migration, source, public API, conversation-state schema, deployment, live
  Rubric call, production index or production database write is part of Day 3.
- The implementation head must be taken from Git after Carmen commits; this
  handoff does not invent a future SHA.

## Frozen benchmark

The labelled, rerunnable artifact is
`benchmarks/v7_day3/benchmark.json`. Labels were written before evaluating any
pipeline. The runner is
`python -m askanu_rag.retrieval.benchmark_cli`.

The fixture is an approved-record projection used only for local ranking and
provenance checks. It is not production evidence and is never loaded by the
request path.

Coverage:

| Dimension | Distribution |
|---|---|
| Queries | 36 |
| Domains | 6 each for Courses, Scholarships, Accommodation, Jobs, Events, Support |
| Difficulty | 12 easy, 17 medium, 7 difficult |
| Route | 21 exact, 8 structured, 7 discovery |
| Answer labels | 29 CONFIRMED, 2 DERIVED, 2 PARTIAL, 3 UNKNOWN |
| ResultSet labels | 34 RESULTS, 1 EMPTY, 1 INCOMPLETE |

Every query predeclares its domain, text, query type, difficulty, route,
supported population, expected relevant record IDs, allowed source IDs, hard
constraints, AnswerState, ResultSet status, population completeness, failure
class and notes. The set covers explicit identity, natural name, facts,
prerequisites, deadlines, requirements, natural-problem wording, structured
filters, currentness, missing evidence and resolved follow-ups/ordinals.

## Current retrieval baseline configuration

The implementation was inventoried from source before optimisation.

### Request-path retrieval

- Exact Courses-family lookup uses canonical type/code/year over fresh
  repository records. Exact identities do not depend on vector similarity.
- Scholarship exact identity/title and metadata filters are deterministic.
- Jobs exact numeric identity/title, current status, closing-date and supported
  employment filters are deterministic.
- Accommodation and Support exact title and fact projection are deterministic.
- Event time-window selection is deterministic in `Australia/Canberra` and
  preserves official ANU Events versus approved Rubric source identity.
- Hard filters create the eligible population before discovery ranking. There
  is no fallback that silently drops an explicit hard constraint.

### Sparse discovery

- `LocalTfidfRetriever` is an ephemeral, local, title-plus-content cosine
  TF-IDF implementation.
- Tokens are lowercase alphabetic terms with a small fixed stop-word list.
- The default minimum score is `0.2`.
- Courses use default candidate Top-K `3`; Accommodation/Support use `5`.
- Before the measured Day 3 correction, the configured service did not run
  sparse Jobs discovery; semantic Jobs discovery required an injected vector
  retriever. Scholarship matching-style filters remain deterministic.

### Dense and hybrid capability

- A provider-neutral `EmbeddingProvider`, deterministic retrieval-unit builder,
  persisted vector repository and pgvector exact-cosine search exist.
- Retrieval units use canonical content, paragraph grouping, 2,000 characters
  per unit and at most 20 units per record by default.
- Stored-vector defaults are Top-K `5`, minimum cosine `0.35` and at most three
  units per record.
- `SharedHybridRetriever` preserves exact/structured/discovery precedence and
  uses reciprocal-rank fusion with constant `60` inside the discovery tier.
- Maximum merged candidates default to `10`.
- `create_configured_app()` does not construct or inject an embedding provider
  or vector retriever. Therefore dense and hybrid discovery are not active in
  the current configured runtime. `embedding_model` and `embedding_version`
  default to null. `DeterministicFakeEmbedder` is test-only.

### State, candidates, evidence and reasoning

- Day 2 creates a typed `QueryInterpretation`; Day 3 retrieval planning now
  keeps exact and structured steps ahead of an explicitly chosen deterministic,
  semantic-vector or hybrid discovery step.
- Candidate ranking remains separate from bounded evidence selection.
- Shared policy now derives ResultSet status only from ordered results and
  population completeness: results → RESULTS; zero results with a complete
  population → EMPTY; zero results with an incomplete population → INCOMPLETE.
- AnswerState is independently derived from approved selected evidence and
  explicit missing evidence: CONFIRMED, DERIVED, PARTIAL or UNKNOWN. State is
  never used as factual evidence.
- Retained ResultSet ordinals continue to resolve stored identity/order without
  rerunning discovery.

## Baseline results — unchanged current pipeline

The baseline was captured before implementing the bounded Support improvement.
It uses 200 in-process repetitions per query for latency. Recall is macro
average over the 35 queries with prelabelled relevant evidence; the one true
EMPTY case is excluded from recall.

| Metric | Current baseline |
|---|---:|
| Recall@1 | 78.33% |
| Recall@3 | 87.86% |
| Recall@5 | 88.57% |
| Recall@10 | 88.57% |
| Recall@20 | 88.57% |
| Selected-evidence completeness at K=5 | 88.57% |
| Selected-evidence precision proxy | 100% |
| Local retrieval p50 | 0.0002 ms |
| Local retrieval p95 | 0.0651 ms |
| Provenance checks | 100% |
| Hard-constraint checks | 100% |

Domain Recall@5 was 100% for Courses, Scholarships, Accommodation and Events,
80% for Jobs, and 50% for Support. The latency outlier was Support because it is the
only domain in this balanced fixture with three multi-record sparse-discovery
queries: Support p50 was 0.00965 ms; the other domain p50 values were 0.0002 ms.
These are local algorithm/fixture timings, not network, PostgreSQL or full-answer
latency.

Baseline failure classification:

- 27 cases: no failure;
- 5 DATA cases: personal Scholarship eligibility, Accommodation vacancy,
  incomplete Job requirements, missing Rubric organiser and missing Support
  hours; and
- 4 RETRIEVAL cases: natural Support problems for unfair assessment, financial
  hardship and international settling-in, plus Jobs topic discovery while the
  configured vector retriever was absent.

There were no evidence-selection/ranking failures once relevant evidence entered
the candidate set. The DATA cases correctly retrieved their record and remained
UNKNOWN/PARTIAL rather than being recast as no match.

## Candidate experiments

### Bounded Support expansion and local sparse Jobs fallback — implemented

Change 1: three auditable Support-only mappings append retrieval vocabulary for
unfair assessment/grade appeal, inability to afford food/rent, and international
student settling-in. Day 2's replaceable problem-domain resolver recognizes the
same bounded problems. The main orchestrator may route a non-ambiguous resolved
Support domain into the existing Support service. The expansion does not create
facts, modify source text, relax constraints or alter source authority.

Change 2: Jobs topic discovery now runs the same local sparse candidate path
inside the deterministically current/hard-filtered Jobs population and merges it
with vectors when a vector retriever is injected. Dense failure or absence no
longer removes the safe local sparse candidate path.

| Metric | Result |
|---|---:|
| Recall@1 | 89.76% |
| Recall@3 | 99.29% |
| Recall@5 / @10 / @20 | 100% |
| Selected-evidence completeness at K=5 | 100% |
| Selected-evidence precision proxy | 100% |
| Local retrieval p50 | 0.0004 ms |
| Local retrieval p95 | 0.0717 ms |
| Every domain Recall@5 | 100% |
| Provenance / hard constraints | 100% / 100% |

The Support-only intermediate reached 97.14% Recall@5 and left only the Jobs
gap. The combined implementation closes both measured gaps. The remaining five
classified cases are DATA, not retrieval defects. The final p95 delta is 0.0066
ms on a synthetic in-process fixture and is not operationally
material. The change is bounded, reversible and retains the current interface.

### Evaluation-only local BM25 — not adopted

| Metric | Result |
|---|---:|
| Recall@1 | 86.90% |
| Recall@3 | 96.43% |
| Recall@5 / @10 / @20 | 97.14% |
| Selected-evidence completeness at K=5 | 97.14% |
| Selected-evidence precision proxy | 77.19% |
| Local retrieval p50 / p95 | 0.0002 / 0.0323 ms |
| Provenance / hard constraints | 100% / 100% |

BM25 improved recall over the original TF-IDF baseline but still missed the
financial-hardship query with no lexical overlap and admitted much more noise.
Adopting this local implementation would add commodity ranking code without
beating the smaller Support-specific correction, so it remains evaluation-only.

### PostgreSQL FTS, dense pgvector, hybrid and reranking

- PostgreSQL FTS would require a database-backed benchmark and likely an index
  or migration decision; Day 3 made no migration and therefore did not claim
  comparative numbers.
- The dense/pgvector path exists but is inactive in configured runtime. No real
  embedding provider/model or production vector population was enabled, so
  fabricating dense/hybrid quality numbers would be misleading.
- Reranking is not justified while the bounded correction reaches 100% Recall@5
  and 100% precision proxy on the frozen set.
- LangChain/LlamaIndex would add dependencies and framework objects without
  replacing a measured maintenance burden. No framework or hosted service was
  adopted and no new data/trust boundary was introduced.

## Reasoning and negative-evidence safety

- Candidate retrieval and evidence selection are measured separately.
- Five missing-field cases retrieve the correct source record but retain DATA
  classification and UNKNOWN/PARTIAL semantics.
- The Jobs incomplete-source case is INCOMPLETE, not EMPTY/no jobs.
- A null Accommodation vacancy field cannot become “no rooms”.
- The one EMPTY case has an explicitly complete supported population and zero
  current matches.
- Official ANU Events and Rubric keep distinct source IDs. Similarity/rank never
  changes authority and there is no live Rubric call.
- Exact identifiers, hard filters and retained ordinals remain vector-independent.

## Proposed Day 7 numeric gates — for Qasim review, not frozen

These proposals follow the measured distribution:

1. Frozen benchmark macro Recall@5 at least 98%, with every domain at least 95%.
2. Recall@20 at least 99%; exact/structured identity cases must remain 100%.
3. Selected-evidence completeness at K=5 at least 98% and precision proxy at
   least 95%.
4. Provenance preservation and hard-constraint preservation exactly 100%.
5. Zero UNKNOWN→FALSE and INCOMPLETE→EMPTY safety regressions.
6. Frozen local candidate benchmark p95 at most 1 ms on the Day 7 runner and no
   more than 20% slower than its same-host RC baseline when both values exceed
   timer noise.

A production-like PostgreSQL candidate latency gate and end-to-end answer gate
remain HOLD until Day 7 measures those paths; this local fixture cannot justify
a network/database threshold.

## Reproduction

```powershell
python -m askanu_rag.retrieval.benchmark_cli --pipeline current --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --pipeline support-expansion --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --pipeline day3-improvement --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --pipeline bm25 --latency-repetitions 200
```

Focused behavioural coverage is in
`tests/test_v7_day3_retrieval_reasoning.py`. Full verification totals belong in
the final author handoff after the complete suite is run.

## Local verification

- Day 3 focused: 20 passed.
- Day 2 understanding regression: 27 passed.
- Day 1 state/wire regression: 36 passed.
- Transport contract: 12 passed.
- Six-domain behavioural selection: 355 passed.
- Explicit 10-turn and both 20-turn journeys: 3 passed.
- Full suite: 916 passed, 89 skipped, 3 dependency deprecation warnings.
- PostgreSQL integration: 88 skipped because
  `ASKANU_TEST_DATABASE_URL` is not configured; no PostgreSQL claim is made.
- `pip check`: no broken requirements.
- `compileall`: passed for `src`, `tests` and `migrations`.
- Alembic: one head, `20260921_0010`.
- `git diff --check`: passed.

## Deferred work

- PM/Qasim freeze of Day 7 numeric gates.
- Database-backed PostgreSQL FTS and pgvector comparison only after a bounded,
  representative approved-data benchmark and explicit migration/index decision.
- Production-like retrieval and end-to-end latency measurement.
- Day 4 work remains on hold pending Day 3 GO.
