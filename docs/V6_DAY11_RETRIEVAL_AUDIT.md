# V6 Day 11 — first-three-domain retrieval and contract audit

Date: 15 September 2026

Owner: Carmen — RAG/backend

Status: historical pre-implementation audit, followed by the approved V6 local
implementation on this branch. See `V6_HYBRID_IMPLEMENTATION_HANDOFF.md` for
the implemented state and verification evidence.

## 0. Implementation update

Qasim subsequently approved the shared retrieval-unit/vector/hybrid design,
Jobs `role_requirements`, Accommodation/Support scope, and the five-entity
Courses-family addendum. Revisions `20260915_0005` and `20260915_0006` plus the
shared services now implement those approved local/test boundaries. The audit
below is intentionally retained as the before-state and gap record; statements
labelled proposal/not implemented/unsupported-today describe that historical
snapshot, not the branch's final state. The current contract and verification
are in `V6_HYBRID_IMPLEMENTATION_HANDOFF.md`. No production migration or
deployment was performed.

The implementation review subsequently corrected details the design-only
sections did not settle: historical unit hashes are retained and checked as
sets; retrieval units embed only canonical hash-covered `content`; the
effective embedding version includes retrieval/chunk policy; sparse and dense
signals use rank fusion rather than raw-score comparison; and Jobs semantic
ranking runs over the complete current hard-filtered pool before the final cap.
Cheap domain plausibility guards also remove the eager cross-domain reads
identified in this audit.

The PR #25 targeted correction additionally separates generic current Jobs
listing from semantic/topic discovery, routes general Jobs topic wording
without requiring the literal phrase `current jobs`, and makes semantic
unavailability/weakness fail closed. It applies explicit stored-value Jobs
filters before semantic ranking and adds deterministic single-fact Scholarship
projection with source-preserving null/missing abstention. These Carmen-owned
review findings are resolved locally; production/provider and live PostgreSQL
gates remain unchanged.

Production pgvector execution remains un-wired pending Qasim approval of the
provider/model/dimension, credentials, effective policy version, worker owner,
thresholds and rollout. No PostgreSQL 18/live-vector claim is made. Events are
reserved/planned only and are not in the current `CommonRecord` runtime union.
Revision `0006` production planning additionally requires a read-only URL-shape
preflight; downgrade restores schema shape but intentionally does not reverse
lowercase URL normalization.

## 1. Scope and result

The original Tuesday audit was limited to Courses, Scholarships and Jobs plus
preparation of the shared semantic/hybrid design. The later approved
implementation instruction added Accommodation and Support; Events remains out
of scope.

The current implementation is a safe vertical slice, not a 99% capability
implementation. Exact identifiers, several structured facts, clarification,
missing-evidence behavior and provenance are strong. The principal 99% blockers
are:

1. The original audit did not model Majors, Minors, Specialisations, Program
   rules or Course corequisites; the frozen `0006` addendum now models these.
   Broad source-backed data and degree-audit/honours engines remain out of scope.
2. Scholarship degree relevance, application method and duration/tenure remain
   absent contract/source gaps. Already-frozen facts now have deterministic
   direct-question projection and null/missing abstention.
3. Jobs `role_requirements` and the requested source-backed structured filters
   are implemented. Broad real-corpus coverage and Position Description source
   policy remain separate data/approval gates.
4. The original audit had only an ephemeral local TF-IDF baseline. Shared
   pgvector persistence/query, retrieval units and hybrid merge now exist;
   production provider/model/dimension and worker deployment remain unfrozen.

Every gap below has one primary classification:

- **SOURCE/DATA GAP** — the approved normalized records or broad entity set do
  not yet contain the required evidence.
- **SHARED CONTRACT GAP** — the cross-repo persisted shape/source policy must be
  reviewed before the capability can be implemented safely.
- **RAG/RETRIEVAL GAP** — the approved stored evidence exists, but the current
  RAG planner/filter/answer path does not use it for that capability.

## 2. Repository and contract state

- Audit branch: `codex/v6-day11-retrieval-audit`.
- `origin/main`: `daa5a4afabfa40a42253fc29c9b98e2fa7001c3a`.
- Starting HEAD: the same merged-main SHA.
- Starting worktree: clean.
- Merged plan: Day 11 is first-three-domain 99% retrieval audit/contract gap
  triage; Day 12 is Accommodation + Support capability implementation.
- Current Alembic head after the approved addenda: `20260915_0006`.
- Shared persistence: `source_records`, with the frozen 16 top-level fields.
- Current approved entity types: `course`, `program`, `scholarship`, `job`.
- Local evidence breadth is deliberately small: Day 5 has five Courses plus one
  Program, and Day 9 has three synthetic Scholarships. RAG has no committed
  Jobs fixture. These fixtures cannot demonstrate 99% entity coverage.

Source-of-truth documents reviewed: `AGENTS.md`, `docs/AI_SETUP.md`,
`docs/API_CONTRACT.md`, `docs/DATA_SCHEMA.md`,
`docs/CONVERSATION_CONTRACT.md`, `docs/SECURITY_BASELINE.md`,
`docs/DECISION_LOG.md`, and the V5 Courses/freshness, Scholarships and Jobs
handoffs.

## 3. Real request and evidence path

The actual `/api/v1/ask` flow is:

```text
AskRequest validation
  -> resolve_current_session (only when the repository is a CatalogReader)
  -> JobQueryService
  -> ScholarshipQueryService
  -> HybridQueryService for Courses/Programs
     (or legacy CourseQueryService for a non-catalog repository)
  -> controlled insufficient_evidence/off_topic fallback
```

The route order is visible in `src/askanu_rag/main.py:223-300`. Conversation
history resolves constrained meaning only. Each factual path rereads repository
records. The in-memory repository rehydrates typed records; PostgreSQL selects
all 16 stored columns from `source_records` and revalidates them.

- Courses/Programs: `plan_query` chooses one mutually exclusive route (`exact`,
  `name`, `metadata`, `semantic` or `unsupported`). `HybridQueryService`
  retrieves current stored rows, projects allowed evidence, optionally calls
  Gemini, validates the answer, and maps sources from stored records.
- Scholarships: deterministic title/slug matching and current-message metadata
  filters over the approved Scholarship snapshot. Answers are deterministic;
  Gemini is not used.
- Jobs: deterministic exact ID/title, current/date/employment-type logic and
  stored-field answers. Gemini and vector retrieval are not used.
- Provenance: all three domains build `Source` from the retrieved row's
  `record_id`, `source_id`, `title`, `canonical_url` and `domain`. Neither
  similarity results nor Gemini can supply facts or URLs directly.

## 4. Current retrieval architecture matrix

| Capability | Courses / Programs | Scholarships | Jobs |
|---|---|---|---|
| Exact lookup | Code and exact normalized title; year ambiguity preserved | Exact slug/entity ID and normalized title | Numeric Job ID and exact normalized title |
| Structured filters | Entity type, academic year, session | Status, featured, application-required, student type, study level/stage, area | Current status/date and exact Fixed Term membership |
| Temporal/relational rules | Explicit year/session only | Stored status only; dates do not derive status | Canberra currentness, dated-first ordering, numeric ID tie-break |
| TF-IDF / lexical fallback | Yes, local ephemeral `title + content` cosine | No | No |
| Dense vector retrieval | No | No | No |
| Hybrid merge | No; route selection is exclusive | No | No |
| Reranking | TF-IDF score then stable record ID on semantic route only | No relevance reranker; stable record order | Deterministic closing date/ID order only |
| Provenance mapping | Rehydrate stored candidate and map stored source | Stored records only | Stored records only |
| Router integration | Yes, third domain handler | Yes, second domain handler | Yes, first domain handler |

The class name `HybridQueryService` should not be read as evidence of a full
hybrid system. It provides deterministic-first routing and a bounded sparse
fallback, but it does not merge deterministic and semantic candidate sets.

## 5. Semantic/vector current-state audit

### Database and storage

At the original audit snapshot (before revisions `0005`/`0006`):

- pgvector is not enabled by any migration.
- No vector column, embedding table, HNSW index or IVFFlat index exists.
- `embedding_version` and `index_status` are lifecycle scaffolding on
  `source_records`; they are not connected to stored vectors.
- Migration tests explicitly assert that current migrations do not claim or
  enable pgvector.

### Embedding generation

- No production dense-embedding generator exists.
- No embedding model/provider/dimension is configured.
- LangChain is neither installed nor imported.
- The only similarity input is local TF-IDF over whole-record
  `title + "\n" + content`; metadata and chunks are not separately embedded.
- The TF-IDF vectors are created in memory for each request and are never
  persisted.

### Freshness and index lifecycle

- `index_lifecycle.py` validates/plans `NEW/CHANGED -> PENDING`, explicit retry,
  stale-result rejection by `record_id + content_hash`, success/failure and
  preservation behavior.
- No queue poller, worker, database writer or embedding provider consumes those
  decisions.
- `NEW/CHANGED -> PENDING` therefore does not trigger real embedding today.
- `UNCHANGED` preserves lifecycle fields by contract, but there is no stored
  vector to preserve in this repo.
- `INDEXED`/`FAILED` are not connected to a real worker.
- Failed/MISSING source refresh behavior preserves last-known-good records and
  lifecycle evidence, but no production vector evidence currently exists.

### Semantic query and router

- `LocalTfidfRetriever.search` implements bounded sparse cosine ranking with
  `top_k` and `min_score`.
- There is no pgvector similarity SQL, dense `semantic_search` repository
  method or persistent-index implementation.
- The Courses path validates hit IDs against its prefiltered approved rows and
  rehydrates the full row, preserving provenance and rejecting unknown IDs,
  non-finite scores and stale persistent hits if such a retriever is injected.
- Dense semantic retrieval is not merely unwired: its generator, storage,
  query adapter and production provider do not exist.
- Scholarships and Jobs have no lexical or semantic runtime integration.

Summary: **vector/index lifecycle scaffolding and a Courses-only local sparse
baseline exist, but production embedding generation, vector storage/query,
worker execution and shared hybrid routing are not implemented.**

## 6. Courses / Programs capability audit

| Capability | Current behavior and evidence | Existing coverage | Gap classification | Owner/dependency | Blocks 99%? |
|---|---|---|---|---|---:|
| Exact course code | Deterministic code/year lookup; no vector fallback | `test_course_api`, `test_exact_retrieval`, `test_hybrid_planner` | — supported | Carmen | No |
| Exact program code | Deterministic code/year lookup | `test_exact_retrieval` | — supported | Carmen | No |
| Exact course/program name | Exact normalized title over current catalog; duplicates/year siblings clarify | `test_hybrid_planner` | — supported | Carmen | No |
| Course overview | Stored bounded content excerpt; optional grounded Gemini | overview/synthesis safety tests | — supported for stored content | Will data breadth | No for behavior |
| Semantic topic/synonym discovery | Courses-only TF-IDF finds shared words but cannot provide dense semantic synonym recall | sparse ranking/low-score tests | **RAG/RETRIEVAL GAP** | Carmen after shared semantic approval | Yes |
| Prerequisites | Exact course path reads stored `prerequisites`; null abstains | COMP1110 and null-evidence tests | — supported | Carmen/Will | No |
| Corequisites | No approved metadata key or planner fact | none | **SHARED CONTRACT GAP** | Qasim + Will field inventory | Yes |
| Incompatibilities | Planner projects stored string | hybrid planner tests | — supported | Carmen/Will | No |
| Assumed knowledge | Planner projects stored string | hybrid planner tests | — supported | Carmen/Will | No |
| Units / credit value | `units` is stored but not a query fact or deterministic answer projection | schema tests only | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Offerings / session / term | Explicit supported sessions filter stored offerings; ambiguous/unknown abstains | session and missing-metadata tests | — supported for current vocabulary | Carmen/Will | No |
| Delivery mode | Stored but not a query fact/answer projection | schema tests only | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Course location | No approved course metadata field | none | **SHARED CONTRACT GAP** | Qasim + Will | Yes |
| Can-I-take using published rules | Guided clarification exists, but no bounded rule explanation combines prerequisites/corequisites/incompatibilities/assumed knowledge | guided-card tests only | **RAG/RETRIEVAL GAP** | Carmen after contract/data coverage | Yes |
| Course comparison | Multiple exact entities can be retrieved, but the service deliberately does not claim comparison semantics | set-shaped safety test | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Program / degree requirements | Program v1 has units/duration/delivery/outcomes, not requirement structure | program schema/code tests | **SHARED CONTRACT GAP** | Qasim + Will | Yes |
| Major requirements | Frozen `major` entity and source-backed `requirements` | focused contract tests | **IMPLEMENTED CONTRACT; DATA GAP** | Will | Yes |
| Minor requirements | Frozen `minor` entity and source-backed `requirements` | focused contract tests | **IMPLEMENTED CONTRACT; DATA GAP** | Will | Yes |
| Specialisation requirements | Frozen `specialisation` entity and source-backed `requirements` | focused contract tests | **IMPLEMENTED CONTRACT; DATA GAP** | Will | Yes |
| What counts toward a program | No rule/group/credit relation contract | none | **SHARED CONTRACT GAP** | Qasim + Will | Yes |
| Study-plan questions | No program-rule/relationship evidence model | guided clarification only | **SHARED CONTRACT GAP** | Qasim + Will | Yes |
| Honours/pathway information | Conservative guided clarification only; no pathway evidence model | guided-card safety tests | **SHARED CONTRACT GAP** | Qasim + Will | Yes |
| Year-aware/historical | Explicit year and multi-year ambiguity work if rows exist; local breadth is tiny | multi-year tests | **SOURCE/DATA GAP** | Will broad/historical collection | Yes |
| Ambiguity handling | Multiple entities/years clarify; no ranking guesses | planner/conversation tests | — supported | Carmen | No |
| Unknown identifier | Exact misses abstain and never fall back to fuzzy/vector | exact/planner tests | — supported | Carmen | No |
| Missing evidence | Null/missing requested field returns controlled insufficient evidence with source when appropriate | course API/hybrid tests | — supported | Carmen | No |

The former entity-model blocker is resolved by distinct `major`, `minor` and
`specialisation` types. They must never be disguised as Programs. Broad source
data and richer relationship/degree-audit semantics remain separate work.

## 7. Scholarships capability audit

| Capability | Current behavior and evidence | Existing coverage | Gap classification | Owner/dependency | Blocks 99%? |
|---|---|---|---|---|---:|
| Broad find/filter | Explicit source-supported filters combine with AND; broad unqualified request clarifies | filter/clarification tests | — supported | Carmen | No |
| Exact scholarship lookup | Exact slug and normalized title over fresh snapshot | repository/title tests | — supported | Carmen | No |
| International/domestic | Exact stored `student_type` membership | refinement/filter tests | — supported | Will breadth | No for behavior |
| Study level | Exact stored list; only frozen Undergraduate/Bachelor normalization | filter tests | — supported | Carmen/Will | No |
| Study stage | Exact stored list | filter tests | — supported | Will breadth | No |
| Field/area | Exact stored `area_of_study` membership | filter tests | — supported | Will breadth | No |
| Topic/synonym discovery | No lexical or semantic path beyond exact stored filter wording | none | **RAG/RETRIEVAL GAP** | Carmen after shared semantic approval | Yes |
| Degree/program relevance | No degree/program relation field | none | **SHARED CONTRACT GAP** | Qasim + Will | Yes |
| Eligibility explanation | Stored official eligibility text may be shown | eligibility tests | — supported when present | Will completeness | No for behavior |
| “Am I eligible?” language | Explicitly refuses personal verdict while showing official evidence | eligibility safety tests | — supported | Carmen | No |
| Closing deadline | Stored closing date is rendered; missing remains unknown | date/missing tests | — supported | Carmen/Will | No |
| Opening date | Stored but not rendered or selected by intent | schema/missing tests only | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Open/closed status | Exact stored status filter; dates do not invent state | status/filter tests | — supported | Carmen/Will | No |
| Value | Rendered when stored | direct-title tests | — supported | Carmen/Will | No |
| Application required flag | Filterable only for the literal phrase; not rendered as requested information | schema/filter coverage | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Application method | No method/instructions/application URL contract | none | **SHARED CONTRACT GAP** | Qasim + Will | Yes |
| Selection basis | Stored but not projected into answers | schema coverage only | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Duration / tenure | No approved metadata field | none | **SHARED CONTRACT GAP** | Qasim + Will | Yes |
| Comparison | Multiple results can be listed; no explicit comparison plan/output | none | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Broad clarification | Offers current stored options and supports first/second/label/ID | pending-scope tests | — supported | Carmen | No |
| Missing deadline/eligibility | Omits unknown fact; does not invent deadline/verdict | missing-evidence tests | — supported | Carmen | No |
| Closed exclusion | `open` hard filter excludes stored closed rows | open/featured test | — supported | Carmen | No |
| No match | Does not relax valid filters; returns insufficient evidence | no-match tests | — supported | Carmen | No |
| Multi-result refinement | Immediate current-message filters refine pending scope; no profile persistence | continuity tests | — supported | Carmen | No |
| Broad entity coverage | Local fixture contains only three synthetic rows; live breadth was not inspected in this audit | fixture/tests | **SOURCE/DATA GAP** | Will + Qasim live evidence | Yes |
| Broad-corpus query cost | Every Scholarship handler call loads the complete Scholarship snapshot before domain recognition; filtering is in application memory | repository/routing tests | **RAG/RETRIEVAL GAP** | Carmen | Yes at broad scale |

Structured Scholarship filters remain authoritative. Future semantic retrieval
may rank only inside the already-filtered candidate set; it must never reinsert
a closed or otherwise hard-filtered row.

## 8. Jobs capability audit

| Capability | Current behavior and evidence | Existing coverage | Gap classification | Owner/dependency | Blocks 99%? |
|---|---|---|---|---|---:|
| Current Jobs | Stored `current` plus Canberra closing-date rule, then order/limit | repository/API/PostgreSQL tests | — supported | Carmen/Will | No |
| Exact numeric ID | Exact stored entity lookup; no fuzzy fallback | Jobs tests | — supported | Carmen | No |
| Exact normalized title | Case/whitespace exact match; duplicates clarify | Jobs tests | — supported | Carmen | No |
| Category | Stored and available after exact selection, but not filterable/queryable | metadata tests only | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Location | Stored and rendered, but not a hard list filter | exact/current tests | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Employment type | Exact Fixed Term list filter only; other stored types are not parsed from questions | Fixed Term tests | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Classification | Stored/rendered, not filterable | exact/current tests | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Salary | Stored source wording is rendered for selected/current rows; salary constraints/comparison are unsupported | exact/current tests | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Closing soon | Recognized as current listing and benefits from deadline ordering, but has no explicit bounded horizon | list tests | **RAG/RETRIEVAL GAP** | Carmen + Qasim meaning decision | Yes |
| Closing date | Stored wording/date is rendered without invention | Jobs tests | — supported | Carmen/Will | No |
| Current/closed status | Stored status plus date rule; null/closed/past excluded | Jobs tests | — supported | Carmen/Will | No |
| Background/degree relevance | Current normalized Job content contains listing labels/summary, not the full detail-page evidence needed for reliable relevance | fixture/parser audit | **SOURCE/DATA GAP** | Will | Yes |
| Requirements/selection criteria | Jobs v1 has no field; RAG safely abstains | exact Ben-prompt tests | **SHARED CONTRACT GAP** | Qasim + Will | Yes |
| Job comparison | Multiple rows can be listed, but no explicit compare intent/projection | none | **RAG/RETRIEVAL GAP** | Carmen | Yes |
| Duplicate title | Returns clarification; selection rereads fresh row | Jobs tests | — supported | Carmen | No |
| Missing fields | Null/list-empty source values remain unknown and are not inferred | model/answer tests | — supported | Carmen | No |
| No match | Exact/current misses return insufficient evidence | Jobs tests | — supported | Carmen | No |
| Canberra closing-day edge | Real timezone rollover and closing-today inclusion are tested | Jobs boundary test | — supported | Carmen | No |
| Multi-job retrieval | Current list returns multiple stored rows in deterministic order with sources/items | API/chat tests | — supported | Carmen | No |
| Broad entity coverage | RAG has no committed broad Jobs fixture; live corpus coverage was not inspected | handoff only | **SOURCE/DATA GAP** | Will + Qasim live evidence | Yes |

Vector or Gemini must not decide currentness, dates, salary, classification,
employment type or unstored requirements.

## 9. Jobs requirements contract triage

### Official source evidence observed

The public ANU Jobs detail page for Job `563693` contains the title, ID,
employment type, closing information, classification, salary, position
overview and application instructions. It says applicants must address the
selection criteria, but the criteria themselves are not inline; they are behind
a separate `Position Description` link:

`https://jobs.anu.edu.au/jobs/senior-consultant-user-experience-hr-systems-projects-canberra-act-act-australia`

Another current detail page, Job `563412`, includes an inline `The Person`
section with source-authored attribute bullets, while still linking to a formal
Position Description:

`https://jobs.anu.edu.au/jobs/capability-lead-agile-practices-canberra-act-act-australia`

This proves that useful role-requirement evidence sometimes exists on the
approved public detail page, but availability and headings vary. Formal
selection criteria may live in a linked PageUp gateway document. Those gateway
URLs currently contain opaque query data and are outside the frozen canonical
Jobs URL boundary; they require a source-policy and URL-stability review before
collection.

Will's current Day 10 parser does not persist the detail-page body. It builds
`content` only from title, ID, category, employment types, location,
classification, salary, closing information, status and listing summary.
Therefore current storage cannot answer role requirements even where the page
shows them.

### Minimum shared-contract proposal — not approved or implemented

Propose a Jobs metadata v2 field:

```text
role_requirements: list of source-preserved strings | null
```

Rules:

1. Populate only from an explicitly labelled, role-requirement section on the
   validated canonical ANU Jobs detail page, preserving the source wording and
   order.
2. Do not classify duties, overview, category, classification, salary or a
   generic summary as requirements.
3. Do not place generic application-document instructions in
   `role_requirements`.
4. Use `null` when the canonical page does not expose role requirements.
5. Continue returning `insufficient_evidence` when the field is null/empty.
6. Do not turn the field into a personal eligibility/suitability verdict.

The existing canonical Job URL is adequate provenance only for criteria present
on that page. Collection of formal criteria from the linked Position
Description is a separate source-policy decision. If approved, Qasim and Will
must first define a stable allowed URL/document boundary and how the exact
secondary source is exposed as evidence; RAG must not store or emit a transient
candidate/apply gateway URL casually.

Impact if approved:

- Shared contract: expand the exact Jobs metadata key set and freeze type,
  nullability and source semantics.
- Scraper: extract only labelled source text; include it in canonical `content`;
  update hash/fixture/parser tests; leave missing evidence null.
- RAG: extend `JobMetadata`, return the stored list for requirements intent,
  retain the stored canonical source, and keep abstention for null.
- Migration: a new reviewed revision is required because `0004` enforces the
  exact 12-key set. Prefer a controlled null backfill for existing Job rows plus
  revised key/type constraints; do not edit `0004`.
- Backward compatibility: existing rows gain `role_requirements: null`; no
  top-level column, ID, URL, API status or endpoint change is needed.

Safe behavior until approval remains the current behavior: resolve the Job,
reread the stored record, return `insufficient_evidence`, include the official
stored source, and never infer requirements.

## 10. Proposed shared hybrid retrieval contract — design only

### Deterministic-first request contract

1. Resolve current-session meaning without treating history as evidence.
2. Detect exact identities and hard constraints.
3. Exact ID/code/title evidence wins. An exact miss does not silently become a
   fuzzy match.
4. Apply domain, entity type, year/session, current/open/closed, dates and other
   approved structured constraints before similarity ranking.
5. Run semantic retrieval only when it can improve recall for the requested
   capability.
6. Merge/dedupe by `record_id`; rank exact evidence first, then complete hard
   constraint satisfaction, then semantic score, then stable record ID.
7. Rehydrate every candidate from the current `source_records` row before it
   becomes evidence.
8. Reject weak/stale/unknown hits. Clarify or abstain instead of forcing the
   nearest vector.
9. Give only validated stored evidence to Gemini; validate output and map URLs
   from stored records.

### Proposed shared storage primitive

Subject to Qasim approval, use one shared table rather than domain-specific
vector systems:

```text
source_record_embeddings
  record_id          FK -> source_records.record_id
  content_hash       lowercase SHA-256 for the embedded source snapshot
  embedding_version  approved provider/model/preprocessing version
  embedding          vector(D), where D is frozen with the approved model
  embedded_at        timezone-aware timestamp
  primary key (record_id, content_hash, embedding_version)
```

MVP embedding input: one whole-record string, exactly `title + "\n" + content`.
Structured metadata remains SQL/filter authority and is not converted into soft
constraints. Do not introduce chunking until evaluation shows whole-record
recall is insufficient. Do not add HNSW/IVFFlat until corpus size and latency
measurements justify it; pgvector exact similarity is acceptable for a bounded
initial corpus.

### Generation and freshness

- A shared worker scans/claims eligible `PENDING` rows and embeds the current
  `record_id + content_hash` snapshot.
- Successful embedding writes/upserts the vector and updates
  `index_status=INDEXED`, `embedding_version=<target>` atomically.
- Failure sets `FAILED` without deleting current deterministic evidence or a
  prior vector row.
- `UNCHANGED` keeps the matching current vector and version.
- `NEW/CHANGED` stays deterministically retrievable while semantic use is
  blocked until the current hash/version is indexed.
- Query joins must require equality of `record_id`, `content_hash` and target
  `embedding_version`, plus `index_status=INDEXED`; old vectors can never rank
  current changed content.
- Unknown worker commit outcomes reconcile by stable identity/hash, never blind
  duplicate writes.

No provider/model/dimension is selected in this audit. Freeze those values and
worker ownership before writing the migration. The existing `google-genai`
dependency may support a narrow provider adapter; LangChain is not required and
must not replace the resolver or domain business rules.

### Query and candidate contract

The shared repository method should accept a query embedding plus hard filters
and return only bounded identities/scores:

```text
semantic_candidates(
  domain,
  query_vector,
  target_embedding_version,
  hard_filters,
  candidate_limit,
  minimum_score,
) -> [(record_id, content_hash, embedding_version, score)]
```

The caller validates finite scores/range, current hash/version, approved
source/domain and candidate limit, then rereads the full `source_records` rows.
The similarity table is ranking data, not factual evidence or provenance.

Provider failure behavior:

- If deterministic evidence completely answers the request, return it without
  requiring semantic availability.
- If semantic recall is required and unavailable, return the existing
  controlled dependency failure or safe insufficient-evidence behavior chosen
  by the frozen API policy; never fabricate a match.
- If every score is below the evaluated threshold, clarify when a meaningful
  missing identity can be requested, otherwise return `insufficient_evidence`.

## 11. Capability-to-retrieval evaluation matrix

| Question | Mode | Hard filters | Candidate behavior | Provenance | Failure behavior |
|---|---|---|---|---|---|
| `COMP1110 prerequisites` | Deterministic | course, exact code, explicit year if present | One exact row or year clarification | Stored course URL | Unknown/null -> insufficient; no fuzzy fallback |
| `What are the prereqs for Introduction to Software Systems?` | Deterministic | course, exact normalized title | Exact title; duplicates/years clarify | Stored course URL | Exact miss remains a miss |
| `What courses involve functional programming?` | Semantic | course; year if explicit | Rank approved current-hash course rows; threshold and dedupe | Rehydrated stored URLs | Weak/no hits -> insufficient |
| `I want a course about cybersecurity after COMP1110` | Hybrid | course plus resolved prerequisite/context constraints | Retrieve exact COMP1110 context; hard-filter candidates; semantic topic ranking | Every final row rehydrated | Missing relationship evidence -> clarify/insufficient |
| `Requirements for the Bachelor of Accounting` | Deterministic after contract | program, exact title/code, year | Exact Program plus structured rules | Stored Program URL | Missing rule contract/data -> insufficient |
| `Which majors focus on climate policy?` | Hybrid | entity type major, year | Hard entity/year filter then semantic rank | Stored Major URLs | Missing/weak approved records -> insufficient |
| `Show me open scholarships for international undergraduate students` | Deterministic | scholarship, stored open, international, undergraduate | Filter with AND before limit/order | Stored Scholarship URLs | No exact matches -> insufficient; never relax filters |
| `Scholarships related to sustainability or climate policy` | Hybrid | scholarship plus any explicit open/student constraints | Hard-filter first, semantic rank inside candidates | Rehydrated stored URLs | Weak/no hits -> insufficient |
| `Job 563556` | Deterministic | job, exact numeric ID | One exact row | Stored Jobs URL | Unknown ID -> insufficient; no similarity |
| `Jobs closing soon` | Deterministic | job, current, Canberra date, approved horizon | Date filter/order before limit | Stored Jobs URLs | Missing approved horizon -> clarify/defined fallback |
| `Jobs related to cybersecurity, networks or IT infrastructure` | Hybrid | job, current under Canberra rule | SQL current filter first, semantic rank within current rows | Rehydrated stored Jobs URLs | Never reinsert closed/expired rows; weak -> insufficient |
| `What are the requirements for this ANU job?` | Deterministic after contract | uniquely resolved Job | Read stored `role_requirements` only | Stored canonical source supporting the field | Missing identity -> clarify; null evidence -> insufficient |
| `Compare these two jobs` | Deterministic/hybrid by requested facts | two resolved IDs; currentness/dates stay hard | Exact rows first; semantic only for source-backed descriptive dimensions | Both stored URLs | Any missing member/fact -> partial or insufficient, never invented |
| Unrelated/unknown semantic wording | Semantic safety | approved domain/entity constraints | No forced nearest neighbor | None unless a row clears the gate | `insufficient_evidence` or clarification |

## 12. Golden-suite preparation

These are draft acceptance cases, not fake passing semantic tests:

| Priority | Future case | Required evidence before executable | Expected gate |
|---|---|---|---|
| P0 | Exact Program requirements and duplicate-year clarification | Approved Program rules fixture | Deterministic exact; no vector fallback |
| P0 | Exact Major/Minor/Specialisation plus unknown identity | Approved identities/relationship schema and fixtures | Exact/clarify/insufficient |
| P0 | Course comparison with one missing requested fact | Broad source-backed course fixtures | Never fabricate or silently drop member |
| P0 | Broad open Scholarship retrieval across many rows | Broad normalized fixture/live snapshot | Hard filters, deterministic ordering/limit, provenance |
| P0 | Scholarship selection basis/opening/application-required answers | Existing stored fields across source-backed fixtures | Deterministic projection and null abstention |
| P0 | Multi-Job current retrieval with category/location/type constraints | Broad normalized Jobs fixture | All hard filters before order/limit |
| P0 | Job requirements present vs null | Approved metadata v2 and source-backed fixtures | Stored wording vs grounded insufficient evidence |
| P1 | Course/Scholarship/Job semantic topic recall | Real embedding provider + pgvector fixture | Evaluated recall and threshold; no forced hit |
| P1 | Exact match versus misleading high vector score | Shared semantic adapter | Exact always wins |
| P1 | Closed Scholarship/Job with high vector similarity | Shared semantic adapter | Hard status/date exclusion always wins |
| P1 | Stale vector after content hash change | Embedding table/worker fixture | Stale hit excluded; current deterministic facts remain |
| P1 | Semantic unknown ID/duplicate hit/non-finite score | Shared adapter fake at trust boundary | Drop invalid hits; preserve provenance |

At the original audit snapshot, deterministic boundary tests covered exact preference, ambiguity,
multiple candidates, low-score/no-match TF-IDF, unknown hit IDs and provenance.
No dense-semantic test was then marked passing because no dense implementation
existed. The later implementation handoff records the now-passing fake-provider,
pgvector SQL-boundary, freshness and hybrid-ranking tests without claiming a
live provider or PostgreSQL execution.

## 13. Risks, dependencies and Qasim approval items

### Immediate risks/dependencies

- A 99% claim is impossible without broad, source-backed entity and required
  field coverage measurements. Local synthetic fixtures are behavior evidence,
  not coverage evidence.
- The former eager cross-domain Scholarship read and the PR #25 Jobs routing/
  fallback findings are resolved by cheap guards and fail-closed intent paths.
- Broad source-backed Programs/Subplan fixtures and relationship data remain a
  Courses coverage blocker; their identity and metadata contract is now frozen.
- Current normalized Jobs content discards useful detail-page body text.
- A transient/opaque PageUp Position Description link must not be treated as an
  automatically approved stable source.
- The current TF-IDF `top_k=3`/`min_score=0.2` values are local-baseline settings,
  not approved dense-vector thresholds.
- No PostgreSQL 18, live corpus, live vector or cloud action was performed.

### Explicit Qasim approvals required before implementation

1. Jobs metadata v2 field name/type/nullability/source semantics for
   `role_requirements`.
2. A new migration/backfill and revised exact Jobs metadata constraints; never
   edit revision `0004`.
3. Whether linked PageUp Position Description documents are an approved source,
   plus their stable URL/provenance boundary.
4. Major/Minor/Specialisation identity and metadata are now approved; richer
   relationship and degree-audit semantics remain a separate future decision.
5. Scholarship contract additions for degree relevance, application method and
   duration/tenure.
6. pgvector extension, shared embedding-table shape, provider/model, dimension,
   preprocessing/version string and worker ownership/deployment.
7. Any change to public API fields/endpoints. This design requires no new
   response status and proposes no public API change today.

Until those approvals land, Carmen can safely implement only RAG gaps over
already approved fields: Course units/delivery/comparison, Scholarship
opening/application-required/selection-basis projection and structured Jobs
category/location/employment/classification/salary filters/comparison.

The Scholarship projection and Jobs filtering portions named above are now
implemented and covered by the current handoff. This paragraph is retained as
the original audit boundary, not a remaining Carmen-owned blocker.

## 13.1 PR #25 correction verification

The correction changes exactly `job_queries.py`, `scholarship_queries.py`,
`main.py`, their two focused test files, this audit, and the V6 implementation
handoff. No migration/schema/public API/provider/Events/Position Description
work was added.

- Jobs focused: `59 passed`.
- Scholarships focused: `90 passed`.
- Full suite: `571 passed, 60 skipped, 3 warnings` (`631 collected`).
- The 59 guarded PostgreSQL tests remain skipped without a disposable test
  database; the other skip is the Windows symlink-privilege case.
- Offline Alembic SQL compilation is not PostgreSQL 18 or live migration
  execution evidence.

## 14. Files and verification

Files changed by this audit:

- `docs/V6_DAY11_RETRIEVAL_AUDIT.md`

Verification results are recorded after running the exact focused and full
commands on this branch. No migration, model, API, runtime retrieval or test
file is changed by the audit.

Focused verification:

```text
python -m pytest tests/test_course_api.py tests/test_exact_retrieval.py tests/test_hybrid_planner.py tests/test_conversation.py
170 passed

python -m pytest tests/test_scholarships.py
78 passed

python -m pytest tests/test_jobs.py
41 passed

python -m pytest tests/test_index_lifecycle.py tests/test_migrations.py
18 passed
```

Full/static verification:

```text
python -m pytest
463 passed, 59 skipped (522 collected)

python -m pip check
PASS

python -m compileall -q src tests migrations
PASS

git diff --check
PASS
```

The 59 skips are the existing 58 guarded PostgreSQL integration cases when
`ASKANU_TEST_DATABASE_URL` is absent plus the Windows symlink-privilege case.
Disposable PostgreSQL and live PostgreSQL 18 were not rerun for this docs-only
audit because no database/repository/migration behavior changed.
