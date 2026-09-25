# AskANU V7 Day 3 — Retrieval and Reasoning Handoff

Status: BM25 candidate retrieval implemented from the PM-frozen decision; ready
for PM review. Day 4 remains on HOLD. No release gate is self-frozen here.

## Git and scope

- Branch: `carmen/v7-day3-retrieval-reasoning`
- Base: `52e84ac084433b8eb55741c3d3a55fbe2a39ae4f`
- Previous reviewed branch head before this correction:
  `71e545fe769714247438310dd1641e01fc0c4322`
- Base includes merged RAG PRs #35 and #36.
- Alembic head: `20260921_0010`.
- No migration, source contract, public API, conversation-state schema,
  deployment, live Rubric call, production index or production database write is
  part of Day 3.
- The final implementation head is reported from Git after the commit; this
  document does not invent a future SHA.

## PM-frozen architecture decision

The selected V7 candidate retriever is the exact repository-owned BM25
implementation measured below. The tuned bounded TF-IDF correction is retained
only as historical benchmark evidence and is not the selected architecture.
There is no current+BM25 hybrid experiment and the sealed holdout is not used for
post-hoc tuning.

Exact selected configuration:

- local, ephemeral Python implementation; no external retrieval dependency;
- `k1=1.2`, `b=0.75`;
- Unicode `casefold()` followed by `[a-z0-9]+` tokenization;
- title, newline and canonical content concatenation;
- no stop-word removal, stemming or field weighting;
- every finite score greater than zero is eligible;
- score descending, then canonical `record_id` ascending for deterministic ties;
- candidate Top-K 5 on the request path;
- raw BM25 score is an internal ordering signal, not normalized confidence or
  factual authority.

The same `LocalBm25Retriever` implementation is called by the benchmark adapter
and the configured runtime. Courses, Scholarships, Jobs, Accommodation and
Support use it for discovery. Events remains deterministic. Each domain applies
its existing currentness, identity and hard-constraint filters before ranking;
returned IDs are rehydrated only from that eligible stored-source snapshot.
Exact and structured routes retain precedence. An injected vector retriever
remains compatible but is not configured or enabled by this change.

Deferred, not selected: hybrid retrieval, learned or heuristic reranking, real
embeddings, PostgreSQL FTS, retrieval frameworks and production vector
enablement.

## Frozen benchmark artifacts

The labelled development artifact is
`benchmarks/v7_day3/benchmark.json`. It contains 36 queries: six per domain,
12 easy / 17 medium / 7 difficult, 21 exact / 8 structured / 7 discovery, and
29 CONFIRMED / 2 DERIVED / 2 PARTIAL / 3 UNKNOWN labels. The one true EMPTY
case is excluded from recall.

The unseen artifact is `benchmarks/v7_day3/holdout.json`. It was labelled and
committed before any retriever was run against it:

- freeze commit: `25d3145d8d7d8ab3ebb0125c6dc72164e80b72d4`;
- SHA-256: `13b061af57a6c2730dc7434f325996f0e2ce536ceddf00281545a89f58bf65b6`;
- 24 non-duplicate queries, four per domain, 6 easy / 12 medium / 6 difficult;
- zero exact query-text overlap with the development set;
- unchanged records, labels, eligibility rules and evaluation function;
- no query, label, retrieval rule or BM25 setting was changed after evaluation.

Both artifacts are approved-record projections for local ranking, provenance
and safety checks. Neither is loaded by the request path or treated as production
evidence.

## Quality results

### Development set

| Metric | Original TF-IDF baseline | Historical bounded correction | Selected BM25 |
|---|---:|---:|---:|
| Recall@1 | 78.33% | 89.76% | 86.90% |
| Recall@3 | 87.86% | 99.29% | 96.43% |
| Recall@5 / @10 / @20 | 88.57% | 100% | 97.14% |
| Selected-evidence completeness@5 | 31/35 (88.57%) | 35/35 (100%) | 34/35 (97.14%) |
| Candidate precision proxy | 41/41 (100%) | 45/45 (100%) | 44/57 (77.19%) |
| Provenance preservation | 100% | 100% | 100% |
| Hard-constraint preservation | 100% | 100% | 100% |
| Failure counts | DATA 5 / NONE 27 / RETRIEVAL 4 | DATA 5 / NONE 31 | DATA 5 / NONE 30 / RETRIEVAL 1 |

Selected BM25 Recall@5 is 100% for Courses, Scholarships, Accommodation,
Jobs and Events, and 83.33% for Support. It misses the financial-hardship query
that has no lexical overlap. The bounded correction reaches 100% here because it
contains three development-specific Support vocabulary mappings; the untouched
holdout shows those mappings do not generalize.

### Frozen unseen holdout

| Metric | Original TF-IDF baseline | Historical bounded correction | Selected BM25 |
|---|---:|---:|---:|
| Recall@1 | 67.36% | 67.36% | 79.86% |
| Recall@3 / @5 / @10 / @20 | 75.00% | 75.00% | 95.83% |
| Selected-evidence completeness@5 | 18/24 (75.00%) | 18/24 (75.00%) | 23/24 (95.83%) |
| Candidate precision proxy | 23/23 (100%) | 23/23 (100%) | 28/43 (65.12%) |
| Provenance preservation | 100% | 100% | 100% |
| Hard-constraint preservation | 100% | 100% | 100% |
| Failure counts | DATA 4 / NONE 14 / RETRIEVAL 6 | DATA 4 / NONE 14 / RETRIEVAL 6 | DATA 4 / NONE 19 / RETRIEVAL 1 |

Selected BM25 Recall@5 is 100% for Courses, Scholarships, Accommodation,
Jobs and Events, and 75% for Support. It retrieves the unseen assessment,
overseas-settling, Jobs, Scholarship and Accommodation cases and misses the
financial paraphrase. The original and bounded pipelines have the same 75%
holdout Recall@5; BM25 reaches 95.83% without holdout tuning.

The 65.12% holdout candidate precision proxy is a material noise warning. The
benchmark recorded no EVIDENCE_SELECTION failure because expected evidence was
present in the selected IDs, but it does not independently score final generated
answer correctness or prove that extra candidates are harmless. Candidate IDs
and ordering are benchmarked; current downstream evidence selection is bounded
Top-K rehydration plus domain-specific source-backed fact projection, not a
learned reranker. Noise remains an explicit monitoring and later evaluation item.

### Metric definitions

- **Recall@K** is macro recall over queries with at least one labelled relevant
  record: for each query, relevant IDs retrieved in the first K divided by all
  relevant IDs, then averaged. The true EMPTY query is excluded.
- **Selected-evidence completeness@5** is the fraction of labelled non-empty
  queries for which every expected relevant record ID occurs in the first five
  candidate IDs.
- **Candidate precision proxy** is micro-averaged
  `sum(relevant selected IDs) / sum(all selected IDs)` over the first five
  candidate IDs for every query. It measures labelled candidate noise, not
  generated-answer precision.
- **Failure class** distinguishes missing source data (DATA), candidate miss
  (RETRIEVAL), evidence/selection failure and final reasoning failure. The
  current artifacts provide reliable candidate labels and safety assertions,
  but not an independently scored answer corpus.

## Auditable local candidate-retrieval latency

These values use 200 in-process repetitions per query and K. They include local
candidate selection over the fixture only. They exclude HTTP transport,
PostgreSQL, embeddings, evidence rendering and answer generation. They must not
be described as `/api/v1/ask` end-to-end latency.

### Development set

| K | Baseline p50 / p95 (ms) | Selected BM25 p50 / p95 (ms) |
|---:|---:|---:|
| 1 | 0.0002 / 0.0709 | 0.0002 / 0.0388 |
| 3 | 0.0002 / 0.0773 | 0.0002 / 0.0383 |
| 5 | 0.0002 / 0.0813 | 0.0002 / 0.0398 |
| 10 | 0.0002 / 0.0763 | 0.0002 / 0.0390 |
| 20 | 0.0002 / 0.0739 | 0.0002 / 0.0402 |

At K=20, selected BM25 interaction p50/p95 is lookup 0.0002/0.0002 ms,
discovery 0.0002/0.0454 ms and follow-up/refinement 0.0002/0.0003 ms.

Selected BM25 domain p50/p95 at K=20:

| Domain | p50 / p95 (ms) |
|---|---:|
| Accommodation | 0.0002 / 0.0391 |
| Courses | 0.0002 / 0.0403 |
| Events | 0.0002 / 0.0003 |
| Jobs | 0.0002 / 0.0370 |
| Scholarships | 0.0002 / 0.0002 |
| Support | 0.00625 / 0.0458 |

### Frozen unseen holdout

| K | Baseline p50 / p95 (ms) | Selected BM25 p50 / p95 (ms) |
|---:|---:|---:|
| 1 | 0.0002 / 0.1030 | 0.0002 / 0.0445 |
| 3 | 0.0002 / 0.1065 | 0.0002 / 0.0448 |
| 5 | 0.0002 / 0.1049 | 0.0002 / 0.0492 |
| 10 | 0.0002 / 0.1052 | 0.0002 / 0.0493 |
| 20 | 0.0002 / 0.1055 | 0.0002 / 0.0459 |

At K=20, selected BM25 interaction p50/p95 is lookup 0.0002/0.0003 ms,
discovery 0.0389/0.0545 ms and follow-up/refinement 0.0002/0.0003 ms.

Selected BM25 domain p50/p95 at K=20:

| Domain | p50 / p95 (ms) |
|---|---:|
| Accommodation | 0.0002 / 0.0446 |
| Courses | 0.0002 / 0.0422 |
| Events | 0.0002 / 0.0003 |
| Jobs | 0.0002 / 0.0358 |
| Scholarships | 0.0003 / 0.0423 |
| Support | 0.0425 / 0.0567 |

There is no material K-growth trend in these small bounded populations. Support
has the visible p50 outlier because each discovery case ranks its five-record
population; its 0.0567 ms holdout p95 is also the maximum selected-BM25 domain
p95 but remains timer-noise-scale local evidence. At K=20, BM25 p95 is 45.6%
lower than baseline on development (0.0402 versus 0.0739 ms) and 56.5% lower on
holdout (0.0459 versus 0.1055 ms).

No end-to-end `/api/v1/ask` latency was measured. The Day 3 contract requires
candidate p50/p95, K behaviour and domain outliers and requires end-to-end values
to be labelled separately if measured. A production-like PostgreSQL candidate
distribution and end-to-end answer distribution remain Day 7 gate-setting work;
the local fixture cannot justify those thresholds.

## Reasoning and negative-evidence safety

- Candidate rank never changes source authority or creates facts.
- Five development DATA cases and four holdout DATA cases retrieve their source
  evidence and remain UNKNOWN/PARTIAL as labelled.
- Incomplete Jobs evidence remains INCOMPLETE, not EMPTY/no jobs.
- Null Accommodation vacancy cannot become “no rooms”.
- EMPTY requires a successfully evaluated complete supported population with
  zero matches.
- Official ANU Events and Rubric retain distinct source IDs; there is no live
  Rubric call.
- Exact identifiers, hard filters and retained ResultSet ordinals remain
  independent of BM25.
- An unresolved explicitly named Support service fails closed instead of being
  replaced by a generic lexical service match.

## Proposed Day 7 numeric gates — for Qasim review, not self-frozen

| Metric | Measured selected BM25 | Proposed gate | Rationale / scope |
|---|---:|---:|---|
| Macro Recall@5 | development 97.14%; holdout 95.83% | at least 95% on each frozen suite | Preserves measured generalization without pretending the missed lexical paraphrase is solved. |
| Exact/structured identity correctness | 100% | exactly 100% | Identity and filters must never depend on ranking. |
| Provenance preservation | 100% on both suites | exactly 100% | Safety invariant. |
| Hard-constraint preservation | 100% on both suites | exactly 100% | Safety invariant. |
| UNKNOWN→FALSE / INCOMPLETE→EMPTY regressions | 0 / 0 | exactly 0 / 0 | Missing evidence must not become negative truth. |
| Candidate precision proxy | development 77.19%; holdout 65.12% | at least 60% on each suite and no more than 5 percentage-point regression from the frozen selected-BM25 reference on the same suite | Monitoring floor for candidate noise; not answer precision. |
| Selected-evidence completeness@5 | development 97.14%; holdout 95.83% | monitor at least 95% on each suite | Candidate label coverage; not a mature answer-quality score. |
| Local candidate p95 at K=5 | development 0.0398 ms; holdout 0.0492 ms | at most 1 ms | Wide absolute guard against local algorithmic blow-ups. |
| Same-host local p95 regression | BM25 is below baseline on both suites | at most 20% when both values exceed timer noise | Relative guard; use the absolute gate for sub-resolution changes. |

No independent evidence-selection/reasoning-quality threshold is proposed or
frozen. The benchmark can audit candidate completeness, candidate noise,
provenance and negative-evidence semantics, but it does not provide a separately
scored final-answer corpus. Inventing an answer-quality percentage would overstate
the evidence. Qasim owns any final gate freeze.

## Reproduction

```powershell
python -m askanu_rag.retrieval.benchmark_cli --pipeline current --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --pipeline day3-improvement --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --pipeline bm25 --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --benchmark benchmarks/v7_day3/holdout.json --pipeline current --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --benchmark benchmarks/v7_day3/holdout.json --pipeline day3-improvement --latency-repetitions 200
python -m askanu_rag.retrieval.benchmark_cli --benchmark benchmarks/v7_day3/holdout.json --pipeline bm25 --latency-repetitions 200
```

Focused runtime equivalence is in `tests/test_v7_day3_bm25_runtime.py`.
Development metrics and safety semantics are covered by
`tests/test_v7_day3_retrieval_reasoning.py`; sealed holdout invariants and exact
observed comparisons are covered by `tests/test_v7_day3_holdout.py`.

## Local verification

- Focused BM25 runtime, Day 3 and frozen holdout: 32 passed.
- Day 2 context/understanding: 27 passed.
- Day 1 state and wire contract: 36 passed.
- Transport contract: 12 passed.
- Six-domain runtime behaviour: 232 passed.
- Explicit 10-turn and three 20-turn journeys: 4 passed.
- Focused hard constraints, provenance/source authority and
  UNKNOWN/EMPTY/INCOMPLETE selection: 58 passed.
- Full suite: 928 passed, 89 skipped, 3 dependency deprecation warnings. The
  skips include 88 PostgreSQL integration cases because
  `ASKANU_TEST_DATABASE_URL` is not configured; they are not counted as passes
  and no PostgreSQL runtime claim is made.
- `pip check`: no broken requirements.
- `compileall`: passed for `src`, `tests` and `migrations`.
- Alembic: one head, `20260921_0010`.
- `git diff --check`: passed.

## Deferred work

- Qasim review/freeze of proposed Day 7 numeric gates.
- Independent downstream evidence-selection/final-answer evaluation, using new
  data rather than tuning the sealed holdout.
- Hybrid retrieval, reranking, real embeddings, PostgreSQL FTS and retrieval
  frameworks unless a later reviewed benchmark demonstrates need.
- Production-like PostgreSQL candidate and `/api/v1/ask` end-to-end latency.
- Day 4 remains on HOLD pending Day 3 review.
