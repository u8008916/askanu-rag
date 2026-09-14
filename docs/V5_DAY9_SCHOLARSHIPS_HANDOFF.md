# V5 Day 9 Scholarships — Carmen/RAG implementation handoff

Date: 13 September 2026

Read-only compatibility follow-up date: 14 September 2026

Clarification-refinement follow-up date: 14 September 2026

Current cleanup branch:
`carmen/day-9-scholarship-clarification-refinement-clean`

Current deployed main SHA: `1576c61935da9f303a3d6ef0aa16ebee52f0045e`

Current live Alembic revision: `20260914_0003`

Original implementation branch: `carmen/day-9-scholarships-rag`

Read-only compatibility follow-up branch: `carmen/day-9-readonly-compat-view`

Starting SHA: `13fc637`

Final contract-alignment follow-up base SHA: `718317b8e52ca4c51e5cae14538d52eb41925fc9`

Deployed migration path: `20260911_0001 -> 20260913_0002 -> 20260914_0003`

This handoff preserves the original local implementation evidence and records
the later live acceptance state reported by Qasim. Carmen did not perform the
Qasim-owned migration, deployment or live acceptance operations in this
clarification follow-up. Shared migration `0002`, read-only follow-up `0003`,
the RAG runtime path and the bounded Scholarship scraper acceptance have now
completed. The only remaining Day 9 RAG acceptance gap is natural-language
refinement after `clar-scholarship-scope`; this branch contains that RAG-only
behavior fix and requires no migration, database mutation or scraper run.

## Current live acceptance state — Qasim-reported

- Alembic is current at `20260914_0003`; shared migration `0002` and the
  read-only compatibility follow-up `0003` are deployed.
- `course_program_records` is structurally read-only with
  `is_updatable = NO` and `is_insertable_into = NO`; the `source_records`
  runtime path and COMP1110 regression are verified.
- The bounded scraper stored 8 real Scholarship rows: the first run produced
  8 `NEW`, and the identical second run produced 8 `UNCHANGED`.
- `collected_at` and content hashes were preserved while `last_seen_at`
  advanced on the successful repeat observation.
- A simulated listing/fetch failure recorded the run as `FAILED` and preserved
  all last-known-good Scholarship rows.
- Deployed RAG main SHA `1576c61` passed exact Scholarship lookup, broad
  Scholarship clarification, explicit option selection, missing-eligibility
  abstention and official persisted-source provenance checks.
- Natural-language refinement of `clar-scholarship-scope` is the sole remaining
  Day 9 RAG acceptance gap before this clean follow-up is merged and deployed.

## Qasim implementation handoff — 20 explicit items

### 1. Table strategy

- Canonical writable object: physical table `source_records`.
- Compatibility object: `course_program_records`, a Courses/Programs-only view
  for legacy reads.
- Revision `20260913_0002` renames the deployed table in place; it does not
  create a second record table or copy rows.
- There is one authoritative physical record store. The compatibility view is
  not a second authority and is not the approved write/upsert target.
- The physical naming and runtime path are approved and live.

### 2. Migration path, constraints, and downgrade

The exact path is `20260911_0001 -> 20260913_0002 -> 20260914_0003`. The
deployed `0001`, `0002` and `0003` files remain unchanged. Revision `0002`:

- renames `course_program_records` to `source_records`;
- retains and renames the primary key, required-text, lifecycle-status,
  index-status and content-hash checks plus the title/last-seen indexes;
- removes the Courses-only source, domain, entity-type, academic-year,
  normalized-code, entity-ID and record-ID checks, then recreates them as
  domain-conditional shared checks;
- replaces the original unqualified Courses identity index with a Courses
  partial identity index and adds a Scholarship `(source_id, entity_id)`
  partial unique index;
- adds the exact 13-key Scholarship metadata checks, exact canonical URL and
  slug-grammar identity checks, and the Scholarship null effective-date check; and
- leaves `ingestion_runs` unchanged.

Revision `0003` drops and recreates only the `course_program_records` view. It
adds a top-level `OFFSET 0`, which preserves the exact 16-column projection,
Courses source/domain filter, rows and values while making the view structurally
non-updatable in PostgreSQL. Its downgrade recreates the exact prior `0002`
simple-view definition. It changes no table, constraint, index, row or shared
data/API contract.

The Scholarship boundary is exactly
`https://study.anu.edu.au/scholarships/find-scholarship/<slug>`, where `<slug>`
matches `^[a-z0-9]+(?:-[a-z0-9]+)*$`. The database compares the entire literal
URL to the constant prefix plus `entity_id`, and also compares the final segment
to `entity_id` with literal `=`. Record data is never concatenated into a regex.

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
| `effective_from` | `TIMESTAMP WITH TIME ZONE` | nullable | none | Must be `NULL` for Scholarships | Unchanged |
| `effective_to` | `TIMESTAMP WITH TIME ZONE` | nullable | none | Must be `NULL` for Scholarships | Unchanged |
| `collected_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL | none | First accepted collection time; preserved after `NEW` | Unchanged |
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

The view exists for read compatibility by contract. Qasim's PostgreSQL 18 live
check found the earlier `0002` simple view reported `is_updatable = YES` and
`is_insertable_into = YES`; follow-up revision `0003` was then deployed and
verified with both values equal to `NO`. It preserves the same legacy reads,
while `source_records` remains the sole approved write target. The live runtime
path, view behavior and COMP1110 regression have been verified under the
intended access boundary.

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

Strict extra-key rejection is part of the approved bounded v1 contract;
cross-repository evolution still requires a new shared decision.

### 7. Scholarship identity and provenance fields

```text
domain = scholarships
source_id = scholarships_anu_finder
entity_id = <slug matching ^[a-z0-9]+(?:-[a-z0-9]+)*$>
record_id = scholarships:scholarship:<entity_id>
canonical_url = https://study.anu.edu.au/scholarships/find-scholarship/<entity_id>
```

`canonical_url` stays top-level and must equal the frozen constant prefix plus
the literal `entity_id`; alternate hosts, paths, query strings, fragments,
trailing slashes and nonconforming slugs are invalid. Neither title nor changing
fields such as year, value, status or deadline enter identity.

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
`ingestion_runs` writes. The scraper is the trusted canonical normalization and
hash writer and guarantees that the persisted hash is SHA-256 of canonical
persisted UTF-8 `content`.

Carmen/RAG owns the shared schema/migration, persisted read model, retrieval,
the meaning of `index_status`, and indexing lifecycle/result-safety semantics.
RAG validates the lowercase 64-character hash format and trusts the persisted
invariant; it does not independently rehash records during retrieval.
Stale-index result safety assumes only approved writer paths can persist rows
and that each such path enforces the canonical content/hash invariant.

Qasim owns shared-contract approval, live migration, deployment, IAM and the
integration/release gate.

### 11. Cross-repository state transitions

```text
NEW
  -> persist complete normalized row
  -> set collected_at and last_seen_at
  -> PENDING
  -> embedding_version NULL

CHANGED
  -> replace current normalized source content under the stable identity
  -> update content_hash
  -> preserve collected_at and update last_seen_at
  -> PENDING
  -> embedding_version NULL

UNCHANGED
  -> preserve content and content_hash
  -> preserve index_status and embedding_version
  -> preserve collected_at and update last_seen_at

MISSING or collection failure
  -> preserve the last-known-good record
  -> do not advance collected_at or last_seen_at
  -> no delete and no re-embedding signal
```

### 12. Failure matrix

| Failure | Previous known-good remains? | Source row / `last_seen_at` | Index status / version | Exact retrieval | Current semantic retrieval | API/audit behavior |
|---|---|---|---|---|---|---|
| Listing fetch fails | yes | unchanged / unchanged | unchanged / unchanged | last-known-good remains available | only if its prior index is still current | controlled failure or safe last-known-good behavior; failed run recorded by writer contract |
| One detail fetch fails | yes for affected record | entire bounded batch rolls back; affected row and timestamp unchanged | unchanged / unchanged | prior record remains available | only if its prior index is still current | do not replace with partial content; recovery transaction marks run failed |
| Parser fails | yes | unchanged / unchanged | unchanged / unchanged | prior record remains available | prior current index remains eligible | controlled failure; no incomplete upsert |
| Validation fails | yes | unchanged / unchanged | unchanged / unchanged | prior record remains available | prior current index remains eligible | reject invalid record, roll back the bounded batch and report run failure |
| DB write fails | yes | no partial committed batch / unchanged | unchanged / unchanged | previous committed row remains | previous committed current index remains | controlled DB failure and failed audit recovery |
| Indexing fails | yes | accepted source row unchanged / unchanged | matching current row becomes `FAILED`; no successful new version | current source facts remain available | current failed content unavailable | deterministic API may still answer; semantic-only request abstains/fails safely |
| Gemini generation fails | yes | unchanged / unchanged | unchanged / unchanged | retrieval remains available | existing eligible retrieval remains available | controlled 502/error envelope; no fabricated answer/source |
| Future embedding provider fails | yes | accepted source row unchanged / unchanged | `FAILED`; no new successful version | current source facts remain available | current content unavailable | exact/filter path remains; semantic path returns controlled failure/insufficient evidence |

Invariant: collection, parsing, indexing or provider failure must never silently
delete a known-good row or replace it with incomplete content.

### 13. Frozen PostgreSQL atomicity

No writer is implemented in this repository; Will's scraper implements the
writer. The frozen shared contract is:

1. Insert the `RUNNING` `ingestion_runs` audit row in a short transaction.
2. Apply every accepted upsert in one transaction per bounded source run and
   update that run to final `SUCCESS` with counts in the same transaction.
3. If any record write or the final success update fails, roll back the entire
   bounded record batch so no partial accepted run becomes visible.
4. After rollback, update the existing audit row to `FAILED` in a separate
   recovery transaction with bounded safe error information.
5. If commit outcome is unknown, reconcile by stable `run_id`, record IDs and
   hashes before retrying; never assume success or issue blind duplicate writes.
6. A partially committed successful batch is invalid.

This prevents a state where record changes commit but the success/count audit
update fails. For an unknown outcome, blind duplicate writes are forbidden.

### 14. Idempotency and timestamp policy

Qasim-reported live integration evidence now satisfies this proof: the first
bounded run stored 8 new logical Scholarship records as `NEW`; the identical
second run kept the same 8 logical records as `UNCHANGED`. Identity and content
hashes remained stable, `collected_at` was preserved and `last_seen_at`
advanced. The simulated listing/fetch failure recorded `FAILED` and preserved
the last-known-good rows.

The continuing contract requires `record_id`, `entity_id`, `canonical_url` and
`content_hash` to stay stable, prohibits duplicate identity/canonical URL rows,
preserves `index_status` and `embedding_version` for unchanged content, and
advances `last_seen_at` only after successful observation/write.

For `NEW`, set both `collected_at` and `last_seen_at`. For `CHANGED` and
`UNCHANGED`, preserve `collected_at` and update `last_seen_at` only in the
successful atomic batch. `MISSING` and any failed observation preserve the
known-good row and advance neither timestamp. This is frozen writer behavior;
RAG does not implement the writer.

If a future content-version timestamp is needed, it must be introduced
deliberately as a new shared field/contract rather than overloading
`collected_at`.

### 15. Generic lifecycle status versus Scholarship dates/status

Top-level `status` is the generic source-record change state
`NEW/CHANGED/UNCHANGED/MISSING`. `metadata_json.status` is the Scholarship
source's public status string. They are different concepts.

`opening_date` and `closing_date` remain Scholarship metadata. Scholarship
top-level `effective_from` and `effective_to` are frozen as `NULL` and enforced
by the model and database. Unknown dates remain null, and RAG never derives
open/closed from dates. Any future effective-date mapping is a new shared
contract change rather than an inference.

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

When the active clarification is `clar-scholarship-scope`, the immediate
follow-up first retains the existing explicit option-selection behavior, then
an explicit current-message switch to another supported domain releases the
stale Scholarship scope back to normal routing. Pending clarification is
current-session context, not a route lock. With no such switch, the follow-up
may reuse the deterministic Scholarship filters for values explicitly present
in that message; explicit Scholarship wording remains in the Scholarship flow.
Supported metadata dimensions remain `student_type`,
`study_level`, `study_stage` and `area_of_study`, together with the existing
`open`, `closed` and `featured` filters. Independent dimensions combine with
AND. The narrow frozen study-level wording treats `Undergraduate` and
`Bachelor` as equivalent; no other semantic synonym layer is added. Earlier
history is not merged into these filters and the refinement is a requested
search scope, not evidence about the user's profile or eligibility.

Response title, record/source IDs, domain and URL are mapped from the retrieved
record. URLs come only from stored `canonical_url`; Gemini cannot generate or
modify them. The existing response envelope supports multiple `sources`; Day 9
may return multiple stored Scholarship sources while leaving `items` within the
frozen API contract. Scholarship Day 9 answers are deterministic and do not
invoke Gemini.

### 19. Current live state and remaining RAG-only release

The shared migrations, structurally read-only view, runtime permissions,
Courses regression and bounded Scholarship scraper acceptance described above
are complete according to Qasim's live acceptance report. They remain recorded
here as historical evidence and are not work for this refinement PR.

After this clean branch is reviewed and merged, Qasim's remaining release path
is to pull the exact merged main SHA, build and push an immutable RAG image,
record its digest, update only `askanu-rag` while preserving its existing
environment, secrets, service account and Cloud SQL attachment, and verify the
new revision serves 100%. Qasim can then rerun COMP1110, exact Scholarship,
broad clarification, `International undergraduate` continuation and missing
eligibility abstention.

This is a RAG-only behavior release. It requires no migration, database
mutation, scraper execution or Scholarship job configuration change. Carmen
has not performed any Qasim-owned live release action in this cleanup task.

### 20. Rollback matrix and verification gates

| Scenario | Migration may remain? | Previous RAG image | Scraper gate/data action | Downgrade |
|---|---|---|---|---|
| Migration succeeds; RAG deploy fails | yes if Courses view access/regression is verified | may run against the view only after runtime grants and behavior are verified | keep disabled; no Scholarship write | allowed only while no non-Courses rows exist |
| RAG works; scraper writer fails | yes | current or reviewed prior image may remain according to compatibility test | disable gate; preserve last-known-good rows; repair writer | blocked if Scholarship rows exist |
| Malformed Scholarship rows detected | normally yes while isolated/remediated | old RAG sees only Courses through verified view; current RAG Scholarship reads may fail closed | disable gate; Qasim-authorized correction/quarantine/removal may be required | blocked until all non-Courses rows are safely handled |
| Courses regression breaks | only if previous RAG + view regression succeeds; otherwise stop and assess | roll back image only after view permissions/behavior pass | keep disabled; do not add Scholarship rows | allowed only with no non-Courses rows; otherwise deliberately blocked |

All rollback choices involving live data or runtime access require Qasim
operational approval. The PostgreSQL 18 migration, view flags, runtime path and
acceptance checks are now complete; the matrix remains the safety policy for
future rollback decisions. Any new release must still record and verify its
exact image SHA/digest. PostgreSQL 12.20 evidence below is historical,
supplementary local evidence only.

## Future carry-over

1. Resolve domain/intent before calling eager `all_scholarships()`; do not make
   that routing refactor in this follow-up.
2. For a future Scholarship semantic vector path, keep candidate K relatively
   generous and tune it empirically across recall, reranking quality, latency
   and evaluation results; no numeric K is frozen here.

## Local verification evidence

The following migration/view results are historical local evidence from the
original Day 9 implementation and read-only follow-up; they are retained rather
than being recast as work performed during the clarification refinement.

- The identity boundary is enforced consistently in migration and Pydantic:
  exact `study.anu.edu.au` host/path, frozen slug grammar, literal final-path
  equality and null Scholarship effective dates. Static, model and guarded
  database tests cover wrong hosts/paths, extra components, queries, fragments,
  trailing slashes, malformed slugs and regex metacharacters.
- Focused Day 9 migration and structurally read-only compatibility-view suite:
  `11 passed`.
- Full suite: `401 passed, 41 skipped` from 442 collected tests. One skip is the
  Windows symlink-privilege case; 40 are the guarded local PostgreSQL cases when
  `ASKANU_TEST_DATABASE_URL` is absent.
- The complete guarded PostgreSQL integration module passed separately with
  `40 passed` on a disposable PostgreSQL 12.20 instance bound only to
  `127.0.0.1:55439`. This includes `NO`/`NO` view-update flags, rejected
  `INSERT`/`UPDATE`, the exact 16-column/filter contract, an unchanged
  `0003 -> 0002 -> 0003` round trip, guarded Scholarship downgrade refusal,
  Scholarship round-trip and existing COMP1110/API behavior. The instance was
  stopped and removed.
- `python -m pip check`, `python -m compileall -q src tests migrations`, Alembic
  single-head and offline SQL generation, and `git diff --check` passed.
- Qasim's later live acceptance completed the PostgreSQL 18 migration/view,
  runtime, COMP1110, bounded scraper, failure-preservation and Scholarship read
  checks listed in the current-live section. This refinement branch neither
  repeats nor claims ownership of those live actions.
- The clean clarification-refinement branch adds current-follow-up-only,
  deterministic AND-filter, option-selection, zero-match, eligibility-safety,
  source-provenance and Course-switch regression coverage. Exact clean-head
  results belong to the branch/PR verification report.
