# DEPLOYMENT.md

V3 target:
```text
Browser
 -> Firebase Hosting
 -> App Cloud Run
 -> authenticated RAG Cloud Run
 -> Cloud SQL PostgreSQL + pgvector
 -> Gemini / Vertex AI

Cloud Scheduler
 -> Scraper Cloud Run Job
 -> safe DB/index update
```

The confirmed Day 6 GCP project is `askanu-dev-gdg` in
`australia-southeast1` (Sydney).

Use separate App/RAG/Scraper service identities, Secret Manager and least privilege.

Do not wait until final week. V3 requires an early real vertical slice:
`Firebase -> App -> RAG -> Cloud SQL -> one real course answer -> real source card`.

## Confirmed Day 7 GCP contract

Qasim supplied these non-sensitive foundation values:

| Resource | Confirmed value |
|---|---|
| Project | `askanu-dev-gdg` |
| Region | `australia-southeast1` |
| Dedicated RAG runtime identity | `askanu-rag-runtime@askanu-dev-gdg.iam.gserviceaccount.com` |
| Gemini Secret Manager secret | `askanu-gemini-api-key` |
| DB password Secret Manager secret | `askanu-db-password` |
| Artifact Registry repository | `askanu-containers` |
| Cloud SQL instance | `askanu-postgres-dev` |
| Cloud SQL connection name | `askanu-dev-gdg:australia-southeast1:askanu-postgres-dev` |
| Database / backend user | `askanu` / `askanu_backend` |
| Private RAG Cloud Run service | `askanu-rag` |
| Private RAG URL | `https://askanu-rag-6gqn2xc7ca-ts.a.run.app` |
| App runtime identity | `askanu-app-runtime@askanu-dev-gdg.iam.gserviceaccount.com` |

PostgreSQL is version 18 on the Enterprise `db-g1-small` zonal instance with
10 GB SSD, automatic growth enabled and a 20 GB cap. Qasim has confirmed the RAG
identity's Cloud SQL Client and named-secret access, and the App identity's
resource-level Cloud Run Invoker binding on `askanu-rag`. These are supplied
contract facts, not evidence of a live mutation by Carmen. The final RAG image
name, Git SHA tag and immutable digest remain `UNKNOWN` until the coordinated
build/deployment.

## Day 6 RAG container contract

Build from the repository root:

```text
docker build --tag askanu-rag:day6 .
```

The image starts `python -m askanu_rag.server`, binds to `0.0.0.0` and reads the
Cloud Run `PORT` environment variable exactly. If `PORT` is absent, the canonical
local RAG fallback is `8081`; Cloud Run's supplied value always overrides it. The
process runs as non-root UID/GID `65532`. The production app factory is
`askanu_rag.main:create_configured_app`; the legacy module-level `app` remains
the deterministic test entrypoint.

Local production-path smoke test:

```text
docker run --rm --name askanu-rag-day6 -p 8081:8081 \
  --env ASKANU_ENV=production \
  --env PORT=8081 \
  askanu-rag:day6
curl http://127.0.0.1:8081/health
```

Expected response:

```json
{"status":"ok"}
```

`/health` is intentionally shallow for Day 6. It confirms that the HTTP process
is serving without disclosing environment values, dependency diagnostics,
credentials, prompts or stack traces. Cloud SQL readiness is a Day 7 concern.

Local container verification completed successfully on Docker Desktop:

- `docker build --tag askanu-rag:day6 .` — passed; image tagged
  `askanu-rag:day6`.
- The documented `docker run` command — passed; the container started locally.
- `curl.exe -i http://127.0.0.1:8081/health` — passed with HTTP 200 and exact body
  `{"status":"ok"}`.

This is local container evidence only. The image has not been pushed to Artifact
Registry, no Cloud Run deployment has been performed, and cloud health has not
been verified.

## Artifact Registry and Cloud Run image strategy

Build an intentional image and push it later, in an authorised deployment
workflow, to the confirmed `askanu-containers` repository. Cloud Run should deploy
that explicit image; do not use a source-deploy workflow that silently selects a
separate source-deploy registry.

Until the image name is frozen, use this pattern only:

```text
australia-southeast1-docker.pkg.dev/askanu-dev-gdg/askanu-containers/<RAG_IMAGE>:<GIT_COMMIT_SHA>
```

Use a unique Git commit SHA tag for traceability. Tags are mutable and must not be
described as immutable rollback references. Record the deployed image digest and
use that digest as the immutable rollback reference.

## Stage A — Day 6 private health-only deployment

The Day 6 cloud goal is limited to proving that the container can run on Cloud
Run and serve `/health`. RAG is a private internal backend service. Anonymous
invocation must remain disabled, and Browser/Firebase clients must never call RAG
directly. App Cloud Run is the service boundary that will call RAG.

The deployment pattern is documented for Qasim's authorised workflow; do not run
it as part of Carmen's implementation:

```text
gcloud run deploy <RAG_CLOUD_RUN_SERVICE> \
  --project askanu-dev-gdg \
  --region australia-southeast1 \
  --image australia-southeast1-docker.pkg.dev/askanu-dev-gdg/askanu-containers/<RAG_IMAGE>:<GIT_COMMIT_SHA> \
  --service-account askanu-rag-runtime@askanu-dev-gdg.iam.gserviceaccount.com \
  --set-env-vars ASKANU_ENV=production \
  --no-allow-unauthenticated
```

The explicit `--service-account` prevents fallback to the default Compute Engine
service account. The explicit `--no-allow-unauthenticated` keeps RAG private. This
identity is dedicated to RAG and should retain only its required permissions.
Never place a service-account key file in the image; Cloud Run supplies the runtime
identity through Application Default Credentials.

Stage A does not require `GEMINI_API_KEY`, `DATABASE_URL`, `DB_PASSWORD`, a Cloud
SQL attachment, pgvector, migrations, scraper data or a real course query. Cloud
Run supplies `PORT` automatically. Verify the deployed `/health` endpoint using
an authenticated invocation by an authorised principal and expect HTTP 200 with
exact body `{"status":"ok"}`; anonymous browser curl is not the expected cloud
verification path.

Qasim has since confirmed resource-level Cloud Run Invoker permission for
`askanu-app-runtime@askanu-dev-gdg.iam.gserviceaccount.com` on `askanu-rag`.
This supplied state is not a reason to add auth middleware or change IAM in the
RAG repository; no project-level grant is required here.

## Stage B — reviewed Gemini/Cloud SQL Day 7 deployment

Qasim confirmed version 1 exists for both named secrets. The authorised,
coordinated deployment should bind the reviewed versions explicitly:

```text
--set-secrets GEMINI_API_KEY=askanu-gemini-api-key:1,DB_PASSWORD=askanu-db-password:1
```

Do not independently change these versions or use `:latest` without review.
Carmen's Day 7 implementation does not read either payload and does not change
the existing private service. The live migration, revision update and smoke test
remain Qasim-coordinated steps after review.

The reviewed Stage B deployment must explicitly attach the Cloud SQL instance;
IAM alone does not create the `/cloudsql/...` Unix socket inside the Cloud Run
revision. The coordinated command shape is:

```text
gcloud run deploy askanu-rag \
  --project askanu-dev-gdg \
  --region australia-southeast1 \
  --image australia-southeast1-docker.pkg.dev/askanu-dev-gdg/askanu-containers/<RAG_IMAGE>:<GIT_COMMIT_SHA> \
  --service-account askanu-rag-runtime@askanu-dev-gdg.iam.gserviceaccount.com \
  --add-cloudsql-instances askanu-dev-gdg:australia-southeast1:askanu-postgres-dev \
  --set-env-vars ASKANU_ENV=production,GOOGLE_CLOUD_PROJECT=askanu-dev-gdg,GOOGLE_CLOUD_LOCATION=australia-southeast1,CLOUD_SQL_INSTANCE_CONNECTION_NAME=askanu-dev-gdg:australia-southeast1:askanu-postgres-dev,DB_NAME=askanu,DB_USER=askanu_backend \
  --set-secrets GEMINI_API_KEY=askanu-gemini-api-key:1,DB_PASSWORD=askanu-db-password:1 \
  --no-allow-unauthenticated
```

This is documentation for Qasim's authorised deployment workflow, not a command
run by Carmen in this follow-up.

Qasim reports that the dedicated RAG identity can access the two named secret
resources and has Cloud SQL Client access. Carmen does not alter or independently
re-audit those bindings in this implementation. Secret Manager bindings inject
selected values into process environment at deployment/runtime configuration.

## Runtime configuration and Secret Manager boundary

Set these non-secret Cloud Run environment variables:

```dotenv
ASKANU_ENV=production
GOOGLE_CLOUD_PROJECT=askanu-dev-gdg
GOOGLE_CLOUD_LOCATION=australia-southeast1
CLOUD_SQL_INSTANCE_CONNECTION_NAME=askanu-dev-gdg:australia-southeast1:askanu-postgres-dev
DB_NAME=askanu
DB_USER=askanu_backend
GENERATION_MODEL=gemini-3.8-flash
GENERATION_THINKING_LEVEL=low
GENERATION_MAX_OUTPUT_TOKENS=4096
GENERATION_TIMEOUT_SECONDS=20
GENERATION_MAX_RETRIES=2
SPARSE_CANDIDATE_K=20
DENSE_CANDIDATE_K=20
FUSED_CANDIDATE_K=20
RRF_K=60
RERANK_MODEL=rerank-v4.0-fast
RERANK_TOP_N=5
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSION=768
EMBEDDING_VERSION=gemini-embedding-2:768:retrieval-format-v1:retrieval-unit-v2-structured
RETRIEVAL_FORMAT_VERSION=retrieval-format-v1
CHUNK_POLICY_VERSION=retrieval-unit-v2-structured
SEMANTIC_MIN_SCORE=0.2
```

Cloud Run supplies `PORT` and overrides the local `8081` fallback. Do not use the
fallback value to infer the deployed service port.
For the existing Day 6 health-only revision, `CLOUD_SQL_INSTANCE_CONNECTION_NAME`
and `DATABASE_URL` may remain unset. `COURSE_RECORDS_PATH` is only the existing local
schema-v1 file/directory handoff interface and is not the Day 7 database path.

Inject secret values through Cloud Run Secret Manager bindings into normal process
environment variables. Do not call the Secret Manager API from application code.
The intended mappings, once real secret versions exist and the relevant stage
requires them, are:

| Process environment variable | Secret Manager resource/version |
|---|---|
| `GEMINI_API_KEY` | `askanu-gemini-api-key:1` |
| `COHERE_API_KEY` | reviewed Cohere key secret/version before reranker enablement |
| `DB_PASSWORD` | `askanu-db-password:1` |

The values above name secret resources, not versions or payloads. The DB secret is
a password secret and must bind to `DB_PASSWORD`, not be misrepresented as a full
`DATABASE_URL`. The config also accepts a complete `DATABASE_URL` as a protected
optional interface if the team later creates an appropriate DSN secret. Day 7
must select and test one connection construction path after the instance,
connection name, DB name and DB user are confirmed. Do not commit secret payloads.
Do not mount or set
`GOOGLE_APPLICATION_CREDENTIALS` in Cloud Run; attach the least-privilege RAG
runtime service identity and use Application Default Credentials. The identity
needs Secret Manager access only to the selected secrets. Qasim reports existing
Cloud SQL Client access; Day 7 must verify the effective binding before connecting.

When `ASKANU_ENV=production`, the application reads process environment only and
does not load a local `.env`. Local development retains the existing explicit
`.env` interface, with process environment values taking precedence.

## Day 7 Cloud SQL repository

Production now selects `PostgresCourseProgramRepository` through the same
`CatalogReader` boundary used by the fixture implementation. Exact code/year,
program, normalized-name/metadata and bounded local BM25 planner paths therefore keep
the existing ordering and logic. Every row is read fresh with parameterised SQL
and validated back through `CourseProgramRecord`; `canonical_url`, `content_hash`,
JSON nulls and all 16 schema-v1 fields come from storage unchanged.

With `ASKANU_ENV=production`, missing database configuration fails closed on
`/api/v1/ask` with the frozen controlled JSON error. It never silently falls back
to fixture evidence. `/health` remains the deliberately shallow Day 6 process
check and still exposes only `{"status":"ok"}`.

The reviewed production connection uses:

```text
/cloudsql/askanu-dev-gdg:australia-southeast1:askanu-postgres-dev
```

with `DB_NAME=askanu`, `DB_USER=askanu_backend`, and `DB_PASSWORD` injected from
`askanu-db-password:1`. No service-account key or Secret Manager client is used in
application code. A protected `DATABASE_URL` remains supported for disposable
local PostgreSQL verification, but the frozen Cloud Run path uses the Unix socket
components above.

If Day 7 selects a composed DSN, the intended Unix-socket URL shape is:

```text
postgresql+psycopg://<DB_USER>:<DB_PASSWORD>@/<DB_NAME>?host=/cloudsql/<CLOUD_SQL_INSTANCE_CONNECTION_NAME>
```

Treat the complete URL as a secret because it contains database credentials.
Browser clients must never receive it or connect directly to Cloud SQL.

## Operational Day 7 migration entrypoint

The Day 7 one-shot entrypoint is:

```text
python -m alembic upgrade head
```

Qasim approved extending this existing Day 7 revision because it has not been
applied to live Cloud SQL. A disposable local database that was stamped with an
earlier draft of `20260911_0001` must be recreated before verification; Alembic
will not rerun an already stamped revision. Do not use this local reset guidance
against any shared or live database.

Revision `20260911_0001` creates `course_program_records` with the 16 frozen
top-level fields, JSONB metadata, timezone-aware timestamps, stable `record_id`
primary key, schema checks, a unique `(entity_type, normalized_code,
academic_year)` expression index, plus title and `last_seen_at` indexes. It also
creates the frozen minimal `ingestion_runs` audit table with a stable run ID,
source ID, timezone-aware start/completion timestamps, bounded run status,
non-negative persisted record counts and an optional error. It does not auto-run
at web startup and does not silently destroy data.

Current V7 retrieval retains local ephemeral BM25 over prefiltered source
snapshots and adds a configuration-gated dense/rerank path. BM25 is `k1=1.2`, `b=0.75`,
case-folded `[a-z0-9]+` tokens, title plus content, no stop-word removal or
stemming, positive scores eligible, deterministic record-ID tie breaking and
candidate Top-K 20. Gemini `gemini-embedding-2` supplies 768-dimensional dense
Top-20; exact cosine pgvector retrieval is version/hash/current-state scoped.
RRF (`k=60`) produces at most 20 candidates and Cohere `rerank-v4.0-fast`
selects at most five relevance candidates, with deterministic RRF fallback.
Hard filters and source rehydration remain application-owned.

The existing `vector` column is untyped/non-null and therefore 768-compatible;
the query explicitly requires matching dimensions. No migration is required.
There is no HNSW/IVFFlat index or vector operator class today. Build one only
after reviewed production-like measurement; do not imply ANN performance.

For a disposable local PostgreSQL database, set a local-only `DATABASE_URL` and
run the command twice; the second invocation should report that the database is
already at head. Do not use production credentials. The same command is intended
for a dedicated reviewed migration job before a service revision depends on the
schema. It is never part of the web-container startup command.

### Shared ingestion and indexing ownership

The RAG repository owns the shared migration/schema. Will's scraper owns record
upsert, `content_hash` comparison, change detection and writes to both shared
tables. Carmen does not implement scraper persistence or ingestion-run writer
logic here. `ingestion_runs` is durable audit/run state only; RAG retrieval does
not query it, add it to Gemini context or expose it through the public API.

The approved handoff uses the existing uppercase stored values:

- `NEW` and `CHANGED` -> `PENDING`, with `embedding_version = NULL`.
- `UNCHANGED` -> update `last_seen_at` and preserve `index_status` plus
  `embedding_version`; do not emit another indexing signal.
- `PENDING` is the downstream indexing signal. Indexing does not re-detect source
  changes.
- successful indexing -> `INDEXED` and set `embedding_version`.
- failed indexing -> `FAILED`; do not claim the current content is embedded.
- an unchanged row already `PENDING` or `FAILED` remains in that state, including
  its existing embedding version.
- `MISSING` or a failed source run preserves last-known-good data and triggers
  neither deletion nor re-embedding.

No scraper writer, live dense embedding call, production backfill or deployment
is performed by this implementation. The reviewed rollout order is: verify
schema/head; build deterministic V2 units; run the explicit bounded backfill;
record eligible/reused/indexed/failed/incomplete counts; validate version-scoped
768-dimensional cosine retrieval; review readiness and latency; then enable the
configured path. Removing provider credentials/config degrades safely to
exact/structured + BM25/RRF.

App Cloud Run may send `X-Request-Id` for cross-service correlation. RAG accepts
only a bounded safe-character value for logging and records it as
`upstream_request_id`, separately from the RAG-generated API `request_id`. Missing
or invalid upstream values are represented by fixed safe markers; invalid raw
values are not logged. The upstream header never replaces the six-field response
`request_id`.

### Locally verified Day 7 acceptance

The current Day 7 working tree completed the target-version acceptance on Docker
Desktop:

- A disposable `postgres:18` container reported PostgreSQL 18.6 and used database
  `askanu_test`, whose name satisfies the required `_test` suffix. Its host mapping
  was limited to `127.0.0.1:55433`; no Cloud SQL endpoint or production credential
  was used.
- The first `python -m alembic upgrade head` applied revision `20260911_0001`.
  `python -m alembic current` returned `20260911_0001 (head)`. A second upgrade
  completed successfully without reapplying the migration.
- `python -m pytest tests/test_postgres_integration.py -v` completed with
  `1 passed`. The test used the explicit `ASKANU_TEST_DATABASE_URL` safety
  interface against the disposable local database, persisted and read back one
  ingestion-run count row, and then exercised the unchanged COMP1110 DB/API path.
- `docker build --tag askanu-rag:day7 .` completed successfully.
- The Day 7 image started locally with `ASKANU_ENV=production` and `PORT=8081`.
  `GET http://127.0.0.1:8081/health` returned HTTP 200 and exact body
  `{"status":"ok"}` without DB or Gemini secrets.
- `docker run --rm askanu-rag:day7 python -m alembic heads` returned
  `20260911_0001 (head)`, confirming the migration is present in the application
  image.

The disposable PostgreSQL 18 and application containers were stopped and removed
after verification. The earlier disposable PostgreSQL 12 compatibility smoke
remains supplementary evidence but is no longer the only real PostgreSQL check.

### Pending coordinated Qasim cloud deployment

The following actions have not been performed by Carmen and remain pending in the
reviewed deployment workflow: live Cloud SQL migration or writes, live secret
binding changes, a new RAG Cloud Run revision, the cloud COMP1110 smoke, and cloud
request-ID/latency evidence. The image has not been pushed to Artifact Registry.
These coordinated live steps are not a blocker for Carmen's local Day 7 PR.

## Coordinated live sequence after review

1. Qasim reviews and merges the Day 7 RAG PR.
2. Build the exact merged Git commit and tag the image with its Git SHA.
3. Push to `australia-southeast1-docker.pkg.dev/askanu-dev-gdg/askanu-containers/...`.
4. Record the immutable image digest.
5. Run revision `20260911_0001` against Cloud SQL as an explicit reviewed step.
6. Bind `DB_PASSWORD=askanu-db-password:1` and
   `GEMINI_API_KEY=askanu-gemini-api-key:1` with the confirmed non-secret DB config.
7. Update the private `askanu-rag` service using the dedicated RAG identity and
   explicitly attach
   `askanu-dev-gdg:australia-southeast1:askanu-postgres-dev` to the revision.
8. Verify authenticated `/health`, exact Cloud SQL retrieval and real
   `/api/v1/ask` while recording request ID, HTTP/response status and latency.

Anonymous access must remain disabled. Browser/Firebase continues to call App
Cloud Run, whose dedicated runtime identity invokes the private RAG service.

## Day 9 Scholarships migration contract (local only)

Revision `20260913_0002` is followed by the narrow compatibility-view revision
`20260914_0003`; neither it nor the already deployed `20260911_0001` is edited.
Revision `0002` renames the existing
physical table in place to writable `source_records`, widens only the approved
source/domain and metadata constraints, preserves the course/program partial
unique identity, adds Scholarship URL-slug identity, and creates the
`course_program_records` Courses/Programs compatibility read view. It copies or
deletes no rows. Downgrade refuses to proceed while Scholarship rows exist.

Revision `0003` drops and recreates only `course_program_records` with the exact
same 16 columns and Courses source/domain filter, adding a top-level `OFFSET 0`
so PostgreSQL classifies the view as structurally non-updatable. It changes no
table, row, constraint, index, API field, projected column or Scholarship
contract. Its downgrade restores the exact prior simple-view definition from
`0002`.

Cloud SQL mutation still requires Qasim's operational approval. The safe live
order is: merge and build the exact reviewed SHA; migrate Cloud SQL through
`20260913_0002` to `20260914_0003`; deploy the compatible RAG revision; regress
Courses/Programs;
verify Scholarship reads; then update/deploy Will's adapter to write
`source_records` and enable only a controlled bounded proof. The old deployed
RAG can continue Courses/Programs reads through the compatibility view after the
migration; the new RAG must not deploy before the migration because it reads
`source_records`. The compatibility view is not the approved upsert target.

Qasim's PostgreSQL 18 live check found the `0002` simple view reported
`is_updatable = YES` and `is_insertable_into = YES`; `0003` corrects that
structurally without adding grants, revokes or triggers. Before migration,
Qasim must verify the actual live roles and record evidence that:

1. `course_program_records` reports `is_updatable = NO` and
   `is_insertable_into = NO`;
2. the old RAG role can `SELECT` `course_program_records`;
3. `INSERT` and `UPDATE` through that view fail under the intended runtime
   roles, so structural protection and grants are both tested;
4. the new RAG role can `SELECT` `source_records`;
5. the scraper writer role can write `source_records`; and
6. the existing COMP1110 path and stored values, hashes, timestamps and index
   state are unchanged under those exact permissions.

PostgreSQL 18 execution must also confirm the exact
`https://study.anu.edu.au/scholarships/find-scholarship/<slug>` boundary, the
frozen slug grammar, literal slug equality and null Scholarship effective-date
checks.

Keep the scraper PostgreSQL gate disabled until Qasim approves and deploys the
migration. No live migration, Cloud Run/Scheduler/IAM/secret change, production
write, image push, embedding worker, or pgvector workflow is part of Carmen's
local Day 9 work.

## Day 10 Jobs migration and release gates (local candidate)

Revision `20260914_0004` follows `20260914_0003` and extends only the bounded
shared constraints/indexes required by the frozen Jobs contract. It accepts the
`jobs_anu_search`/`jobs` source pair, exact Job metadata/identity/URL rules and
adds a partial unique Jobs identity index. It does not change the 16 columns,
copy data, modify `ingestion_runs`, or recreate `course_program_records`.
Downgrade refuses while Jobs rows exist rather than deleting or coercing them.

The deterministic endpoint is `GET /api/v1/jobs/current?limit=5`, with limits
1–20. PostgreSQL applies source/domain/status/date filtering, deterministic
closing-date and numeric-ID ordering, then the limit. It does not depend on
Gemini, vectors or successful indexing. Production remains fail-closed when the
required database is unavailable.

Live work remains Qasim-coordinated: review/merge the exact SHA; apply `0004` on
PostgreSQL 18; verify production-equivalent RAG reads and scraper writes; verify
the Day 9 compatibility view remains structurally non-updatable; use Will's
contract-aligned source-backed fixture/writer; run dry-run/zero-write evidence;
then prove controlled `NEW`, repeat `UNCHANGED`, failure preservation, Current
Jobs ordering, exact lookup and canonical URLs before discussing Scheduler or
write-gate enablement. No live/cloud step is performed by this local task.

## V6 revision 20260915_0005 — local only

`20260915_0005` is append-only after `20260914_0004`. It backfills Jobs
`role_requirements` to JSON null, adds the approved Accommodation/Support shared
record checks, enables pgvector and creates `source_record_embeddings`. It does
not change the 16 source-record columns or the read-only
`course_program_records` compatibility view, and it creates no ANN index.

Do not apply this revision to Cloud SQL until Qasim has reviewed:

1. Will's Jobs v2 and Accommodation/Support normalized contracts/fixtures;
2. the production embedding provider/model/version/dimension and secret path;
3. worker ownership and bounded invocation;
4. PostgreSQL 18 upgrade and downgrade on a disposable database;
5. old/new RAG reads, scraper writes, compatibility-view non-updatability and
   least-privilege grants; and
6. a frozen corpus evaluation supporting the selected threshold/top-k.

The table, indexer and query adapter are implemented and test-covered locally,
but are not wired into normal production startup. Production enablement remains
blocked on provider/model/dimension, effective retrieval-policy version,
credentials, worker ownership/invocation, evaluation thresholds and rollout
approval. V6 intentionally defines no historical-vector garbage collection.

Normal web startup never runs this migration or indexing. No production
migration, Cloud Run, IAM, Secret Manager, Scheduler or source-data change was
performed by the local V6 implementation.

## V6 revision 20260915_0006 — Courses-family local candidate

`20260915_0006` is append-only after `20260915_0005`; the migration graph has a
single head. It expands the existing Courses source/domain to Course, Program,
Major, Minor and Specialisation, normalizes the previously accepted exact
uppercase Course/Program URL path form to lowercase, and rejects unexpected
existing Courses URLs before changing constraints. It adds no table or public
API field and does not invent effective dates.

The revision recreates the structurally read-only `course_program_records` view
with an explicit `entity_type IN ('course', 'program')` predicate. Subplans are
stored in `source_records` and deliberately excluded from the compatibility
view. Downgrade refuses while any Subplan row exists.

Before any production migration, Qasim must verify on disposable PostgreSQL 18:

1. upgrade `0004 -> 0005 -> 0006` and the one-head graph;
2. preservation of existing Course/Program rows and lowercase canonical URLs;
3. acceptance/rejection of valid/invalid Subplan identity and URLs;
4. Course+Program visibility and Subplan exclusion in the compatibility view;
5. `is_updatable = NO`, `is_insertable_into = NO`, and intended role grants;
6. safe downgrade refusal with Subplan data; and
7. Will's synchronized deterministic content/metadata and independent 99%
   source-present coverage evidence for all five entity families.

The live URL migration also requires a read-only preflight before `0006`:

1. count every existing Course/Program row and group canonical URLs into the
   exact legacy uppercase form, already-lowercase target form, and unexpected
   form;
2. require the unexpected count to be zero and retain the IDs/URLs in the
   release evidence;
3. after upgrade, prove row count/identity/hash/timestamps are unchanged and
   every Courses-family URL exactly matches its lowercased metadata code; and
4. treat downgrade as schema rollback only: it does not uppercase URLs.
   Lowercase Course/Program URLs remain readable under the restored `0005`
   database shape and the compatible RAG URL model.

No production migration, deployment, push or external data write was performed.

## V6 revision 20260916_0008 — Day 12 Accommodation/Support local candidate

`20260916_0008` is append-only after `20260915_0007` and replaces only the six
Accommodation/Support constraints introduced by the provisional `0005`
contract. It freezes `accommodation:residence:<slug>` and
`support:support_service:<slug>`, exact canonical URLs, and the approved nested
metadata shapes. Accommodation `application_url` is limited to approved HTTPS
StarRez hosts; Support topic URLs remain inside the ANUSA Student Assistance
boundary and referral URLs must be external HTTP(S) destinations.

The upgrade runs its read-only preflight before dropping any constraint. Exact
frozen rows may proceed. Recognized provisional rows stop with a manual
re-ingestion message because the old shape cannot be converted without losing
meaning. Unknown rows stop for manual contract review. The migration performs no
row `UPDATE`, `DELETE`, or automatic JSON rewrite. Downgrade refuses while any
Accommodation or Support row exists.

Before any production migration, Qasim must verify on disposable PostgreSQL 18:

1. upgrade `0007 -> 0008`, one-head graph, and preservation of unrelated rows;
2. frozen Accommodation/Support acceptance plus invalid nested URL/type rejection;
3. exact identity/canonical-URL equality for both domains;
4. known-provisional and unknown-row fail-closed preflight behavior;
5. safe downgrade refusal with resource rows; and
6. compatible scraper image, runtime grants, database configuration, and staged
   writer/reader evidence.

No production migration, Cloud SQL mutation, deploy, scraper change, or live
StarRez fetch was performed by the Day 12 RAG task.
