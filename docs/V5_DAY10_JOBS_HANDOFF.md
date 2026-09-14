# V5 Day 10 Jobs — Carmen/RAG implementation handoff

Date: 14 September 2026

Branch: `carmen/day-10-jobs-rag`

PR base SHA: `45455a6c07116b778ef3b28e68253e3e09c7493b`

Reviewed head before final cleanup: `2de15872e7853ebdbc4ce5bf064c35176cf53d03`

Final PR head: the cleanup commit containing this handoff (`git rev-parse HEAD`;
its immutable SHA is supplied in the review package because a commit cannot
embed its own hash).

Migration: `20260914_0004` after `20260914_0003`

The Jobs normalized contract v1 is frozen and is no longer an implementation
blocker. This is a local RAG candidate only: no live Cloud SQL migration, Jobs
write, Cloud Run deployment, Scheduler/IAM/secret change or write-gate action
has been performed.

## Frozen Jobs v1 record boundary

- `domain = jobs`
- `source_id = jobs_anu_search`
- `metadata_json.entity_type = job`
- `entity_id` is the digits-only official ANU requisition/job ID string.
- `record_id = jobs:job:<entity_id>`.
- `metadata_json.job_id` equals `entity_id` exactly.
- Identity is never derived from title, URL slug, dates, location, employment
  type, classification, category or salary.
- The canonical URL is exactly `https://jobs.anu.edu.au/jobs/<slug>` with one
  non-empty path segment and no query, fragment, trailing slash, port,
  alternate host or extra component. The slug is not the numeric identity.
- Top-level `effective_from` and `effective_to` are null.

Jobs metadata has exactly 12 keys: `entity_type`, `job_id`, `category`,
`employment_types`, `location`, `classification`, `salary`, `closing_text`,
`closing_date`, `closing_at`, `status`, and `summary`. Unknown keys are invalid.
Missing scalar values are null; missing `employment_types` is `[]`.
`closing_date` is a real Canberra-local ISO calendar date. `closing_at` is a
timezone-aware ISO datetime string only when the source supplies an exact time.
Status is exactly `current`, `closed` or null.

Fixed-term is stored only as source wording inside `employment_types`. It is not
a Boolean and has no effect on currentness. Jobs v1 has no opening/posting/start
date; ingestion timestamps are never reinterpreted as one.

## Migration and preservation

Revision `0004` changes only the shared source/domain, entity-type and record-ID
checks needed to include Jobs, then adds strict Job identity, canonical URL,
effective-date and exact metadata checks plus a partial unique Jobs identity
index. It does not change the shared 16 columns, rebuild/copy rows, modify
`ingestion_runs`, or touch the `course_program_records` view.

Revisions `0001`, `0002` and `0003` remain byte-for-byte unchanged. With no Jobs
rows, downgrade restores the exact pre-Jobs shared checks. With any Jobs row,
downgrade refuses before removing constraints or data.

## Current Jobs rule

RAG includes a record exactly when:

```text
metadata.status == "current"
AND (
  metadata.closing_date IS NULL
  OR metadata.closing_date >= Canberra today
)
```

It excludes `closed`, null status and any past closing date. A date-only role is
included for the complete closing date in `Australia/Canberra`. No artificial
time is added. The evaluation date is injected at the business-logic boundary
for deterministic tests.

Filtering, ordering and limiting occur in that order. Dated roles are first,
ordered by `closing_date ASC` then numeric `entity_id ASC`. Undated current roles
follow, ordered by numeric `entity_id ASC`. Thus ID `9` sorts before `10`.

## Repository, endpoint and provenance

The shared in-memory and PostgreSQL repositories provide:

1. exact numeric entity/job-ID lookup;
2. whitespace-normalized, case-insensitive exact-title lookup returning every
   duplicate rather than choosing one;
3. source/domain-isolated Current Jobs SQL with filter -> order -> limit; and
4. optional exact `Fixed Term` membership filtering for bounded chat queries.

`GET /api/v1/jobs/current?limit=5` uses a default of 5 and accepts 1–20. Its
successful response contains `status`, `items`, and `request_id`. Each item
contains stored `record_id`, `source_id`, `job_id`, `title`,
`employment_types`, `location`, `classification`, `salary`, `closing_text`,
`closing_date`, `closing_at`, `status`, `url`, and `domain`. Null source values
remain null and URLs come only from stored `canonical_url`. No records returns
`ok` with an empty list. Invalid limits use the controlled 400 error envelope;
an unavailable required production database uses the controlled 500 envelope.

## `/api/v1/ask` behavior

The existing six response fields are unchanged. Jobs routing happens before any
broad Jobs read and uses no Gemini/vector dependency.

- `job <numeric ID>` performs authoritative exact-ID lookup.
- Exact normalized title lookup returns the stored record.
- Duplicate exact titles return `needs_clarification`; options use Job ID and
  available stored location/classification. A selection is revalidated and
  retrieved from current repository evidence.
- Current/open/available/closing-soon/fixed-term list questions use the
  deterministic Current Jobs query. An explicit Jobs message takes precedence
  over stale pending Scholarship scope even when it also contains Scholarship
  filter wording; that context is not treated as a Jobs suitability filter.
- “this job”, “this ANU job” and equivalent `that`/`role` wording can inherit
  only a constrained Job ID from bounded current-session history; all facts and
  URLs are freshly retrieved. With no resolved Job, Ben's exact launcher prompt
  `What are the requirements for this ANU job?` asks which role the user means.
- Jobs v1 contains no structured requirements, qualifications or selection
  criteria. If a Job is resolved but requirements evidence is absent, RAG uses
  `insufficient_evidence`, retains the stored official source, and does not
  infer requirements from title, classification, category, salary or summary.
- Closed, unknown-status or date-expired records are never described as current.
- Unsupported eligibility, suitability, hiring, visa, salary or deadline claims
  are not inferred.

## Ownership and live dependencies

Will/Scraper owns raw source interpretation, normalized status/date/time/
employment/salary values, canonical URL and content hash, writer/upsert/change
detection, ingestion-run records and the approved source-backed fixture.
Carmen/RAG owns validation, the shared migration, exact/current reads, ordering,
endpoint, chat behavior and index-state interpretation. Qasim owns contract and
cross-repo approval plus live migration/deployment ordering.

Will's real source-backed fixture exists on unmerged Scraper branch
`origin/will/day10-jobs` at
`fixtures/jobs/normalized_job_record_sample.json` (commit `52a56f7`, Job ID
`563693`). A direct read-only validation of that Git object passed unchanged
through `CommonRecord`, `JobRecord`, exact repository lookup and Current Jobs;
no field adaptation, identity/URL reconstruction or salary conversion was
needed. It is not in Scraper `main` or a checked-out shared fixture path, so RAG
does not add a brittle cross-repository/branch-dependent pytest. A committed
source-backed compatibility regression remains pending Will's merge or an
explicitly approved fixture-vendoring decision. Synthetic RAG records remain
unit-test-only and are not presented as ANU production facts.

## Remaining live gates

1. Review and merge the exact Jobs RAG SHA.
2. Apply `20260914_0004` on PostgreSQL 18 under Qasim's control.
3. Verify production-equivalent RAG reads, scraper writes and the unchanged
   structurally non-updatable Courses compatibility view.
4. Merge Will's contract-aligned source-backed fixture/writer, then add the
   stable cross-repo compatibility regression from the merged artifact.
5. Deploy the separate expected `askanu-scraper-jobs` collector only after its
   own review; run dry-run and prove zero writes.
6. Prove first bounded `NEW`, inspect `source_records`, repeat as `UNCHANGED`,
   and run failure-preservation/unknown-outcome reconciliation.
7. Smoke Current Jobs exclusion/ordering, exact known-role lookup and stored
   canonical links before any Scheduler/write-gate decision.

## Future carry-over

1. Broader router cleanup should resolve domain before every domain-specific
   bulk retrieval; no six-domain rewrite is included here.
2. Future semantic Jobs retrieval should use a relatively generous candidate K
   tuned against recall, reranking quality and latency; no numeric K is frozen.

## Manual review item

Qasim should review the locally selected `/api/v1/jobs/current` DTO and maximum
limit of 20. The frozen contract defined the endpoint and source facts but did
not separately freeze those DTO types/nullability or a project-wide maximum.
No other Jobs v1 contract decision is reopened.

## Local verification

- Focused Jobs model/retrieval/API and migration suite: `46 passed`. The five
  final-cleanup cases cover Ben's exact requirements prompt without a selected
  Job, selected-Job requirements abstention with stored source, rejection of
  unrelated or multi-Job history, and a real `canberra_today()` rollover at
  `2026-09-14T14:30:00Z` (Canberra date `2026-09-15`) including closing-today
  currentness.
- Final Day 9 Scholarship suite: `76 passed`; explicit COMP1110 regression:
  `1 passed`; the selected pending Scholarship/Jobs/Courses routing and COMP1110
  check is `5 passed`.
- Full suite: `461 passed, 59 skipped` from 520 collected tests. One skip is the
  Windows symlink-privilege case; 58 are guarded PostgreSQL cases when
  `ASKANU_TEST_DATABASE_URL` is absent.
- The complete guarded PostgreSQL module passed separately with `58 passed` on
  a disposable PostgreSQL 12.20 instance bound only to `127.0.0.1:55443`.
  It covered actual `0004` upgrade/downgrade, strict Job constraints, SQL
  filter/order/limit, numeric ID ordering, endpoint/chat reads, downgrade
  refusal and the unchanged structurally read-only Courses view. The instance
  and its files were stopped and removed.
- `python -m pip check`, compileall, `git diff --check`, Alembic single-head
  inspection and focused `0003:0004` offline SQL generation passed. The head is
  `20260914_0004`.
- Revisions `0001`, `0002` and `0003` retain their reviewed hashes. No secret or
  credential is part of the candidate diff.
- PostgreSQL 18, a stable merged path for Will's source-backed fixture pytest,
  Qasim's final review and every cloud/live gate above remain pending.
