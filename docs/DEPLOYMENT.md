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

The Dockerfile and production package path have been reviewed and exercised,
but an actual `docker build`, `docker run` and container `/health` request remain
pending because the current workstation has no compatible container engine.

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

The deployment pattern is documented for Qasim's authorised workflow; do not run
it as part of Carmen's Day 6 implementation:

```text
gcloud run deploy <RAG_CLOUD_RUN_SERVICE> \
  --project askanu-dev-gdg \
  --region australia-southeast1 \
  --image australia-southeast1-docker.pkg.dev/askanu-dev-gdg/askanu-containers/<RAG_IMAGE>:<GIT_COMMIT_SHA> \
  --service-account askanu-rag-runtime@askanu-dev-gdg.iam.gserviceaccount.com \
  --set-env-vars ASKANU_ENV=production,GOOGLE_CLOUD_PROJECT=askanu-dev-gdg,GOOGLE_CLOUD_LOCATION=australia-southeast1 \
  --set-secrets GEMINI_API_KEY=askanu-gemini-api-key:latest
```

The explicit `--service-account` prevents fallback to the default Compute Engine
service account. This identity is dedicated to the RAG service and should retain
only its required permissions. Qasim reports that it can access the two named
secrets and has Cloud SQL Client access; exact IAM role IDs and binding scopes
still require read-only policy confirmation. Never place a service-account key
file in the image. Cloud Run supplies the runtime identity through Application
Default Credentials, and Secret Manager bindings inject selected values into the
process environment.

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
The confirmed mappings are:

| Process environment variable | Secret Manager source |
|---|---|
| `GEMINI_API_KEY` | `askanu-gemini-api-key:latest` |
| `DB_PASSWORD` | `askanu-db-password:latest` |

The values above name secrets and versions, not their payloads. The DB secret is
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
