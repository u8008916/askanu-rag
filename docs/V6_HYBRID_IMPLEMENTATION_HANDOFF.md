# AskANU V6 shared hybrid retrieval implementation handoff

Date: 15 September 2026

Owner: Carmen — RAG/backend

Approval: Qasim's approved V6 implementation instruction, relayed by the user

Status: local implementation for review; no production migration/deployment

## 1. Repository state

- Branch: `codex/v6-day11-retrieval-audit`
<<<<<<< HEAD
- Base and current HEAD before human review: `daa5a4afabfa40a42253fc29c9b98e2fa7001c3a`.
- The implementation is an uncommitted working-tree diff so a human can review
  it before commit, as required by `docs/AI_SETUP.md`.
- Final review scope: 47 changed paths (31 modified, 16 untracked), including
  the already completed V6 hybrid work and this Courses-family addendum.
=======
- PR #25 head before this correction: `a3a6a43baaffe72fc61efc175c2c1db36a030c3a`.
- The approved V6 implementation is already present at that head. The targeted
  Carmen-owned review correction remains an uncommitted seven-file working-tree
  diff for human review, as required by `docs/AI_SETUP.md`.
>>>>>>> ed0f1b7 (fix: harden Jobs and Scholarship retrieval)
- The two pre-existing stashes were not changed.

## 2. Architecture implemented

The request path remains:

```text
POST /api/v1/ask
-> current-session resolver
-> domain/intent and exact identities
-> hard structured filters
-> exact/structured + existing sparse + optional shared dense candidates when configured
-> precedence merge and source-level dedupe
-> evidence/provenance gate
-> existing synthesis/validated AskResponse
```

Dense vectors discover candidates only. A hit becomes usable only after it is
joined and rehydrated from the current approved `source_records` row. IDs,
codes, dates, current/open state, eligibility filters and source-backed factual
fields remain deterministic authority.

There is one shared infrastructure layer. No per-domain vector table/service or
LangChain dependency was added.

## 3. Retrieval units and chunk policy

`RetrievalUnitBuilder` emits one `whole` unit containing canonical `content`
when that text is at most the configured 2,000 characters. Longer
records split deterministically on paragraph boundaries; an individually long
paragraph is split on word boundaries. Unit IDs are `chunk-0001`,
`chunk-0002`, and so on. A configurable maximum of 20 units prevents unbounded
records.

Every unit carries:

- its exact `source_record_id`;
- the source record's `content_hash`;
- a stable unit ID; and
- a SHA-256 `retrieval_content_hash` over the exact embedded unit text.

The same unit ID/hash/model/effective-version is not embedded again, even when
older hashes for that unit are retained. Changed content or an explicit
model/retrieval-policy version rollout is eligible for regeneration. Display
`title` is not a separate embedding input because source freshness hashes only
canonical `content`.

## 4. Embedding boundary

`EmbeddingProvider` separates document batches from query embedding and owns
the model/version identity. Optional dimension validation is centralized.
`DeterministicFakeEmbedder` provides stable, secret-free test vectors and is
explicitly not a production provider.

No production provider/secret/model/dimension was frozen in the approval. The
runtime therefore does not silently enable a provider. `EMBEDDING_MODEL`,
`EMBEDDING_VERSION` and `EMBEDDING_DIMENSION` document the future persisted-row
configuration, but production provider construction remains a Qasim-approved
integration step.
The effective stored version combines the provider version with the retrieval-unit policy and chunk bounds, while the embedding model identity remains stored separately in `embedding_model`.

## 5. Migration graph and persistence

The append-only graph remains linear:

```text
20260914_0004
-> 20260915_0005 shared hybrid embeddings/resources/Jobs v2
-> 20260915_0006 Courses-family/Subplan contract
-> 20260915_0007 nullable-array contract consistency
-> 20260916_0008 frozen Day 12 Accommodation/Support contract (head)
```

Revision `0005`:

1. adds nullable Jobs `role_requirements` with a `null` backfill;
2. adds approved Accommodation/Support source/domain/identity/metadata checks;
3. enables pgvector with `CREATE EXTENSION IF NOT EXISTS vector`; and
4. creates shared `source_record_embeddings`.

The vector table supports one source record to many retrieval units. Its
composite primary key covers source record, unit identity, retrieval-content
hash, embedding model and embedding version. It keeps both source and unit
hashes, timestamps, a source-record foreign key with intentional `ON DELETE
CASCADE`, and a dimension-neutral `vector` column. No HNSW/IVFFlat index is
created; exact pgvector cosine distance is the bounded MVP.

Its downgrade refuses while Accommodation/Support rows exist, drops the vector
table, preserves the potentially pre-existing pgvector extension, removes the
new domain constraints, removes the nullable Jobs key, and restores the v1 Jobs
checks.

Revision `0006` leaves `0005` unchanged. It safely normalizes only the exact
previously accepted uppercase Course/Program URL form to the frozen lowercase
path form and refuses unexpected existing URLs. It expands Courses entity,
code, identity, URL, metadata-type and uniqueness checks for all five entity
types. It recreates `course_program_records` as Course + Program only with the
existing top-level `OFFSET 0` read-only guard. Downgrade refuses while Subplan
rows exist rather than hiding or coercing them. If downgrade proceeds, it
restores the `0005` schema shape but deliberately leaves normalized lowercase
URLs unchanged; that database shape and compatible RAG URL model accept them.
Earlier revisions, including
`0004` and `0005`, are unchanged.

Revision `0007` makes nullable array checks consistent with the validated model
contract. Revision `0008` leaves every earlier migration unchanged and replaces
only the provisional Accommodation/Support checks. Its preflight is deliberately
read-only: exact frozen rows proceed, while known provisional or unknown rows
raise an operator-facing error before any constraint is dropped. No lossy JSON
rewrite is attempted. Downgrade refuses while either resource domain has rows.

No production database migration was run.

## 6. Indexing and freshness

`EmbeddingIndexService` is an explicit service primitive, not a request-time
reindexer or scheduler. It:

- consumes the existing `NEW`/`CHANGED`/`UNCHANGED` and
  `PENDING`/`FAILED`/`INDEXED` lifecycle;
- skips an unchanged unit when its current hash exists among retained rows at
  the same current source hash, model and effective version;
- supports explicit version rollout/retry;
- persists the complete embedding batch and matching source index-state update
  in one repository transaction;
- uses a source `record_id + content_hash` compare-and-set so an old task cannot
  mark changed content indexed;
- marks a matching source row failed when generation fails without a usable
  prior index;
- preserves the prior `INDEXED` version when an unchanged-content target-version
  rollout fails, so current LKG evidence remains usable only through its old
  version;
- compare-and-sets failure on source hash, starting index state and version so
  a late failed worker cannot clobber a concurrent success; and
- keeps prior vector rows as last-known-good evidence. Historical retention is
  intentional and V6 defines no garbage-collection policy.

Semantic queries require current source hash, requested model/version and
`INDEXED`. `MISSING` source observations may continue to use the preserved
last-known-good row/vector when all those facts still match. Unknown database
commit outcomes are not followed by a blind duplicate write.

The local handoff loader now validates the shared `CommonRecord` boundary for a
single file or direct `records/` directory, allowing richer Courses-family,
Scholarship and Jobs records to enter the same repository and retrieval-unit
indexing path. The legacy Course-only loader remains available for narrow
callers. No parser logic or new metadata/API field was introduced.

## 7. Vector query and hybrid merge

`PersistedSemanticRetriever` embeds one query and calls the shared repository
with domain, optional prefiltered record IDs, `top_k`, threshold and per-source
unit bounds. `PostgresVectorRepository` performs an exact cosine query, joins
to `source_records`, rehydrates validated records, groups multiple unit hits by
source record, keeps the best source score and stable unit order, and returns a
bounded source-level result.

`SharedHybridRetriever` does not pretend exact/structured/sparse/dense scores
share one calibrated scale. It applies tiers:

1. exact identity;
2. deterministic structured result; and
3. sparse/dense discovery.

It deduplicates by `record_id`, combines sparse/dense details for the same
discovery candidate, and uses deterministic reciprocal-rank fusion with a
dual-signal advantage. Sparse and dense raw scores are never compared across
signals. Stable record ID breaks ties and the final list is capped. Threshold
rejection happens before merge.

## 8. Domain results

### Courses family

- Exact codes, exact names, year/session filters and factual projection remain
  unchanged and authoritative.
- The frozen 2026 universe is 500 Courses, 393 Programs, 109 Majors, 126
  Minors and 128 Specialisations: 1,256 total. Independent 99% gates are 495,
  390, 108, 125 and 127; identity/provenance correctness is 100%.
- Major, Minor and Specialisation are first-class `courses` records from
  `courses_programs_and_courses`, never Programs or separate-domain records.
- Identity is `<CODE>_<YEAR>` and
  `courses:<entity_type>:<CODE>_<YEAR>`. Logical uniqueness includes entity
  type, so equal codes in different entity types remain distinct.
- Metadata codes are uppercase while the exact HTTPS canonical URL path code is
  lowercase. Host, year, entity type and path code must match, with no port,
  query, fragment or trailing slash.
- `CourseMetadata` adds `description`, `learning_outcomes` and structured
  `corequisites`. `ProgramMetadata` adds `overview`, `program_requirements`,
  `admission_requirements` and `prerequisites`.
- `SubplanMetadata` preserves nullable `career`, `units`, `subplan_type`,
  `overview`, `learning_outcomes`, faithful source `requirements`,
  `relevant_degrees` and `other_information`.
- Source-present Program `Minors`, `Elective Study` and `Study Options` remain
  in deterministic content. Courses-family content is source-backed section
  text, never model-authored or title/code-only.
- Exact Subplan code/name/year resolution, filtering, clarification labels and
  evidence projection use the same Courses retrieval path.
- Existing local TF-IDF remains the default sparse signal.
- When configured, persisted dense candidates augment the semantic route and dedupe with TF-IDF
  for all five entity types through the same embedding table.
- `involve/involves/involving` is now recognized for the approved functional
  programming discovery example.
- Explicit codes never call or yield to vector retrieval.
- Academic year is not converted into invented effective dates. Complex rules
  remain faithful stored text; no degree-audit engine was introduced.

Required source-present field coverage is at least 99% independently per
family. A genuinely absent ANU field is not a failure; a required published
field omitted or altered is. Workload, fees, prescribed readings and other
non-frozen fields are not silently added to the mandatory denominator.

The compatibility view deliberately exposes Course and Program only. Subplans
persist in `source_records` and participate in retrieval/hybrid indexing, but
do not leak into `course_program_records`.

### Scholarships

- Open/closed, student type, study level/stage, area and other existing filters
  are applied before dense search.
- Semantic topical intent such as `interested in` or `related to` ranks only
  within the hard-filtered pool.
- A closed scholarship cannot return for an explicit open query.
- Direct questions for `featured`, `application_required`, `study_stage`,
  `student_type`, `study_level`, `area_of_study`, `value`, `selection_basis`,
  `opening_date`, `closing_date`, and source status use a one-fact deterministic
  projection. A missing/null requested fact returns `insufficient_evidence`
  with the selected Scholarship's official stored source; unrelated facts are
  not substituted.
- Existing deterministic clarification/eligibility language is preserved.

### Jobs

- Exact numeric ID/title, current/closed, Canberra closing date, ordering and
  structured facts remain deterministic.
- Generic current-list intent remains deterministic and does not require
  vectors. Topic intent (`related to`, `about`, `focused on`, `involves`) enters
  semantic Jobs discovery even without the literal phrase `current jobs`.
- Semantic unavailability, errors, weak hits, or no hits fail closed with
  `insufficient_evidence`; they never fall back to arbitrary current Jobs.
- Current/open filtering and explicit employment type, location, category,
  classification, exact salary wording, closing information, and direct
  `role_requirements` constraints occur before semantic role/topic ranking.
- Semantic ranking sees the complete hard-filtered current candidate pool; the
  public `/jobs/current` limit remains unchanged and the final chat candidate
  cap is applied only after ranking.
- `role_requirements: list[str] | null` is implemented. A non-empty stored list
  is rendered as source wording with the stored canonical source; null/empty
  returns `insufficient_evidence`.
- No requirement is inferred from title, classification, summary, category,
  salary or employment type.
- Position Description fetching/ingestion was not implemented.

### Accommodation

- Shared exact-title, sparse and dense discovery routes are implemented over
  `accommodation_anu_study` records.
- Source-backed category, location, catering options, audiences, advertised
  rate/cost period, room-level rate/contract/inclusions/other fees, features,
  overview, accessibility, application, eligibility and structured contact can
  be projected without breaking their associations.
- Answers label rates as advertised information, not a guarantee.
- A stored source-backed `vacancy_status` is reported exactly. Null vacancy
  returns `insufficient_evidence`; the application link is navigation only and
  is never treated as evidence of availability.

### Support

- Shared exact-title, sparse and dense routing is implemented over the approved
  ANUSA Student Assistance source.
- Published category, purpose, audiences, structured contact, hours, access,
  cost, nested topics and external referrals can be projected.
- Missing hours/contact/location are not invented.
- Topic links remain inside the approved ANUSA Student Assistance boundary;
  referrals are labelled as navigation to external services, not as separate
  ANUSA services.
- Responses make no clinical diagnosis, emergency-coverage claim,
  response-time promise, 24/7 claim or professional-availability assurance.
- Additional ANU Support pages are not silently approved; only the existing
  active source-registry boundary is accepted.

Cheap no-database plausibility guards run before each Jobs, Scholarships,
Accommodation and Support service. A routed domain failure fails closed rather
than falling through to another domain. Existing pending-clarification routing
is preserved. Specific resource-name misses abstain; only genuinely broad
resource discovery may offer a catalog clarification.

## 9. Jobs requirements source distribution

An exact frozen Jobs-universe distribution cannot be produced from the current
repositories: the RAG repository contains no frozen real Jobs snapshot, and
Will's merged/main and Day 10 branch contain only synthetic/sample fixtures plus
a bounded live-run report. Therefore the exact frozen denominator is unknown,
with zero real frozen records available to classify. Inventing a `55`-record
denominator would be incorrect.

For a clearly separate live diagnostic on 15 September 2026, the official
[`Current opportunities`](https://jobs.anu.edu.au/jobs/search?subscribe=true)
page stated `Displaying 1 - 30 of 60 in total`. Of the two current detail pages
already manually inspected from that live universe:

| Category | Exact inspected count |
|---|---:|
| direct-page requirements | 1 (`563412`) |
| Position-Description-only requirements | 1 (`563693`) |
| absent/unclear | 0 |
| unresolved/not inspected | 58 |

That is an exact accounting of the two inspected pages plus the live page's 60
total, not an exact frozen-universe distribution. Will must supply a frozen
60-record (or later reviewed) canonical-page snapshot/normalized export to
complete the requested distribution. PD contents remain untouched.

## 9.1 Files changed and purpose

The targeted PR #25 correction changes exactly:

- `src/askanu_rag/job_queries.py`: general topic routing, fail-closed semantic
  behavior, relevance threshold use, and conservative stored-value filters.
- `src/askanu_rag/scholarship_queries.py`: deterministic one-fact projection
  and selected-record null/missing abstention.
- `src/askanu_rag/main.py`: passes the existing configured semantic threshold
  into the Jobs service; no public API field or status changes.
- `tests/test_jobs.py` and `tests/test_scholarships.py`: targeted review-finding
  regression cases.
- `docs/V6_HYBRID_IMPLEMENTATION_HANDOFF.md` and
  `docs/V6_DAY11_RETRIEVAL_AUDIT.md`: corrected review status and evidence.

The already-committed PR implementation includes the broader files below:

- `src/askanu_rag/models/records.py` and model exports: frozen Course, Program
  and Subplan metadata plus type-sensitive identity/canonical URL validation.
- `src/askanu_rag/retrieval/{identifiers,catalog,repository,postgres}.py` and
  exports: generic five-entity exact lookup without changing the legacy Course
  method or shared-table authority.
- `src/askanu_rag/query_planner.py`, `hybrid_queries.py`, and `main.py`: explicit
  Subplan recognition, exact/name/filter/semantic routes, corequisite and
  requirements projection, and safe ambiguity labels.
- `migrations/versions/20260915_0006_courses_family_subplans.py`: append-only
  constraints/index/view update after the untouched `0005`.
- `fixtures/day2_course_program_records.json` and
  `fixtures/day5_course_program_records.json`: canonical Course/Program URL path
  codes corrected to lowercase; no external/source facts added.
- `tests/test_courses_family.py`, `test_courses_family_migration.py`, and
  narrow existing-test updates: model, URL, identity, retrieval, migration and
  compatibility regression coverage.
- `docs/DATA_SCHEMA.md`, `DECISION_LOG.md`, `DEPLOYMENT.md`, this handoff, the
  historical audit and `README.md`: synchronized contract/release evidence.
- The earlier V6 `0005`, shared retrieval units, embedding/vector/hybrid layer,
  Jobs, Scholarships and Accommodation/Support files remain part of the same
  uncommitted review tree and retain their purposes documented above.

## 10. Evaluation coverage

Retrieval-level tests cover:

- valid Major/Minor/Specialisation records, type-sensitive uniqueness and
  exact lowercase canonical URLs;
- Course corequisites and expanded Program/Subplan source-field projection;
- exact Subplan code/name/year resolution, semantic type filtering and
  shared-pipeline provenance;
- Course+Program compatibility-view inclusion and all Subplan exclusions;
- exact ID/code and exact-title paths remaining vector-independent;
- semantic paraphrase/topic discovery;
- structured open/current filters before semantic ranking;
- two discovery candidates and deterministic order;
- exact/structured precedence over higher-scoring fuzzy candidates;
- weak-score rejection;
- duplicate sparse/vector candidates;
- provenance after merge/source rehydration;
- source and retrieval-unit hash freshness;
- version-triggered regeneration and unchanged-content skip;
- multiple unit hits deduped to one source record;
- stable tie behavior and candidate/top-k bounds;
- Jobs requirements positive/null behavior;
- general Jobs topic routing and semantic fail-closed behavior;
- Jobs location, employment type, category, classification, salary, closing,
  and direct-requirements hard filters, including semantic combinations;
- deterministic Scholarship fact projection and missing-fact abstention;
- Accommodation vacancy/cost/facility/application behavior; and
- Support fuzzy routing and missing-hours behavior.

The existing full deterministic/conversation/security suites remain the
regression gate. Real-provider retrieval quality and threshold tuning remain
blocked until a production embedding provider and representative frozen corpus
are approved.

## 11. Verification evidence

Exact Courses-family/model/repository/migration command:

```text
.venv\Scripts\python.exe -m pytest tests/test_courses_family.py tests/test_courses_family_migration.py tests/test_exact_retrieval.py tests/test_handoff_loading.py tests/test_hybrid_planner.py tests/test_course_api.py tests/test_postgres_repository.py tests/test_migrations.py -o addopts= --basetemp <workspace-temp>
```

Result: `238 passed, 1 skipped` (the existing Windows symlink-privilege case).

Exact shared hybrid/vector/freshness command:

```text
.venv\Scripts\python.exe -m pytest tests/test_shared_retrieval.py tests/test_postgres_vector_repository.py tests/test_index_lifecycle.py tests/test_v6_migration.py -o addopts= --basetemp <workspace-temp>
```

Result: `34 passed`.

Exact Scholarships/Jobs/conversation/resources regression command:

```text
.venv\Scripts\python.exe -m pytest tests/test_scholarships.py tests/test_jobs.py tests/test_conversation.py tests/test_resources.py tests/test_domain_routing.py -o addopts= --basetemp <workspace-temp>
```

Result: `188 passed`.

Full suite:

```text
.venv\Scripts\python.exe -m pytest --basetemp <workspace-temp>
```

Result: `571 passed, 60 skipped` (`631 collected`). Fifty-nine skips are guarded PostgreSQL
integration cases because no disposable local test URL is configured; the
remaining skip is the existing Windows symlink-privilege case.
The three warnings are existing dependency deprecations.

Also passed:

```text
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m compileall -q src tests migrations
.venv\Scripts\python.exe -m alembic upgrade head --sql
git diff --check
```

Offline Alembic SQL reaches the single head `20260915_0006`. This is compilation
evidence only, not a PostgreSQL 18 or live Cloud SQL claim.

The targeted Carmen-owned review findings requested for PR #25 are resolved in
the local correction diff and verified by the results above. This statement
does not clear the production/provider/PostgreSQL gates below.

### Day 11 second pass and PR #27 review correction

The previous reviewed PR head was `a6f75e0`. Its final pre-correction evidence
was `584 passed, 61 skipped, 3 warnings`, with Alembic head
`20260915_0007`.

The PR #27 review correction adds success-path compare-and-set protection on
the task's starting source hash, index status and embedding version. A late v2
success can no longer overwrite an already committed v3 state, and PostgreSQL
rolls back the stale worker's vector writes in the same transaction. Focused
lifecycle/vector repository verification passed with `40 passed`. The complete
suite after the correction passed with `588 passed, 61 skipped, 3 warnings`.

The following checks also passed after the correction:

```text
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m compileall -q src tests migrations
.venv\Scripts\python.exe -m alembic heads
git diff --check
```

`alembic heads` returned the existing single head `20260915_0007`. No final
post-correction commit SHA is claimed here. No real embedding provider,
database operation, migration change, deployment or production data was used.

## 12. Cross-repository dependencies and release gates

Will must:

1. add the nullable Jobs v2 key to every normalized Job and only populate it
   from explicitly labelled canonical-page requirement/selection text;
2. include that text in canonical content/hash where source-backed;
3. leave PD-only and absent cases null;
4. deliver frozen current-Jobs data for the exact distribution audit; and
5. keep Accommodation and Support normalized records synchronized with Qasim's
   frozen Day 12 contract and provide the staged writer evidence required by the
   release gate; and
6. synchronize all five Courses-family entity outputs, exact uppercase metadata
   codes/lowercase URLs, new metadata fields and deterministic content sections,
   then supply independent 99% source-present field/entity coverage evidence.

Qasim must review/freeze the production embedding provider, model, version,
retrieval-policy version, dimension, credentials and worker
invocation/ownership, then run PostgreSQL 18
upgrade/downgrade, compatibility-view and role/grant gates before any deploy.

No source policy, secret, IAM, Cloud SQL, Cloud Run, Scheduler, production data
or Position Description boundary was changed in this task.

The pgvector table/indexer/query code is implemented and covered by local fake
and SQL-boundary tests, but it is not wired into production startup. No live
provider was called. Events remain planned/reserved contract vocabulary and are
not part of the current `CommonRecord` runtime union or this implementation.

## 13. Explicit confirmations

- Migration `20260914_0004` was not edited.
- Position Description ingestion was not implemented.
- AskResponse fields and statuses were unchanged.
- Existing Courses TF-IDF was preserved.
- No LangChain dependency was added.
- No production migration or deployment was performed.
- No fake Courses, Accommodation, Support or Jobs production data was added.
