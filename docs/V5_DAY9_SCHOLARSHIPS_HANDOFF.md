# V5 Day 9 Scholarships — Carmen/RAG implementation handoff

Date: 13 September 2026

Branch: `carmen/day-9-scholarships-rag`

Starting SHA: `13fc637`

Candidate migration: `20260913_0002` after deployed `20260911_0001`

This is a local implementation candidate. It does not claim approval, a live
Cloud SQL migration, a production write, deployment, IAM/secret/Scheduler work,
or write-gate enablement. The shared name, constraints, transaction contract,
and release sequence remain subject to Carmen/Qasim review, with Will included
where scraper write semantics are affected.

## Qasim implementation handoff — 20 explicit items

### 1. Table strategy

- Proposed canonical writable object: physical table `source_records`.
- Compatibility object: `course_program_records`, a Courses/Programs-only view
  for legacy reads.
- Revision `20260913_0002` renames the deployed table in place; it does not
  create a second record table or copy rows.
- There is one authoritative physical record store. The compatibility view is
  not a second authority and is not the approved write/upsert target.
- Final naming still requires Qasim approval.

### 2. Migration path, constraints, and downgrade

The exact path is `20260911_0001 -> 20260913_0002`. The deployed `0001` file is
unchanged. The new revision:

- renames `course_program_records` to `source_records`;
- retains and renames the primary key, required-text, lifecycle-status,
  index-status and content-hash checks plus the title/last-seen indexes;
- removes the Courses-only source, domain, entity-type, academic-year,
  normalized-code, entity-ID and record-ID checks, then recreates them as
  domain-conditional shared checks;
- replaces the original unqualified Courses identity index with a Courses
  partial identity index and adds a Scholarship `(source_id, entity_id)`
  partial unique index;
- adds the exact 13-key Scholarship metadata checks and URL-slug identity
  check; and
- leaves `ingestion_runs` unchanged.

The Scholarship URL rule uses a constant regex only for the HTTPS ANU host/path
shape. It obtains the final path segment with PostgreSQL string operations and
compares it to `entity_id` using literal `=`. Record data is never concatenated
into a regex. No new slug character-set policy is introduced.

Downgrade first refuses if any non-Courses row exists. With only Courses rows it
drops the view/shared checks, restores the original Courses checks/index names,
and renames the table back. It never deletes Scholarship rows to make rollback
appear successful.

### 3. Exact 16-column SQL contract

No Scholarship-only top-level columns are added. `0002` changes no column type,
nullability, default, or stored value from `0001`.

| Column | PostgreSQL type | Nullability | Default | Key/index/check behavior | Course/Program change |
|---|---|---|---|---|---|
| `record_id` | `TEXT` | NOT NULL | none | Primary key; domain-conditional normalized record-ID CHECK | Value/rule unchanged; constraint renamed/generalised |
| `source_id` | `TEXT` | NOT NULL | none | Paired with `domain` by bounded CHECK; part of Scholarship partial unique index | Existing value remains required |
| `entity_id` | `TEXT` | NOT NULL | none | Course code/year CHECK or literal Scholarship URL-slug CHECK; Scholarship partial unique index | Existing code/year identity unchanged |
| `domain` | `TEXT` | NOT NULL | none | Bounded source/domain CHECK; predicate for partial checks/indexes | Remains `courses` |
| `title` | `TEXT` | NOT NULL | none | Non-empty shared CHECK; non-unique title index | Unchanged |
| `content` | `TEXT` | NOT NULL | none | Non-empty shared CHECK | Unchanged |
| `canonical_url` | `TEXT` | NOT NULL | none | Non-empty shared CHECK; Scholarship ANU canonical URL and literal slug CHECK | Stored value unchanged |
| `status` | `TEXT` | NOT NULL | none | CHECK: `NEW`, `CHANGED`, `UNCHANGED`, `MISSING` | Unchanged |
| `effective_from` | `TIMESTAMP WITH TIME ZONE` | nullable | none | No index/default; only source-supported values | Unchanged |
| `effective_to` | `TIMESTAMP WITH TIME ZONE` | nullable | none | No index/default; only source-supported values | Unchanged |
| `collected_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | none | Required observation/version timestamp | Unchanged |
| `last_seen_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | none | Required; non-unique index | Unchanged |
| `content_hash` | `VARCHAR(64)` | NOT NULL | none | CHECK for lowercase 64-character SHA-256 hex | Unchanged |
| `embedding_version` | `TEXT` | nullable | none | Lifecycle-controlled; no standalone index | Unchanged |
| `index_status` | `TEXT` | NOT NULL | none | CHECK: `PENDING`, `INDEXED`, `FAILED` | Unchanged |
| `metadata_json` | `JSONB` | NOT NULL | none | Domain-discriminated validation and identity checks | Existing Course/Program policy remains compatible |

### 4. Courses/Programs compatibility and preservation

Existing rows become `source_records` rows automatically through the physical
rename. There is no backfill, copy or re-ingestion step. `record_id`,
`source_id`, `entity_id`, `canonical_url`, `content_hash`, `index_status`,
`embedding_version`, timestamps and `metadata_json` are not rewritten.

The Courses source/domain filter, course/program discriminator, code/year
identity and uniqueness behavior remain. Regression coverage retains COMP1110
exact lookup, prerequisites, explicit years, multi-year ambiguity and stored
source URL behavior. Course re-ingestion is not required merely because of the
table generalisation.

The view exists for read compatibility by contract. An ordinary PostgreSQL
single-table view may be automatically updatable, so read-only behavior is not
currently enforced by this migration. No current RAG path writes the view.
Whether to enforce read-only permissions and how long the view remains are
Qasim decisions. Old-runtime access also depends on verified view grants.

### 5. Persisted RAG model structure

`CommonRecord` is the strict shared 16-field model. `metadata_json` is a Pydantic
discriminated union over `CourseMetadata`, `ProgramMetadata`, and
`ScholarshipMetadata`, selected by `entity_type`. Compatibility subclasses
`CourseProgramRecord` and `ScholarshipRecord` narrow the source/domain and
metadata types for their repositories.

This keeps domain additions inside the controlled metadata extension rather
than adding top-level columns or another table. Jobs, Accommodation, Support,
and Events could reuse the same physical shape after separately reviewed
source/domain, identity and metadata variants are added. None is implemented by
Day 9, and the current bounded DB/model literals must be extended by migration
and code before any such rows are accepted.

### 6. Scholarship metadata contract

`ScholarshipMetadata` requires exactly these 13 keys:

`entity_type`, `featured`, `status`, `application_required`, `study_stage`,
`student_type`, `study_level`, `area_of_study`, `value`, `selection_basis`,
`opening_date`, `closing_date`, `eligibility`.

- `entity_type` must be the literal `scholarship`.
- Missing scalar source values are represented explicitly as `null`; scalar
  keys may not be omitted.
- Missing filter collections are represented as `[]`; list keys may not be
  omitted and every element must be a string.
- Dates are `YYYY-MM-DD` strings or `null`; RAG additionally rejects impossible
  calendar dates.
- Unknown Scholarship metadata keys are rejected (`extra="forbid"`).
- No null, list, date, value, deadline, status or eligibility fact is inferred.

Strict extra-key rejection is an implemented candidate policy and still
requires Qasim approval for cross-repository evolution.

### 7. Scholarship identity and provenance fields

```text
domain = scholarships
source_id = scholarships_anu_finder
entity_id = <literal final path segment of canonical_url>
record_id = scholarships:scholarship:<entity_id>
```

`canonical_url` stays top-level. It must be HTTPS on `anu.edu.au` or a subdomain
with no query, fragment or trailing slash. Neither title nor changing fields
such as year, value, status or deadline enter identity. The current contract has
no separately frozen slug character whitelist, so the migration enforces exact
literal final-segment equality without inventing one.

### 8. PENDING deterministic retrieval rule

A `PENDING` row contains current accepted DB source text and may be used by
exact lookup and deterministic structured filtering. It must not participate as
current persistent semantic/vector evidence, and the response must not claim
that its embedding is current. `NEW` and `CHANGED` require `PENDING` with
`embedding_version = NULL`.

### 9. INDEXED, FAILED, and derived-stale rules

- `INDEXED` means the current content completed indexing successfully and has a
  non-null matching `embedding_version` for the requested target version.
- `FAILED` leaves accepted source facts available for safe exact/deterministic
  retrieval but excludes current content from the persistent semantic path.
- Stale is derived, not a DB enum/column. A non-`INDEXED` status, missing or
  mismatched version, or an async task whose `record_id + content_hash` no
  longer matches current content is stale/unusable.
- Current DB source content remains authoritative. Old vectors/results cannot
  overwrite or masquerade as current content.
- No `indexed_content_hash`, embedding worker or pgvector workflow is added.

### 10. Ownership

Will/Scraper owns source fetch, parsing, normalization, record upsert,
`content_hash` comparison, `NEW/CHANGED/UNCHANGED` classification and
`ingestion_runs` writes.

Carmen/RAG owns the shared schema/migration, persisted read model, retrieval,
the meaning of `index_status`, and indexing lifecycle/result-safety semantics.

Qasim owns shared-contract approval, live migration, deployment, IAM and the
integration/release gate.

### 11. Cross-repository state transitions

```text
NEW
  -> persist complete normalized row
  -> PENDING
  -> embedding_version NULL

CHANGED
  -> replace current normalized source content under the stable identity
  -> update content_hash
  -> PENDING
  -> embedding_version NULL

UNCHANGED
  -> preserve content and content_hash
  -> preserve index_status and embedding_version
  -> update only approved freshness fields such as last_seen_at

MISSING or collection failure
  -> preserve the last-known-good record
  -> no delete and no re-embedding signal
```

### 12. Failure matrix

| Failure | Previous known-good remains? | Source row / `last_seen_at` | Index status / version | Exact retrieval | Current semantic retrieval | API/audit behavior |
|---|---|---|---|---|---|---|
| Listing fetch fails | yes | unchanged / unchanged | unchanged / unchanged | last-known-good remains available | only if its prior index is still current | controlled failure or safe last-known-good behavior; failed run recorded by writer contract |
| One detail fetch fails | yes for affected record | affected row and timestamp unchanged | unchanged / unchanged | prior record remains available | only if its prior index is still current | do not replace with partial content; batch/run outcome follows approved atomicity policy |
| Parser fails | yes | unchanged / unchanged | unchanged / unchanged | prior record remains available | prior current index remains eligible | controlled failure; no incomplete upsert |
| Validation fails | yes | unchanged / unchanged | unchanged / unchanged | prior record remains available | prior current index remains eligible | reject invalid record and report run failure; batch rollback policy requires approval |
| DB write fails | yes if proposed transaction boundary is adopted | no partial committed batch / unchanged | unchanged / unchanged | previous committed row remains | previous committed current index remains | controlled DB failure and failed audit recovery |
| Indexing fails | yes | accepted source row unchanged / unchanged | matching current row becomes `FAILED`; no successful new version | current source facts remain available | current failed content unavailable | deterministic API may still answer; semantic-only request abstains/fails safely |
| Gemini generation fails | yes | unchanged / unchanged | unchanged / unchanged | retrieval remains available | existing eligible retrieval remains available | controlled 502/error envelope; no fabricated answer/source |
| Future embedding provider fails | yes | accepted source row unchanged / unchanged | `FAILED`; no new successful version | current source facts remain available | current content unavailable | exact/filter path remains; semantic path returns controlled failure/insufficient evidence |

Invariant: collection, parsing, indexing or provider failure must never silently
delete a known-good row or replace it with incomplete content.

### 13. Expected PostgreSQL atomicity — REQUIRES QASIM/WILL APPROVAL

No writer is implemented in this repository, and the transaction boundary is
not yet frozen. The proposed shared contract is:

1. Insert the `RUNNING` `ingestion_runs` audit row in a short transaction.
2. Apply every accepted upsert in one transaction per bounded source run and
   update that run to final `SUCCESS` with counts in the same transaction.
3. If any record write or the final success update fails, roll back the entire
   bounded record batch so no partial accepted run becomes visible.
4. After rollback, update the existing audit row to `FAILED` in a separate
   recovery transaction with bounded safe error information.
5. If commit outcome is unknown, reconcile by stable `run_id`, record IDs and
   hashes before retrying; never assume success or issue blind duplicate writes.

This proposal prevents a state where record changes commit but the success/count
audit update fails. Qasim and Will must approve or replace it in both repos.

### 14. Idempotency and timestamp policy

Expected proof after approval:

- first bounded run of N new logical records produces N `NEW` rows;
- an identical second run produces the same N logical rows as `UNCHANGED`;
- `record_id`, `entity_id`, `canonical_url` and `content_hash` stay stable;
- no duplicate identity/canonical URL rows appear;
- `index_status` and `embedding_version` are preserved; and
- `last_seen_at` advances only after successful observation/write.

The schema defines `collected_at` as the collection timestamp, but the existing
shared text does not unambiguously freeze whether it changes on an identical
`UNCHANGED` observation. The proposed rule is: set it for `NEW`, replace it when
new content is accepted as `CHANGED`, and preserve it for `UNCHANGED` while only
`last_seen_at` advances. **This requires Qasim/Will approval** and is not claimed
as implemented by RAG.

### 15. Generic lifecycle status versus Scholarship dates/status

Top-level `status` is the generic source-record change state
`NEW/CHANGED/UNCHANGED/MISSING`. `metadata_json.status` is the Scholarship
source's public status string. They are different concepts.

`opening_date` and `closing_date` remain Scholarship metadata. No approved rule
maps them to top-level `effective_from/effective_to`; current fixtures keep the
top-level fields null. Unknown dates remain null, and RAG never derives
open/closed from dates. Any future effective-date mapping requires Qasim/Will
approval rather than inference.

### 16. Exact, structured, and semantic Scholarship retrieval

| Query dimension | Current implementation |
|---|---|
| Exact `entity_id`/slug | Exact SQL repository method exists and is tested; the request service also recognizes slugs deterministically in the current Scholarship snapshot |
| Exact title | Deterministic normalized title match over current Scholarship rows |
| `status` | Structured metadata equality filter using stored value only |
| `featured` | Structured strict-boolean filter |
| `application_required` | Structured strict-boolean filter |
| `study_stage` | Structured stored-list membership filter |
| `student_type` | Structured stored-list membership filter |
| `study_level` | Structured stored-list membership filter |
| `area_of_study` | Structured stored-list membership filter |
| Semantic/lexical fallback | Not implemented for Scholarships in Day 9 |

The PostgreSQL adapter first limits rows to the approved Scholarship
source/domain. The service currently performs title/slug recognition and
metadata filtering deterministically in application code over that bounded
snapshot; it does not yet push every filter into SQL. Filters precede any future
semantic ranking, and exact/filter retrieval is independent of vector state.

### 17. Eligibility boundary

RAG separates stored public eligibility text, untrusted current-session user
details, and missing/uncertain evidence. It may display stored official
requirements but explicitly states it cannot determine personal eligibility.
Null eligibility produces no invented requirements or binary verdict. Day 9 is
not an authoritative eligibility engine and must not answer “You are definitely
eligible.”

### 18. Session privacy and source provenance

Scholarship behavior uses the current request, bounded current-session meaning
context, and stored public ANU records. It creates no persistent profile,
cross-session preference, account eligibility state or raw conversation store.
History does not become factual Scholarship evidence.

Response title, record/source IDs, domain and URL are mapped from the retrieved
record. URLs come only from stored `canonical_url`; Gemini cannot generate or
modify them. The existing response envelope supports multiple `sources`; Day 9
may return multiple stored Scholarship sources while leaving `items` within the
frozen API contract. Scholarship Day 9 answers are deterministic and do not
invoke Gemini.

### 19. Deployment and write-enablement order

1. Carmen/Qasim review and merge the RAG/schema PR.
2. Build an image from the exact merged SHA and record its digest.
3. Apply `20260913_0002` to dev PostgreSQL 18 Cloud SQL.
4. Deploy the compatible RAG revision; do not deploy it before the migration
   because it reads `source_records`.
5. Regress existing Courses/Programs paths.
6. Verify Scholarship model/read behavior with controlled data.
7. Qasim approves Will's target switch to `source_records`.
8. Deploy the reviewed Will scraper image with bounded limits and writes still
   gated.
9. Run the first bounded write and prove `NEW`.
10. Run the identical bounded write and prove `UNCHANGED`/idempotency.
11. Simulate and prove failure preservation.
12. Only then decide whether scheduled writes may be enabled.

No step above has been executed by Carmen in this task.

### 20. Rollback matrix and verification gates

| Scenario | Migration may remain? | Previous RAG image | Scraper gate/data action | Downgrade |
|---|---|---|---|---|
| Migration succeeds; RAG deploy fails | yes if Courses view access/regression is verified | may run against the view only after runtime grants and behavior are verified | keep disabled; no Scholarship write | allowed only while no non-Courses rows exist |
| RAG works; scraper writer fails | yes | current or reviewed prior image may remain according to compatibility test | disable gate; preserve last-known-good rows; repair writer | blocked if Scholarship rows exist |
| Malformed Scholarship rows detected | normally yes while isolated/remediated | old RAG sees only Courses through verified view; current RAG Scholarship reads may fail closed | disable gate; Qasim-authorized correction/quarantine/removal may be required | blocked until all non-Courses rows are safely handled |
| Courses regression breaks | only if previous RAG + view regression succeeds; otherwise stop and assess | roll back image only after view permissions/behavior pass | keep disabled; do not add Scholarship rows | allowed only with no non-Courses rows; otherwise deliberately blocked |

All rollback choices involving live data or runtime access require Qasim
operational approval. Before live work, verify PostgreSQL 18 migration behavior,
view privileges, row counts/hashes, exact Courses behavior, downgrade guard and
the exact image SHA/digest. PostgreSQL 12.20 evidence is supplementary only.

## Local verification evidence

- The pre-commit identity blocker was removed by literal final-path comparison;
  static, Pydantic and guarded database regression tests cover `foo.*`,
  `foo|bar`, `foo[0-9]`, `foo+`, and `foo?`, plus a valid literal slug.
- Focused migration/model/repository/lifecycle/conversation/Courses/Scholarship
  suite: `234 passed`.
- Full suite: `362 passed, 8 skipped` from 370 collected tests. One skip is the
  Windows symlink-privilege case; seven are the guarded local PostgreSQL cases
  when `ASKANU_TEST_DATABASE_URL` is absent.
- The complete guarded PostgreSQL integration module passed separately with
  `7 passed` on a disposable PostgreSQL 12.20 instance bound only to
  `127.0.0.1:55435`. This includes all five regex-metacharacter rejection cases,
  the valid literal slug, the compatibility view, Scholarship round-trip and
  existing COMP1110/API behavior. The instance was stopped and removed.
- `python -m pip check`, `python -m compileall -q src tests migrations`, Alembic
  single-head and offline SQL generation, and `git diff --check` passed.
- PostgreSQL 18 and a Day 9 container/image smoke remain pending in Qasim's
  controlled integration environment. Docker and Podman are unavailable on the
  current machine.
- The scraper write gate remains disabled.
