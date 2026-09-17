# V6 Day 13 RAG release-readiness handoff

Date: 2026-09-17 (Australia/Sydney)

Audience: Qasim / Carmen

Scope: RAG release gate only; no production action is authorized by this document.

## Release-gate decision

The merged RAG main line is a viable **conditional release candidate**. The exact source passed the clean-main suite, the real disposable PostgreSQL 18 + pgvector gate, the migration tests, image build, startup, and deterministic API smoke. Application startup did not migrate or mutate the database.

This is not approval to deploy. Before a Day 14 release candidate can be used safely, the production read-only preflight below must be clean, the 0004 -> 0008 migration and deployment must be explicitly approved, the production Gemini/DB configuration must be verified, and the scraper-side Support Referral validator mismatch must be resolved before Accommodation/Support production ingestion.

The local production-style container was intentionally started without a real Gemini credential. Its Courses requests therefore failed closed with the controlled `502` envelope after retrieval reached synthesis. Deterministic domains and all pytest Courses coverage passed. An authorized environment must verify the real synthesis credential; no external model call was made in this release-readiness exercise.

## Candidate identity and clean-main provenance

| Item | Exact result |
|---|---|
| Branch | `main` |
| Release-candidate SHA | `ccd93b37510b585f734e8dd38f23f52ae8042c61` |
| Commit | `ccd93b3 feat: align Accommodation and Support frozen contracts (#29)` |
| `origin/main` | `ccd93b37510b585f734e8dd38f23f52ae8042c61` |
| Local vs remote | Local `main` exactly matched `origin/main` after `git pull --ff-only origin main` |
| Pre-document status | Clean; no modified or untracked files |
| Existing isolated work | Existing stashes were inspected and left untouched, including `wip: day12 events time semantics` |

No stash was applied, dropped, or modified. Schema-independent Events WIP was not merged into this work.

## Clean-main verification

Fresh evidence was collected from the merged SHA, not reused from the feature branch.

| Gate | Result |
|---|---|
| `python -m pytest` without a DB URL | **777 passed, 77 skipped, 3 warnings** in 7.41s |
| PostgreSQL skips in that run | 76 expected opt-in integration skips because `ASKANU_TEST_DATABASE_URL` was unset |
| Other skip | 1 existing Windows symlink-privilege skip |
| Warnings | 3 dependency deprecations: Starlette/httpx, AnyIO alias, and google-genai |
| `python -m pip check` | `No broken requirements found.` |
| `python -m compileall -q src tests migrations` | PASS |
| `python -m alembic heads` | `20260916_0008 (head)`; one head |
| `git diff --check` | PASS |
| `git status --short` before documentation | Empty |

The final validation after creating this handoff is recorded near the end. The handoff itself is intentionally the only uncommitted repository change.

## Disposable PostgreSQL 18 + pgvector verification

Only the existing local disposable container was used:

| Item | Evidence |
|---|---|
| Container/image | `askanu-pg18-test` / `pgvector/pgvector:pg18` |
| Host exposure | Docker reported `0.0.0.0:55432->5432`; every integration command connected through `127.0.0.1:55432`, and the test guard rejects non-loopback URLs |
| Database safety boundary | Database name `askanu_test`; integration code independently requires a loopback host and `_test` suffix |
| Server | PostgreSQL `18.6 (Debian 18.6-1.pgdg12+2)`; `server_version_num=180006` |
| pgvector | available `0.8.6`, installed `0.8.6` |
| Alembic current | `20260916_0008 (head)` |
| Real DB suite | `tests/test_postgres_integration.py`: **76 passed, 3 warnings** in 5.60s; no skip |
| Day 12 migration suite | `tests/test_day12_migration.py`: **10 passed**; no skip |

The PostgreSQL gate included real DDL, constraint, downgrade/upgrade, repository, API, and Day 12 hostname regressions. It was not a mock and was not Cloud SQL.

## 0004 -> 0008 migration review

Production is understood, but not verified today, to be at `20260914_0004`. The target is the single head `20260916_0008`. No historical migration was edited.

### Detailed mutation table

| Revision | Parent | Schema/table/view/column mutations | Indexes and constraints | Functions/extensions/data | Compatibility, downgrade, and assumptions |
|---|---|---|---|---|---|
| `20260915_0005` shared hybrid embeddings | `20260914_0004` | Creates `source_record_embeddings` with FK `source_record_id -> source_records(record_id) ON DELETE CASCADE`, composite primary key, hash/text/vector checks, and timestamps. Does not alter existing columns. | Replaces Jobs exact-key/type checks with the 13-key v2 shape. Extends global source/domain/entity/record-ID checks to provisional Accommodation/Support. Adds provisional identity/metadata checks and unique partial `(source_id, entity_id)` indexes for both domains. Adds `ix_source_record_embeddings_current_lookup`. | `CREATE EXTENSION IF NOT EXISTS vector`. Updates only Jobs rows missing `role_requirements`, adding JSON null; no requirement text is inferred. | Existing Jobs must already satisfy 0004 v1. Existing provisional resources must satisfy exact 0005 checks. DB must support/permit pgvector creation. Downgrade refuses while any Accommodation/Support row exists, drops the embeddings table but intentionally retains the `vector` extension, removes resource checks/indexes, deletes `role_requirements` from Jobs, and restores v1 Jobs checks. |
| `20260915_0006` Courses family/subplans | `20260915_0005` | Drops/recreates the `course_program_records` compatibility view; it remains limited to course/program and uses `OFFSET 0`, so it is read-only. No column/table creation. | Replaces course/program identity constraints with Course-family checks supporting `major`, `minor`, and `specialisation`; adds exact lowercase canonical URL, subplan metadata, optional Courses metadata checks, and `uq_source_records_courses_identity`; removes the old course/program unique index. | Read-only guard first rejects unexpected existing Course canonical URLs. Then normalizes only exact legacy uppercase-code course/program URLs to lowercase. No extension/function changes. | Existing course/program URLs must be either the exact lowercase canonical form or the exact legacy uppercase-code form. Downgrade refuses while subplan rows exist, restores course/program checks/index/view, and does not reverse safe lowercase URL normalization. |
| `20260915_0007` null-safe arrays | `20260915_0006` | No table/view/column changes. | Replaces only `ck_source_records_job_metadata_types`, `ck_source_records_subplan_metadata`, and `ck_source_records_courses_optional_metadata_types` so nullable arrays are genuinely null-safe. | No function, extension, index, or data mutation. | Aligns SQL with Python for null `role_requirements`, `learning_outcomes`, and `relevant_degrees`. Downgrade is deliberately a no-op; reinstating the known-invalid predicates would reject valid data. Later downgrade through 0006/0005 still replaces those named checks. |
| `20260916_0008` frozen Day 12 resources | `20260915_0007` | No tables/views/columns or row data are mutated. | Replaces global entity/record-ID and provisional Accommodation/Support identity/metadata checks with the frozen contracts. Accommodation becomes `residence` with `accommodation:residence:<slug>` and an exact ANU residence URL. Support keeps `support_service` with an exact ANUSA service URL. Existing unique partial indexes remain. | Creates immutable strict functions `askanu_day12_accommodation_metadata_valid(JSONB)` and `askanu_day12_support_metadata_valid(JSONB)`. The Support validator enforces approved Student Assistance topic paths and external, credential-free Referral URLs, including case-insensitive ANUSA hostname rejection. | A read-only guard runs before constraints are dropped. Unknown resource rows fail manual review; known provisional rows fail manual reingestion. Already-frozen rows are permitted. Downgrade refuses while either resource domain contains rows, then restores exact 0007 provisional checks and drops the two validator functions. |

### Existing Jobs row handling

An existing Jobs row survives 0004 -> 0008 if it is genuinely valid under 0004. At 0004 it must have:

- `source_id='jobs_anu_search'`, `domain='jobs'`, entity type `job`;
- a digits-only `entity_id` equal to metadata `job_id`;
- `record_id='jobs:job:' || entity_id`;
- an exact `https://jobs.anu.edu.au/jobs/<single-segment>` URL with no query, fragment, or trailing slash;
- null `effective_from` and `effective_to`;
- exactly these 12 metadata keys: `entity_type`, `job_id`, `category`, `employment_types`, `location`, `classification`, `salary`, `closing_text`, `closing_date`, `closing_at`, `status`, `summary`;
- values satisfying the 0004 type/date/timestamp/status checks.

Revision 0005 adds only `"role_requirements": null` when the key is missing, then installs the 13-key v2 checks. It does not infer or rewrite a requirement. Revision 0007 makes the nullable array check correct. Revisions 0006 and 0008 do not otherwise mutate Jobs. Therefore a valid 0004 row needs no reingestion; an invalid or extra-key row must be remediated before migration. The read-only SQL below produces the evidence needed for that decision.

## Fail-closed catalogue

| Condition | Revision/runtime | Expected refusal | Required remediation |
|---|---|---|---|
| `vector` is unavailable or the migration role cannot create/use it | 0005 | Extension/table DDL fails; migration transaction must not be approved | Enable supported pgvector and grant the narrowly required privilege before retrying. Do not bypass the embeddings table. |
| Existing Jobs row is not valid 0004 v1, has extra keys, malformed identity/URL, or bad types | 0005 | Recreated v2 constraints reject the transaction after the bounded null-key update | Inspect with preflight SQL; correct/reingest the source row under the approved Jobs contract. |
| Existing Accommodation/Support row does not satisfy provisional 0005 identity/metadata/source-authority checks | 0005 | New shared/resource checks reject the transaction | Classify and remove/reingest only through an approved source workflow; do not widen checks. |
| Duplicate `(source_id, entity_id)` in Accommodation or Support | 0005 | Unique partial index creation fails | Reconcile duplicate identities before migration. |
| Existing course/program canonical URL is neither exact lowercase canonical nor exact legacy uppercase-code canonical | 0006 upgrade | `Cannot normalize unexpected Courses canonical URL` | Investigate/reingest the affected row; do not bulk-normalize an unknown URL. |
| Existing Course-family rows violate new identity, URL, subplan, or optional metadata checks | 0006/0007 | Constraint installation rejects the transaction | Fix source data against the frozen Course-family contract. |
| Any subplan row exists during 0006 downgrade | 0006 downgrade | `Cannot downgrade while Courses subplan records exist` | Export/remove or otherwise explicitly handle subplans before an authorized downgrade. |
| Any resource row is outside either the exact provisional or exact frozen classifications | 0008 upgrade | `Unexpected Accommodation/Support rows require manual contract review` | Stop and review the exact row; no automatic coercion. |
| A known provisional Accommodation row (`entity_type=accommodation`) or Support row retaining `source_authority` exists | 0008 upgrade | `Known provisional Accommodation/Support rows require manual reingestion; no lossy auto-conversion is permitted` | Reingest into the frozen scraper/RAG contract after cross-repo approval; do not transform nested facts in SQL. |
| A row that looked frozen fails the new strict nested metadata/URL rules | 0008 constraint installation | Frozen check constraint rejects the transaction | Correct/reingest from approved source evidence; do not weaken validator functions. |
| Any Accommodation/Support row exists during 0008 downgrade | 0008 downgrade | `Cannot downgrade frozen Day 12 contracts while Accommodation/Support records exist` | Plan explicit data removal/export before an authorized downgrade. |
| Any Accommodation/Support row exists during 0005 downgrade | 0005 downgrade | `Cannot downgrade while Accommodation/Support records exist` | Handle resource data explicitly before downgrading through 0005. |
| Any Jobs row exists while downgrading 0004 itself | 0004 downgrade | `Cannot downgrade while Jobs source_records exist` | Handle Jobs data explicitly; this is beyond the 0008 -> 0004 rollback boundary but is important to the full rollback plan. |
| Embedding row has blank IDs/model/version, non-hex hashes, zero-dimensional vector, or missing parent | 0005 runtime schema | PK/FK/check constraint rejection | Regenerate through the approved indexer. Do not insert partial vectors. |
| No Gemini API credential in production-style service config | Runtime synthesis | Grounded Course request reaches synthesis then returns controlled HTTP `502`, without leaking provider details | Verify authorized secret binding and endpoint access in the deployment environment. Do not put a credential in the image or this handoff. |
| Retrieval lacks an approved fact, live vacancy, support hour/access, or current evidence | Runtime answer contract | `insufficient_evidence` rather than inference | Populate approved evidence if available; otherwise preserve abstention. |

0005 creates the embeddings table but does not populate it and does not change `source_records.index_status` or `embedding_version`. None of 0006-0008 enables indexing.

## Read-only production preflight SQL

Run this only in a separately authorized, read-only production session. It contains no DDL or DML. Save the result set with the migration approval record. The expected starting revision is `20260914_0004`; anything else requires a new review.

```sql
-- A. Revision, server, and schema inventory.
SELECT current_database() AS database_name,
       current_user AS role_name,
       current_setting('server_version') AS server_version,
       current_setting('server_version_num') AS server_version_num,
       pg_is_in_recovery() AS is_replica;

SELECT version_num AS alembic_revision FROM alembic_version;

SELECT c.relkind, n.nspname AS schema_name, c.relname AS object_name
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN (
      'alembic_version', 'ingestion_runs', 'source_records',
      'course_program_records', 'source_record_embeddings'
  )
ORDER BY c.relname;

SELECT table_name, column_name, data_type, udt_name, is_nullable,
       column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('source_records', 'ingestion_runs',
                     'source_record_embeddings')
ORDER BY table_name, ordinal_position;

SELECT conrelid::regclass AS table_name, conname,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
  AND conrelid IN (
      'public.source_records'::regclass,
      'public.ingestion_runs'::regclass
  )
ORDER BY table_name::text, conname;

-- B. pgvector availability/installation and indicative database privilege.
-- CREATE privilege is necessary but is not by itself proof that Cloud SQL permits
-- this extension; platform support and Qasim's migration role must also be verified.
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'vector';

SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';

SELECT has_database_privilege(current_user, current_database(), 'CREATE')
       AS role_has_database_create;

-- C. Corpus and envelope inventory.
SELECT domain, source_id, metadata_json ->> 'entity_type' AS entity_type,
       count(*) AS row_count
FROM source_records
GROUP BY domain, source_id, metadata_json ->> 'entity_type'
ORDER BY domain, source_id, entity_type;

SELECT record_id, source_id, domain, entity_id, canonical_url,
       metadata_json ->> 'entity_type' AS entity_type,
       status, index_status, embedding_version, content_hash
FROM source_records
ORDER BY domain, record_id;

SELECT record_id, domain, source_id, entity_id, canonical_url,
       metadata_json ->> 'entity_type' AS entity_type,
       CASE
         WHEN jsonb_typeof(metadata_json) <> 'object' THEN 'metadata_not_object'
         WHEN record_id IS NULL OR btrim(record_id) = '' THEN 'bad_record_id'
         WHEN source_id IS NULL OR btrim(source_id) = '' THEN 'bad_source_id'
         WHEN entity_id IS NULL OR btrim(entity_id) = '' THEN 'bad_entity_id'
         WHEN canonical_url IS NULL OR btrim(canonical_url) = '' THEN 'bad_url'
         WHEN content_hash !~ '^[0-9a-f]{64}$' THEN 'bad_content_hash'
         ELSE 'review_domain_contract'
       END AS issue
FROM source_records
WHERE jsonb_typeof(metadata_json) <> 'object'
   OR record_id IS NULL OR btrim(record_id) = ''
   OR source_id IS NULL OR btrim(source_id) = ''
   OR entity_id IS NULL OR btrim(entity_id) = ''
   OR canonical_url IS NULL OR btrim(canonical_url) = ''
   OR content_hash !~ '^[0-9a-f]{64}$'
ORDER BY domain, record_id;

-- Course URL guard used by 0006. Only canonical_lowercase and
-- normalizable_legacy_uppercase may proceed.
WITH course_urls AS (
  SELECT record_id, canonical_url,
         metadata_json ->> 'entity_type' AS entity_type,
         metadata_json ->> 'academic_year' AS academic_year,
         CASE WHEN metadata_json ->> 'entity_type' = 'course'
              THEN metadata_json ->> 'course_code'
              ELSE metadata_json ->> 'program_code' END AS code
  FROM source_records
  WHERE domain = 'courses'
    AND metadata_json ->> 'entity_type' IN ('course', 'program')
)
SELECT *,
       CASE
         WHEN canonical_url =
              'https://programsandcourses.anu.edu.au/' || academic_year || '/' ||
              entity_type || '/' || lower(code)
           THEN 'canonical_lowercase'
         WHEN canonical_url =
              'https://programsandcourses.anu.edu.au/' || academic_year || '/' ||
              entity_type || '/' || code
           THEN 'normalizable_legacy_uppercase'
         ELSE 'BLOCK_0006_unexpected_url'
       END AS migration_class
FROM course_urls
ORDER BY migration_class, record_id;

-- D. Existing Jobs rows: exact 0004 v1 compatibility and 0005 effect.
WITH jobs AS (
  SELECT *, ARRAY(
    SELECT jsonb_object_keys(metadata_json) ORDER BY 1
  ) AS actual_keys
  FROM source_records
  WHERE domain = 'jobs'
), checked AS (
  SELECT *,
    actual_keys = ARRAY[
      'category','classification','closing_at','closing_date','closing_text',
      'employment_types','entity_type','job_id','location','salary','status','summary'
    ]::text[] AS exact_v1_keys,
    source_id = 'jobs_anu_search'
      AND metadata_json ->> 'entity_type' = 'job'
      AND entity_id ~ '^[0-9]+$'
      AND metadata_json ->> 'job_id' = entity_id
      AND record_id = 'jobs:job:' || entity_id
      AND canonical_url ~ '^https://jobs[.]anu[.]edu[.]au/jobs/[^/?#[:space:]]+$'
      AND effective_from IS NULL AND effective_to IS NULL AS valid_identity,
    jsonb_typeof(metadata_json -> 'employment_types') = 'array'
      AND NOT jsonb_path_exists(metadata_json,
            '$.employment_types[*] ? (@.type() != "string")')
      AND jsonb_typeof(metadata_json -> 'entity_type') = 'string'
      AND jsonb_typeof(metadata_json -> 'job_id') = 'string'
      AND jsonb_typeof(metadata_json -> 'category') IN ('string','null')
      AND jsonb_typeof(metadata_json -> 'location') IN ('string','null')
      AND jsonb_typeof(metadata_json -> 'classification') IN ('string','null')
      AND jsonb_typeof(metadata_json -> 'salary') IN ('string','null')
      AND jsonb_typeof(metadata_json -> 'closing_text') IN ('string','null')
      AND jsonb_typeof(metadata_json -> 'closing_date') IN ('string','null')
      AND jsonb_typeof(metadata_json -> 'closing_at') IN ('string','null')
      AND jsonb_typeof(metadata_json -> 'status') IN ('string','null')
      AND jsonb_typeof(metadata_json -> 'summary') IN ('string','null')
      AND (metadata_json ->> 'status' IS NULL OR
           metadata_json ->> 'status' IN ('current','closed')) AS base_types_ok
  FROM jobs
)
SELECT record_id, source_id, entity_id, canonical_url, actual_keys,
       exact_v1_keys, valid_identity, base_types_ok,
       CASE
         WHEN exact_v1_keys AND valid_identity AND base_types_ok
           THEN 'expected_0005_action:add_role_requirements_json_null'
         ELSE 'BLOCK_review_or_reingest_before_0005'
       END AS migration_class
FROM checked
ORDER BY record_id;

-- Keep date/timestamp inspection explicit and non-casting so malformed values
-- cannot abort this read-only report before they are visible.
SELECT record_id,
       metadata_json ->> 'closing_date' AS closing_date,
       metadata_json ->> 'closing_at' AS closing_at,
       (metadata_json ->> 'closing_date' IS NULL OR
        metadata_json ->> 'closing_date' ~ '^\d{4}-\d{2}-\d{2}$')
         AS closing_date_lexically_iso,
       (metadata_json ->> 'closing_at' IS NULL OR
        metadata_json ->> 'closing_at' ~
          '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}([.]\d+)?)?(Z|[+-]\d{2}:\d{2})$')
         AS closing_at_lexically_iso
FROM source_records
WHERE domain = 'jobs'
ORDER BY record_id;
```

Continue with the resource and embedding checks in the same read-only session:

```sql
-- E. Accommodation/Support classification before 0008.
-- 0008 intentionally blocks known provisional rows and any unknown row.
WITH resource_rows AS (
  SELECT *, ARRAY(
    SELECT jsonb_object_keys(metadata_json) ORDER BY 1
  ) AS actual_keys
  FROM source_records
  WHERE domain IN ('accommodation', 'support')
), classified AS (
  SELECT record_id, domain, source_id, entity_id, canonical_url,
         metadata_json, actual_keys,
         CASE
           WHEN domain = 'accommodation'
            AND source_id = 'accommodation_anu_study'
            AND entity_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'
            AND record_id = 'accommodation:accommodation:' || entity_id
            AND metadata_json ->> 'entity_type' = 'accommodation'
            AND metadata_json ->> 'source_authority' = 'official_anu'
            AND actual_keys = ARRAY[
              'accommodation_type','advertised_rate','application_information',
              'audience','catering','contact','contract_term','eligibility',
              'entity_type','facilities','location','rate_exclusions',
              'rate_inclusions','room_types','source_authority'
            ]::text[]
             THEN 'known_provisional_BLOCK_0008_reingest'
           WHEN domain = 'support'
            AND source_id = 'support_anusa_student_assistance'
            AND entity_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'
            AND record_id = 'support:support_service:' || entity_id
            AND metadata_json ->> 'entity_type' = 'support_service'
            AND metadata_json ->> 'source_authority' = 'approved_anusa'
            AND actual_keys = ARRAY[
              'access_instructions','audience','categories','contact','cost',
              'entity_type','hours','location','source_authority'
            ]::text[]
             THEN 'known_provisional_BLOCK_0008_reingest'
           WHEN domain = 'accommodation'
            AND source_id = 'accommodation_anu_study'
            AND entity_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'
            AND record_id = 'accommodation:residence:' || entity_id
            AND canonical_url =
                'https://study.anu.edu.au/accommodation/our-residences/' || entity_id
            AND metadata_json ->> 'entity_type' = 'residence'
            AND actual_keys = ARRAY[
              'accessibility','advertised_rate','application_text','application_url',
              'audiences','category','catering_options','contact','cost_period',
              'eligibility','entity_type','features','location','overview','rooms',
              'vacancy_status'
            ]::text[]
             THEN 'frozen_candidate_validate_nested_shape'
           WHEN domain = 'support'
            AND source_id = 'support_anusa_student_assistance'
            AND entity_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'
            AND record_id = 'support:support_service:' || entity_id
            AND canonical_url =
                'https://anusa.com.au/student-assistance/' || entity_id || '/'
            AND metadata_json ->> 'entity_type' = 'support_service'
            AND actual_keys = ARRAY[
              'access','audiences','category','contact','cost','entity_type',
              'hours','purpose','referrals','topics'
            ]::text[]
             THEN 'frozen_candidate_validate_nested_shape'
           ELSE 'unknown_BLOCK_0008_manual_review'
         END AS migration_class
  FROM resource_rows
)
SELECT record_id, domain, source_id, entity_id, canonical_url, actual_keys,
       metadata_json ->> 'source_authority' AS source_authority,
       migration_class
FROM classified
ORDER BY migration_class, domain, record_id;

-- Critical nested-type indicators. A frozen_candidate is not approved until
-- these and the exact 0008 validator rules are satisfied.
SELECT record_id, domain,
       jsonb_typeof(metadata_json -> 'contact') AS contact_type,
       jsonb_typeof(metadata_json -> 'rooms') AS rooms_type,
       jsonb_typeof(metadata_json -> 'topics') AS topics_type,
       jsonb_typeof(metadata_json -> 'referrals') AS referrals_type,
       jsonb_path_exists(metadata_json, '$.**.source_authority')
         AS has_source_authority_anywhere
FROM source_records
WHERE domain IN ('accommodation', 'support')
ORDER BY domain, record_id;

SELECT source_id, entity_id, count(*) AS duplicate_count,
       array_agg(record_id ORDER BY record_id) AS record_ids
FROM source_records
WHERE domain IN ('accommodation', 'support')
GROUP BY source_id, entity_id
HAVING count(*) > 1;

-- F. Embeddings/index state. At a true 0004 database the table is expected
-- to be absent; do not run the last query until the first returns non-null.
SELECT to_regclass('public.source_record_embeddings') AS embeddings_table;

SELECT domain, index_status, embedding_version, count(*) AS record_count
FROM source_records
GROUP BY domain, index_status, embedding_version
ORDER BY domain, index_status, embedding_version;

SELECT count(*) FILTER (WHERE index_status = 'INDEXED') AS indexed_records,
       count(*) FILTER (WHERE index_status <> 'INDEXED') AS nonindexed_records,
       count(*) FILTER (WHERE embedding_version IS NULL) AS no_embedding_version
FROM source_records;

-- Run only if source_record_embeddings exists (normally after 0005):
SELECT count(*) AS embedding_rows,
       count(*) FILTER (
         WHERE e.source_content_hash <> r.content_hash
       ) AS stale_source_hash_rows,
       count(*) FILTER (
         WHERE r.embedding_version IS DISTINCT FROM e.embedding_version
       ) AS version_mismatch_rows,
       count(DISTINCT e.source_record_id) AS records_with_embeddings
FROM source_record_embeddings e
JOIN source_records r ON r.record_id = e.source_record_id;
```

Interpretation rules:

- Stop if the revision is not exactly `20260914_0004`.
- Stop if `vector` is unavailable, if platform support is not approved, or if the migration role lacks the required narrowly scoped capability.
- Stop for any `BLOCK_*` result.
- A `frozen_candidate_validate_nested_shape` result is not a pass by itself; compare the complete JSON with the exact 0008 functions. The migration's own guard remains authoritative.
- At a clean 0004 start, `source_record_embeddings` should be absent. After 0005 it should exist but may be empty; migration does not backfill vectors.
- Production outputs must be reviewed without copying credentials or personal data into tickets.

## Local release-candidate image and startup

| Item | Evidence |
|---|---|
| Source SHA | `ccd93b37510b585f734e8dd38f23f52ae8042c61` |
| Build command | `docker build --tag askanu-rag:day13-rc-ccd93b3 .` |
| Local tag | `askanu-rag:day13-rc-ccd93b3` |
| Build result | PASS; dependency integrity check in the image passed |
| Local image digest | `sha256:bd8326a80286eb49e8bf2fa2bb7f5524d242e0b921477324e22034a01c1509bc` |
| Push/deploy | None |

The container was booted with `ASKANU_ENV=production` and a `DATABASE_URL` that pointed only to the disposable PG18 container through `host.docker.internal:55432/askanu_test`. It was exposed only at local host port `127.0.0.1:58081`.

Before and after normal application startup, the database had the same:

- Alembic revision `20260916_0008`;
- three source rows (two Courses and one Scholarship in the pre-smoke snapshot);
- zero embedding rows;
- one ingestion run;
- exact record IDs, content hashes, timestamps, `index_status`, and `embedding_version` values.

`GET /health` returned HTTP 200 / `{"status":"ok"}`. The Docker command starts only `python -m askanu_rag.server`; code inspection and the snapshots agree that normal startup does **not** run Alembic, seed rows, generate embeddings, modify source rows, or change index state.

## Running-container API smoke

Smoke used only repository-owned fixtures inserted into the disposable `_test` database through the existing integration helpers. The fixture corpus was: Courses 3, Scholarships 3, Jobs 2, Accommodation 2, Support 2. These are synthetic contract fixtures, not production-source claims. No Gemini credential was supplied and no provider call was attempted.

| Domain/scenario | Representative request | HTTP / API status | Key result and provenance |
|---|---|---|---|
| Health | `GET /health` | 200 / `ok` | Service booted against PG18. |
| Courses prerequisites | `What are the prerequisites for COMP1110 in 2026?` | 502 / `error` | Controlled failure because production-style runtime requires Gemini synthesis and no real key was injected. No fact or provider detail leaked. Pytest deterministic and synthesis-contract coverage passed. |
| Courses learning outcomes | `What are the learning outcomes for COMP1110 in 2026?` | 502 / `error` | Same deliberate no-credential boundary. |
| Courses corequisites | `What are the corequisites for COMP1110 in 2026?` | 502 / `error` | Same deliberate no-credential boundary. |
| Program lookup | `What are the program requirements for BACCT in 2026?` | 502 / `error` | Same deliberate no-credential boundary. |
| Courses ambiguity | `What are the prerequisites for COMP1110?` | 200 / `needs_clarification` | Deterministic options were `COMP1110 (2026)`, then `COMP1110 (2027)`. |
| Pending selection | `COMP1110 (2026)` with returned pending state | 502 / `error` | Selection resolved, then reached the same missing-Gemini synthesis boundary. |
| New Chat isolation | `What are its prerequisites?` with empty history/state | 200 / `insufficient_evidence` | No old session fact was inherited. |
| Scholarship topic switch | Exact Scholarship value while Course clarification was pending | 200 / `ok` | Old Course pending state did not lock the new topic; official fixture URL returned. |
| Scholarship clarification | `Show me ANU scholarships` | 200 / `needs_clarification` | Three deterministic fixture options, no guessed choice. |
| Scholarship value | Exact undergraduate fixture value | 200 / `ok` | Returned `$5,000 test value` with the exact study.anu.edu.au fixture URL. |
| Scholarship closing date | Exact undergraduate fixture closing date | 200 / `ok` | Returned `2026-10-31` with source URL. |
| Scholarship eligibility | Exact fixture eligibility request | 200 / `ok` | Reported official requirements while explicitly refusing to determine personal eligibility; source URL present. |
| Jobs current | `GET /api/v1/jobs/current?limit=5` | 200 / `ok` | Two current fixture items, bounded by requested limit. |
| Jobs detail/status/closing | Exact Research Officer/123456 query | 200 / `ok` | Returned current status and closing `2026-09-27`, with exact jobs.anu.edu.au URL. |
| Jobs requirements | Exact Research Officer requirements | 200 / `ok` | Returned only the two stored fixture requirements, with source URL. |
| Accommodation exact | `Tell me about Yukeembruk accommodation` | 200 / `ok` | Exact residence facts and study.anu.edu.au residence URL. |
| Accommodation room/rate | Exact Yukeembruk rate and room query | 200 / `ok` | Published wording, room evidence, source URL, and explicit no-price/no-vacancy inference language. |
| Accommodation application/eligibility | Exact Yukeembruk query | 200 / `ok` | Published application and eligibility evidence with source URL. |
| Accommodation comparison | Compare Yukeembruk and Ursula Hall | 200 / `ok` | Both residences returned with both source URLs. |
| Accommodation live vacancy | `Does Yukeembruk have a live vacancy right now?` | 200 / `insufficient_evidence` | Null vacancy treated as unknown; application link did not become a vacancy claim. |
| Support exact/topic | `Can Academic Support help with a grade appeal?` | 200 / `ok` | Published Grade Appeal topic with ANUSA service URL; safety disclaimer preserved. |
| Support hours | Exact Academic Support hours | 200 / `ok` | Returned stored `Monday to Friday, 10 am to 4 pm`, with source URL. |
| Support null hours | Exact Financial Support hours | 200 / `insufficient_evidence` | Missing hours remained unknown. |
| Support null access | `How can I access Financial Support?` | 200 / `insufficient_evidence` | Missing access remained unknown. |
| Support referral | Exact Academic Support referral request | 200 / `ok` | Returned only the stored external ANU assessment link and described it as navigation, not a separate service. |
| Support safety | Ask for diagnosis and guaranteed immediate service | 200 / `insufficient_evidence` | Refused diagnosis, personal advice, and availability guarantee; service source retained. |
| Unknown Course | Prerequisites for `COMP9999` | 200 / `insufficient_evidence` | No source and no invented prerequisite. |
| Events | `What ANU events are on this weekend?` | 200 / `insufficient_evidence` | No Events fact, listing, or unsupported claim. |
| Generic off-topic | Sydney weather | 200 / `off_topic` | No unrelated answer or source. |

All successful factual responses included the expected approved fixture source URL. The Courses 502s are an external deployment-configuration gate, not a passed live synthesis smoke; this distinction must remain visible in release approval.

## Post-deployment E2E matrix (prepared, not executed)

Run immediately after a future authorized migration, population, and deployment. Replace bracketed identities with production records selected from the approved corpus. Preserve the full request/response artifacts and source URLs.

| Domain | Scenario/request | Expected status | Expected semantic result/evidence | Failure signal |
|---|---|---|---|---|
| Courses | `What are the prerequisites for [COURSE] in [YEAR]?` | `ok` | Exact structured prerequisite and matching Programs & Courses URL | 5xx; wrong year/entity; content-only guess; missing/wrong URL |
| Courses | `What are the learning outcomes for [COURSE] in [YEAR]?` | `ok` or `insufficient_evidence` only when field is null | Exact stored list; null never substituted with description | Unrelated fact substituted; fabricated outcome |
| Courses | `What are the corequisites for [COURSE] in [YEAR]?` | `ok` or grounded `insufficient_evidence` | Exact structured corequisite and same-record URL | Incompatibility/prerequisite substituted |
| Courses | `What are the program requirements for [PROGRAM] in [YEAR]?` | `ok` | Exact Program identity/year/requirements and URL | Course result, wrong year, or synthesis 502 |
| Scholarships | `Am I eligible for [SCHOLARSHIP]?` | `ok`/`insufficient_evidence` | Official criteria only plus personal-eligibility disclaimer and Finder URL | Personal eligibility determination or inferred criterion |
| Scholarships | `What is the value of [SCHOLARSHIP]?` | `ok` or grounded `insufficient_evidence` | Exact published value; no substitute field | Value inferred from title/content |
| Scholarships | `When does [SCHOLARSHIP] close?` | `ok` or grounded `insufficient_evidence` | Exact closing date; missing stays unknown | Opening date or another scholarship substituted |
| Scholarships | `Show me ANU scholarships` | `needs_clarification` | Fresh deterministic options | Silent arbitrary choice or stale option |
| Jobs | `GET /api/v1/jobs/current?limit=5` | `ok` | At most five current, non-expired rows in deterministic order with official URLs | Closed/expired job; more than five; missing URL |
| Jobs | `Tell me about job [ID]` | `ok` | Exact ID/title/details and source URL | Title collision or wrong ID |
| Jobs | `What are the role requirements for job [ID]?` | `ok` or grounded `insufficient_evidence` | Only `role_requirements`; null stays unknown | Summary/category substituted as requirements |
| Jobs | `What is the status of job [ID]?` | `ok` | Exact stored status | “Open” inferred from page existence |
| Jobs | `When does job [ID] close?` | `ok` or grounded `insufficient_evidence` | Exact closing wording/date/instant | Local-time guess or unrelated date |
| Accommodation | `Tell me about [RESIDENCE] accommodation` | `ok` | Exact residence and ANU residence URL | Wrong/partial residence silently chosen |
| Accommodation | `What rooms and published rates does [RESIDENCE] have?` | `ok` or grounded `insufficient_evidence` | Exact room/rate/contract wording; no final-price guarantee | Invented room/rate or vacancy inference |
| Accommodation | `How do I apply for [RESIDENCE]?` | `ok` or grounded `insufficient_evidence` | Published application text/link only | Generic or invented application process |
| Accommodation | `Does [RESIDENCE] have a vacancy now?` for a null field | `insufficient_evidence` | Explicitly says current live vacancy is unknown | “Available”/“unavailable” inferred from application/rate |
| Support | `Can [SERVICE] help with [TOPIC]?` | `ok` or grounded `insufficient_evidence` | Exact service/topic and approved ANUSA service URL | Diagnosis, legal/medical advice, or service guarantee |
| Support | `What are [SERVICE] hours?` when null | `insufficient_evidence` | Missing hours remain unknown | Guessed business hours or emergency coverage |
| Support | `How can I access [SERVICE]?` when null | `insufficient_evidence` | Missing access remains unknown | Invented booking/drop-in process |
| Support | `What topics does [SERVICE] cover?` | `ok` | Only stored topics and approved Student Assistance paths | Off-boundary/internal URL accepted or topic fabricated |
| Support | `What referrals does [SERVICE] provide?` | `ok` | Only stored external credential-free referrals; labelled navigation | Internal ANUSA Referral, credential URL, or service claim |
| Cross-cutting | Known identifier with absent fact | `insufficient_evidence` | No unrelated field substitution | `ok` with unsupported content |
| Cross-cutting | Clearly unrelated question | `off_topic` | No ANU factual claim/source | Hallucinated answer or internal error |
| Cross-cutting | Ambiguous entity/year | `needs_clarification` | Fresh deterministic options | Arbitrary selection; unstable order |
| Cross-cutting | Select returned option | `ok`/grounded abstention | Fresh retrieval; correct source | Answer copied from history or stale pending evidence |
| Cross-cutting | Topic switch while clarification is pending | New domain's valid status | Old pending state does not lock the request | Old-domain clarification repeated |
| Cross-cutting | Clear/New Chat then pronoun-only follow-up | `insufficient_evidence` | No prior-session context | Cross-session data leak |
| Cross-cutting | Every factual `ok` response | `ok` | `record_id`, `source_id`, title, domain, exact approved URL agree | Missing/mismatched provenance |
| Events | Events request before persisted integration is approved | `insufficient_evidence`/documented non-support | No event listing or event fact | Any unsupported Events claim |

Deployment acceptance must include successful Course responses with the authorized Gemini configuration; the local no-key 502 evidence is not a substitute.

## Production drift and readiness checklist

Current expected drift (to be verified, not treated as observed fact today):

- production DB is understood to be at `20260914_0004`; target is `20260916_0008`;
- deployed RAG is behind merged main SHA `ccd93b37510b585f734e8dd38f23f52ae8042c61`;
- the production corpus is currently tiny;
- persisted Events integration remains pending a frozen source/contract handoff.

Every item below must be true before deployment approval:

- [ ] Production starts at the reviewed revision, and the read-only preflight is saved and clean.
- [ ] PostgreSQL/Cloud SQL supports pgvector; extension availability/version and migration-role privileges are confirmed.
- [ ] Every existing Jobs row passes the exact 0004 check and expected 0005 null-key transition.
- [ ] No unknown/provisional Accommodation or Support row will trigger a 0008 guard.
- [ ] Courses URLs are canonical or exactly normalizable by 0006; all existing metadata satisfies 0005-0008 checks.
- [ ] Qasim/team explicitly approve the 0004 -> 0008 migration and its rollback limitations.
- [ ] The DB is migrated transactionally to the single head `20260916_0008` before the new service relies on it.
- [ ] Source ingestion/population is aligned to each frozen contract; no direct ad-hoc production rows are used.
- [ ] The scraper-side Support Referral validator mismatch is resolved before relevant production ingestion.
- [ ] Embedding model/version/dimension, retrieval policy, indexing authority, and backfill/refresh procedure are approved; migration alone does not index.
- [ ] Production DB credentials, service account/runtime grants, Gemini secret, model endpoint, request limits, and network path are correct.
- [ ] The deployed image is built from the approved exact candidate SHA and digest; no mutable tag substitution.
- [ ] The post-deploy matrix above is assigned, ready, and executed immediately after authorization.
- [ ] Operators understand that resource/subplan/Jobs downgrade guards can make rollback require explicit data handling.
- [ ] Monitoring and controlled-error behavior are observed without logging credentials or source content.
- [ ] No Events functionality or release expectation is added until the frozen Events contract is approved and integrated.

## Cross-repo contract status

The only confirmed remaining cross-repo contract issue is the scraper-side Support Referral validator mismatch. A read-only inspection of the exact PR #26 remote ref `refs/remotes/origin/will/v6-day12-accommodation-support` at `9db3f1a` found:

- scraper `CommonRecord` validates a Referral only as HTTP(S) with a non-empty netloc; it does not enforce the RAG contract's external-only, credential-free, no-port, no-query, and no-fragment boundary;
- the scraper parser excludes lowercase `anusa.com.au` / `www.anusa.com.au` Referral hosts but compares them case-sensitively and does not implement the complete validator boundary;
- RAG Python and 0008 SQL reject internal ANUSA Referral hosts case-insensitively and enforce the credential/port/query/fragment boundary.

This mismatch does not require a RAG schema widening. The scraper must align before Support production ingestion. No scraper file or ref was changed during this work.

## Events status

The existing schema-independent Events work remains isolated and counts as complete for:

- Australia/Canberra timezone handling;
- today, tomorrow, this Friday, and next week semantics;
- past-event exclusion;
- ascending ordering;
- deterministic limiting/ties;
- DST and date-boundary coverage.

Persisted Events integration remains pending the frozen source/contract handoff. This work did not implement or invent Events `source_id`, entity/record identity, canonical URL, persisted dates, venue/organiser, status/currentness, repository shape, `/api/v1/events/upcoming?limit=5`, Rubric persisted fields, or an approved-source flag. The isolated Events stash/branch was not applied or modified.

Pending Events integration is **not a Day 14 RC blocker** unless Qasim's approved release scope explicitly requires Events.

## Day 14 RC blockers

### Carmen-owned blockers

**None.** The merged RAG code gates passed, the handoff/preflight/E2E artifact is complete, and the only working-tree change is this review document. Carmen should review and hand off; no additional Carmen-owned implementation fix was found.

### External dependencies/blockers

1. Qasim/team must approve the release SHA, run/review the production read-only preflight, and authorize the 0004 -> 0008 migration and deployment sequence.
2. The future production environment must confirm Cloud SQL PostgreSQL/pgvector compatibility, migration-role privileges, and actual starting revision. Cloud SQL was not accessed today.
3. The existing production Jobs row must pass the exact preflight; its compatibility is proven by migration semantics, not by a production observation today.
4. The scraper-side Support Referral validator mismatch described above must be fixed before Support production ingestion. This is the only confirmed cross-repo contract mismatch.
5. The deployed runtime must have the authorized Gemini secret/model/network configuration. Without it, Course synthesis correctly fails closed with HTTP 502, as the local production-style smoke showed.
6. Approved source population and any embedding/index policy/backfill must be ready and separately authorized. Schema migration alone neither populates the corpus nor enables indexing.

### Informational risks that are not blockers

- Production-at-0004, deployed-RAG-behind-main, and tiny-corpus statements are current expectations, not observations from this task; the preflight converts them into evidence.
- The local RC container used synthetic repository fixtures. It proves runtime wiring and safety behavior, not production data coverage.
- Three third-party deprecation warnings remain, and the one Windows symlink test is skipped on this host; neither caused a functional failure.
- Downgrades deliberately refuse populated resource/subplan/Jobs states in specified cases. This is a rollback-planning constraint, not an upgrade defect.
- Persisted Events integration is pending but is not a blocker unless Events is explicitly added to the approved Day 14 release scope.

## Final validation after documentation

| Gate | Final result |
|---|---|
| Full suite with the local PG18 `_test` URL | **853 passed, 1 skipped, 3 warnings** in 12.46s |
| Focused PostgreSQL integration | **76 passed, 3 warnings** in 5.60s |
| Focused Day 12 migration | **10 passed** |
| `python -m pip check` | `No broken requirements found.` |
| `python -m compileall -q src tests migrations` | PASS |
| `python -m alembic heads` | `20260916_0008 (head)` |
| `python -m alembic current` against disposable PG18 | `20260916_0008 (head)` |
| `python -m alembic upgrade head --sql` | PASS; generated 954 lines and ended at `20260916_0008` / `COMMIT` |
| `git diff --check` | PASS |
| Final `git status --short` | `?? docs/V6_DAY13_RAG_RELEASE_READINESS_HANDOFF.md` |

The first offline-SQL invocation was intentionally refused because no database configuration was supplied. It was rerun successfully with the disposable local `_test` URL solely as Alembic dialect configuration; `--sql` did not connect to or mutate the database.

## Explicit no-production-action statement

- No Cloud SQL access.
- No production migration or production/shared database mutation.
- No RAG deployment and no container image push.
- No production indexing or indexing enablement.
- No scraper modification.
- No Events persisted implementation and no Events WIP merge.
- No Rubric expansion.
- No old migration edit; revisions 0004-0008 remain exactly as merged. If migration SQL changed, only 0008 would have been in scope, but **no migration SQL changed in Day 13**.
- No commit and no push.

Exact changed file: `docs/V6_DAY13_RAG_RELEASE_READINESS_HANDOFF.md` (new, intentionally untracked/uncommitted for Carmen review).
