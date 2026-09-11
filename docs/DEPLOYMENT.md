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
GEMINI_MODEL=gemini-3.5-flash-lite
MAX_OUTPUT_TOKENS=800
REQUEST_TIMEOUT_SECONDS=30
SEMANTIC_TOP_K=3
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
program, normalized-name/metadata and bounded TF-IDF planner paths therefore keep
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

Revision `20260911_0001` creates `course_program_records` with the 16 frozen
top-level fields, JSONB metadata, timezone-aware timestamps, stable `record_id`
primary key, schema checks, a unique `(entity_type, normalized_code,
academic_year)` expression index, plus title and `last_seen_at` indexes. It does
not auto-run at web startup and does not silently destroy data.

Current Day 5 retrieval is local sparse TF-IDF/cosine, not dense embeddings.
Accordingly this migration does **not** enable pgvector and the runtime does not
use pgvector. Future embedding/indexing work requires a reviewed migration and
must not be claimed as operational here.

For a disposable local PostgreSQL database, set a local-only `DATABASE_URL` and
run the command twice; the second invocation should report that the database is
already at head. Do not use production credentials. The same command is intended
for a dedicated reviewed migration job before a service revision depends on the
schema. It is never part of the web-container startup command.

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
  interface against the disposable local database.
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
7. Update the private `askanu-rag` service using the dedicated RAG identity.
8. Verify authenticated `/health`, exact Cloud SQL retrieval and real
   `/api/v1/ask` while recording request ID, HTTP/response status and latency.

Anonymous access must remain disabled. Browser/Firebase continues to call App
Cloud Run, whose dedicated runtime identity invokes the private RAG service.
