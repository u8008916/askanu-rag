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

## Confirmed Day 6 GCP foundation

Qasim supplied these non-sensitive foundation values:

| Resource | Confirmed value |
|---|---|
| Project | `askanu-dev-gdg` |
| Region | `australia-southeast1` |
| Dedicated RAG runtime identity | `askanu-rag-runtime@askanu-dev-gdg.iam.gserviceaccount.com` |
| Gemini Secret Manager secret | `askanu-gemini-api-key` |
| DB password Secret Manager secret | `askanu-db-password` |
| Artifact Registry repository | `askanu-containers` |

The exact RAG Cloud Run service name/URL, Cloud SQL instance/connection name,
DB name/user and final RAG image name/tag convention remain `UNKNOWN`. Do not
infer them from the values above.

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

App-to-RAG identity-token invocation and IAM binding are Day 7 integration work.
At that stage, the App runtime identity should receive resource-level Cloud Run
Invoker permission on the RAG service. Do not grant an unnecessarily broad
project-level invoker role, and do not add auth middleware or token-flow code in
the Day 6 RAG PR.

## Stage B — Gemini-enabled / Day 7 deployment

The Secret Manager resource `askanu-gemini-api-key` exists, but a real Gemini API
key secret version is not yet guaranteed to exist. Only after a real version is
created and separately verified should the authorised deployment add:

```text
--set-secrets GEMINI_API_KEY=askanu-gemini-api-key:latest
```

Stage B can then verify a real grounded Gemini request and add the separately
confirmed Cloud SQL configuration, App-to-RAG authentication and Day 7 vertical
slice. Day 6 does not populate a secret version and does not claim that a
Gemini-enabled cloud revision or grounded cloud query already works.

Qasim reports that the dedicated RAG identity can access the two named secret
resources and has Cloud SQL Client access; exact IAM role IDs and binding scopes
still require read-only policy confirmation. Secret Manager bindings inject
selected values into process environment at deployment/runtime configuration.

## Runtime configuration and Secret Manager boundary

Set these non-secret Cloud Run environment variables:

```dotenv
ASKANU_ENV=production
GOOGLE_CLOUD_PROJECT=askanu-dev-gdg
GOOGLE_CLOUD_LOCATION=australia-southeast1
CLOUD_SQL_INSTANCE_CONNECTION_NAME=<UNKNOWN_CONNECTION_NAME>
DB_NAME=<UNKNOWN_DB_NAME>
DB_USER=<UNKNOWN_DB_USER>
GEMINI_MODEL=gemini-3.5-flash-lite
MAX_OUTPUT_TOKENS=800
REQUEST_TIMEOUT_SECONDS=30
SEMANTIC_TOP_K=3
SEMANTIC_MIN_SCORE=0.2
```

Cloud Run supplies `PORT` and overrides the local `8081` fallback. Do not use the
fallback value to infer the deployed service port.
For Day 6 health-only deployment, `CLOUD_SQL_INSTANCE_CONNECTION_NAME` and
`DATABASE_URL` may remain unset. `COURSE_RECORDS_PATH` is only the existing local
schema-v1 file/directory handoff interface and is not the Day 7 database path.

Inject secret values through Cloud Run Secret Manager bindings into normal process
environment variables. Do not call the Secret Manager API from application code.
The intended mappings, once real secret versions exist and the relevant stage
requires them, are:

| Process environment variable | Secret Manager resource |
|---|---|
| `GEMINI_API_KEY` | `askanu-gemini-api-key` |
| `DB_PASSWORD` | `askanu-db-password` |

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

## Cloud SQL expectations for Day 7

Day 6 does not add a database driver, open a database connection or change the
existing fixture-backed query behaviour. Day 7 is expected to:

1. use the Cloud SQL for PostgreSQL instance after its metadata is confirmed,
   adding pgvector only if the reviewed Day 7 migration requires it;
2. attach the instance to the RAG Cloud Run service;
3. verify the reported least-privilege Cloud SQL Client access on the RAG identity;
4. bind the confirmed DB password secret to `DB_PASSWORD`, configure confirmed
   `DB_NAME`/`DB_USER`, and set
   `CLOUD_SQL_INSTANCE_CONNECTION_NAME` as non-secret configuration;
5. connect through the Cloud SQL Unix socket at
   `/cloudsql/<CLOUD_SQL_INSTANCE_CONNECTION_NAME>` (or a separately documented
   private-IP path); and
6. preserve parameterised SQL and the frozen schema-v1 record semantics.

If Day 7 selects a composed DSN, the intended Unix-socket URL shape is:

```text
postgresql+psycopg://<DB_USER>:<DB_PASSWORD>@/<DB_NAME>?host=/cloudsql/<CLOUD_SQL_INSTANCE_CONNECTION_NAME>
```

Treat the complete URL as a secret because it contains database credentials.
Browser clients must never receive it or connect directly to Cloud SQL.

## Day 7 migration entrypoint

The planned Day 7 one-shot entrypoint is:

```text
python -m alembic upgrade head
```

This command is not operational on Day 6: Alembic is not installed and the repo
has no `alembic.ini` or migration environment. Day 7 must first add and review the
versioned migration files, Alembic dependency/configuration and database adapter.
Once implemented, run the command as a dedicated migration job or explicit
release step using the migration identity/configuration before deploying a
service revision that depends on the new schema. Do not run migrations in every
web-container startup, and do not report migration success until the Day 7
implementation exists and has been exercised against the target database.

Day 7, not Day 6, owns real Cloud SQL connection, schema migration, pgvector
enablement, durable persistence, data loading and the deployed COMP1110 proof.
