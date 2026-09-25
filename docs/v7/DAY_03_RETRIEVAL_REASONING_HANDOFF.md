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
| Local retrieval p95 | 0.0628 ms |
| Provenance checks | 100% |
| Hard-constraint checks | 100% |

Domain Recall@5 was 100% for Courses, Scholarships, Accommodation and Events,
80% for Jobs, and 50% for Support. The latency outlier was Support because it is
the only domain in this balanced fixture with three multi-record sparse-discovery
queries: Support p50/p95 was 0.01055/0.0663 ms. These are local
algorithm/fixture timings, not network, PostgreSQL or full-answer latency.

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
| Local retrieval p95 | 0.0737 ms |
| Every domain Recall@5 | 100% |
| Provenance / hard constraints | 100% / 100% |

The Support-only intermediate reached 97.14% Recall@5 and left only the Jobs
gap. The combined implementation closes both measured gaps. The remaining five
classified cases are DATA, not retrieval defects. The final p95 delta is 0.0109
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
| Local retrieval p50 / p95 | 0.0002 / 0.0321 ms |
| Provenance / hard constraints | 100% / 100% |

BM25 improved recall over the original TF-IDF baseline but still missed the
financial-hardship query with no lexical overlap and admitted much more noise.
On the development set it did not beat the smaller Support-specific correction.
The independent holdout below materially changes the confidence in that tuned
comparison, but does not by itself approve BM25 for production.

## Auditable local candidate-retrieval latency

All values below are local, in-process candidate-retrieval timings over the
frozen 36-query fixture, with 200 repetitions per query and K. Each K row
therefore contains 7,200 samples. They exclude HTTP transport, PostgreSQL,
embedding calls, evidence rendering and answer generation.

| K | Baseline p50 / p95 (ms) | Final p50 / p95 (ms) | BM25 p50 / p95 (ms) |
|---:|---:|---:|---:|
| 1 | 0.0001 / 0.0634 | 0.0004 / 0.0737 | 0.0002 / 0.0320 |
| 3 | 0.0001 / 0.0631 | 0.0004 / 0.0738 | 0.0002 / 0.0319 |
| 5 | 0.0001 / 0.0625 | 0.0004 / 0.0725 | 0.0002 / 0.0317 |
| 10 | 0.0001 / 0.0622 | 0.0004 / 0.0730 | 0.0002 / 0.0318 |
| 20 | 0.0002 / 0.0628 | 0.0004 / 0.0737 | 0.0002 / 0.0321 |

There is no material K-growth trend in this bounded fixture: exact and
structured routes slice an already-filtered tuple, while sparse discovery ranks
the same small eligible population before applying K. The observed p95 ranges
are timer-noise scale, not evidence of an operational K penalty.

At K=20, interaction classes are mutually exclusive. `follow_up` means one of
`resolved_follow_up`, `resolved_time_refinement`, `retained_resultset_ordinal`
or `continue_resultset`; other exact routes are `lookup`; all remaining
structured/discovery routes are `discovery`.

| Interaction | Baseline p50 / p95 (ms) | Final p50 / p95 (ms) | BM25 p50 / p95 (ms) |
|---|---:|---:|---:|
| Lookup | 0.0001 / 0.0002 | 0.0004 / 0.0005 | 0.0001 / 0.0002 |
| Discovery | 0.0002 / 0.0653 | 0.0005 / 0.0775 | 0.0002 / 0.0349 |
| Follow-up/refinement | 0.0001 / 0.0002 | 0.0004 / 0.0005 | 0.0001 / 0.0002 |

The final domain distribution at K=20 was:

| Domain | p50 (ms) | p95 (ms) |
|---|---:|---:|
| Accommodation | 0.0004 | 0.0653 |
| Courses | 0.0004 | 0.0506 |
| Events | 0.0004 | 0.0004 |
| Jobs | 0.0004 | 0.0568 |
| Scholarships | 0.0004 | 0.0007 |
| Support | 0.01275 | 0.0808 |

Support is the only material domain outlier because three queries rank a
five-record sparse population and apply bounded query expansion. Jobs gains a
sparse discovery call in the final pipeline, which explains its p95 movement
from 0.0002 ms at baseline to 0.0568 ms. Both remain far below the proposed
local absolute gate.

No end-to-end `/api/v1/ask` latency was measured. The latest explicit-PM-GO Day
3 contract requires retrieval p50/p95, K behaviour and domain outliers, and says
end-to-end latency must be reported separately *if measured*. It therefore does
not require another end-to-end run before PR review. A production-like
PostgreSQL and end-to-end answer distribution remains a Day 7 gate-setting
dependency, not a result that this local fixture can support.

## Evidence metric definitions and denominators

- **Selected-evidence completeness at K=5** is the macro fraction of labelled,
  non-empty queries for which every prelabelled expected record ID appears in
  the first five selected candidate IDs. The true EMPTY case is excluded from
  the denominator. Baseline is 31/35 (88.57%), final is 35/35 (100%), and BM25
  is 34/35 (97.14%).
- **Selected-evidence precision proxy** is micro-averaged
  `sum(relevant selected IDs) / sum(all selected IDs)` over the first five
  selected candidates for all 36 queries. A zero-candidate query adds zero to
  both numerator and denominator. Baseline is 41/41 (100%), final is 45/45
  (100%), and BM25 is 44/57 (77.19%). It is a labelled-fixture noise proxy, not
  a claim about generated-answer precision.

These calculations are emitted from the same frozen labels and candidate lists
used for Recall@K, so their numerators and denominators are directly auditable.

## Frozen unseen holdout — generalization check

`benchmarks/v7_day3/holdout.json` was prelabelled and committed before any
retriever was run against it. Freeze commit:
`25d3145d8d7d8ab3ebb0125c6dc72164e80b72d4`; artifact SHA-256:
`13b061af57a6c2730dc7434f325996f0e2ce536ceddf00281545a89f58bf65b6`.
The labels and queries were not changed after evaluation, and no retrieval rule
was modified in response to the results.

The holdout has 24 non-duplicate queries, four per domain, with 6 easy, 12
medium and 6 difficult cases. It reuses unchanged records from the development
corpus but has zero exact query-text overlap with the 36-query development set.
Its three natural Support problems deliberately avoid every currently encoded
Support expansion phrase.

Each pipeline used the same records, eligible populations, labels, K values and
evaluation function. Latency uses 200 local in-process repetitions per query
and K.

| Holdout metric | Original baseline | Final Day 3 | BM25 experiment |
|---|---:|---:|---:|
| Recall@1 | 67.36% | 67.36% | 79.86% |
| Recall@3 | 75.00% | 75.00% | 95.83% |
| Recall@5 | 75.00% | 75.00% | 95.83% |
| Recall@10 | 75.00% | 75.00% | 95.83% |
| Recall@20 | 75.00% | 75.00% | 95.83% |
| Selected-evidence completeness@5 | 18/24 (75.00%) | 18/24 (75.00%) | 23/24 (95.83%) |
| Precision proxy | 23/23 (100%) | 23/23 (100%) | 28/43 (65.12%) |
| Provenance preservation | 100% | 100% | 100% |
| Hard-constraint preservation | 100% | 100% | 100% |
| Local candidate p50 / p95 | 0.0002 / 0.0743 ms | 0.0004 / 0.0825 ms | 0.0002 / 0.0396 ms |
| Failure counts | DATA 4, NONE 14, RETRIEVAL 6 | DATA 4, NONE 14, RETRIEVAL 6 | DATA 4, NONE 19, RETRIEVAL 1 |

The four DATA cases were retrieved correctly by every pipeline: Scholarship
personal eligibility, Accommodation current vacancy, incomplete Job
requirements and missing Rubric organiser. They remain DATA rather than being
misclassified as retrieval misses.

The final pipeline's six RETRIEVAL failures are:

- Scholarship equity discovery using “money is tight” wording;
- Accommodation music-space preference phrased as “practise music”;
- Jobs discovery phrased as backend Python services; and
- all three unseen Support problems: disagreeing with an assignment result,
  inability to make ends meet, and difficulty adjusting after arriving from
  abroad.

Final per-domain Recall@5 is Courses 100%, Events 100%, Accommodation 75%, Jobs
75%, Scholarships 75% and Support 25%. The original baseline has the identical
distribution: the tuned Support expansion and Jobs fallback do not materially
outperform it on these unseen queries.

BM25 reaches 100% Recall@5 in every domain except Support at 75%. It retrieves
the unseen assessment, overseas-settling, Jobs, Scholarship and Accommodation
cases, but misses the financial paraphrase and adds 15 irrelevant selected
candidates, reducing the precision proxy to 65.12%.

Generalization decision:

1. The final Day 3 pipeline does **not** materially outperform the original
   baseline on this unseen holdout.
2. BM25 materially outperforms both on unseen Recall@5, 95.83% versus 75%, but
   its candidate noise is materially worse, 65.12% versus 100% precision proxy.
3. The current Support mappings are tuned phrase corrections, not demonstrated
   semantic generalization. The Jobs sparse fallback exists, but the current
   TF-IDF threshold/ranking does not generalize to this unseen Jobs wording.
4. The development-set improvement remains valid for those labelled queries,
   but it is not sufficient evidence to freeze the retrieval architecture.
5. A separately designed hybrid current+BM25 candidate/selection experiment is
   justified. This sealed holdout must not be used to tune or then prove that
   experiment; it needs a new development set and a later untouched validation
   set.
6. No production migration is justified yet. BM25 remains evaluation-only and
   the retrieval architecture decision is HOLD pending further PM-directed
   evaluation.

### PostgreSQL FTS, dense pgvector, hybrid and reranking

- PostgreSQL FTS would require a database-backed benchmark and likely an index
  or migration decision; Day 3 made no migration and therefore did not claim
  comparative numbers.
- The dense/pgvector path exists but is inactive in configured runtime. No real
  embedding provider/model or production vector population was enabled, so
  fabricating dense/hybrid quality numbers would be misleading.
- The holdout now justifies evaluating a bounded current+BM25 candidate union
  with an explicit evidence-selection/noise control. It does not justify
  implementing or tuning that experiment on this sealed holdout.
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

The unseen final pipeline fails the proposed Recall@5 and evidence-completeness
gates. These values therefore remain proposals only and are not ready for Qasim
to freeze until the generalization gap is addressed on separate data.

| Metric | Measured baseline | Measured final | Proposed gate | Rationale / scope |
|---|---:|---:|---:|---|
| Macro Recall@5 | 88.57% | 100% | at least 98% | Allows at most a small aggregate regression while preserving the measured improvement. |
| Per-domain Recall@5 | 50%–100% | 100% each | at least 95% each | Prevents a strong macro score from hiding one weak domain. |
| Macro Recall@20 | 88.57% | 100% | at least 99% | Required evidence should almost always enter the candidate set by K=20. |
| Exact/structured identity correctness | 100% | 100% | exactly 100% | Deterministic identity and filters must not depend on ranking. |
| Selected-evidence completeness@5 | 31/35 (88.57%) | 35/35 (100%) | at least 98% | Reliable labelled-fixture evidence-selection measure. |
| Selected-evidence precision proxy | 41/41 (100%) | 45/45 (100%) | at least 95% | Allows limited candidate noise without hiding a material selection regression. |
| Provenance / hard-constraint preservation | 100% / 100% | 100% / 100% | exactly 100% / 100% | These are safety invariants, not tunable quality metrics. |
| UNKNOWN→FALSE / INCOMPLETE→EMPTY regressions | 0 / 0 | 0 / 0 | exactly 0 / 0 | Missing evidence must never become negative truth. |
| Local candidate retrieval p95 at K=20 | 0.0628 ms | 0.0737 ms | at most 1 ms | Wide absolute margin for the frozen local fixture while still catching algorithmic blow-ups. |
| Same-host local p95 regression | reference | +17.36% (+0.0109 ms) | at most 20% when both measurements exceed timer noise | A relative release-candidate guard; sub-resolution changes are judged by the absolute gate. |

No generated-answer reasoning-quality percentage is proposed: this fixture has
reliable record-level evidence labels and semantic safety assertions, but no
independently scored answer corpus. The proposed measurable reasoning controls
are therefore selected-evidence completeness/precision plus the exact safety
invariants above, rather than a fabricated answer-quality number.

A production-like PostgreSQL candidate latency gate and end-to-end answer gate
remain HOLD until Day 7 measures those paths; this local fixture cannot justify
a network/database threshold.

## Reproduction

```powershell
python -m askanu_rag.retrieval.benchmark_cli --pipeline current --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --pipeline support-expansion --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --pipeline day3-improvement --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --pipeline bm25 --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --benchmark benchmarks/v7_day3/holdout.json --pipeline current --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --benchmark benchmarks/v7_day3/holdout.json --pipeline day3-improvement --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --benchmark benchmarks/v7_day3/holdout.json --pipeline bm25 --latency-repetitions 200
```

Focused behavioural coverage is in
`tests/test_v7_day3_retrieval_reasoning.py`; frozen holdout invariants and
observed comparison results are covered in `tests/test_v7_day3_holdout.py`.
Full verification totals belong in the final author handoff after the complete
suite is run.

## Local verification

- Frozen unseen holdout: 8 passed.
- Day 3 focused: 20 passed.
- Day 2 understanding regression: 27 passed.
- Day 1 state/wire regression: 36 passed.
- Transport contract: 12 passed.
- Six-domain behavioural selection: 355 passed.
- Explicit 10-turn and three 20-turn journeys: 4 passed.
- Full suite: 924 passed, 89 skipped, 3 dependency deprecation warnings.
- PostgreSQL integration: 88 skipped because
  `ASKANU_TEST_DATABASE_URL` is not configured; no PostgreSQL claim is made.
- `pip check`: no broken requirements.
- `compileall`: passed for `src`, `tests` and `migrations`.
- Alembic: one head, `20260921_0010`.
- `git diff --check`: passed.

## Deferred work

- PM decision on a new, separately developed current+BM25 hybrid experiment;
  the sealed holdout cannot become its tuning set.
- PM/Qasim freeze of Day 7 numeric gates.
- Database-backed PostgreSQL FTS and pgvector comparison only after a bounded,
  representative approved-data benchmark and explicit migration/index decision.
- Production-like retrieval and end-to-end latency measurement.
- Day 4 work remains on hold pending Day 3 GO.
