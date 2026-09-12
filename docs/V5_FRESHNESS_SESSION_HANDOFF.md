# V5 Freshness, Session Conversation and App Handoff

Date: 2026-09-12

Owner: Carmen (RAG/backend)
Contracts/integration/release: Qasim

This report describes the local V5 implementation. It does not claim that a
production embedding worker exists or that Qasim's integration/deployment gate
has passed. The frozen `/api/v1/ask` request and six-field response envelopes,
statuses, schema-v1 database fields and migration `20260911_0001` are unchanged.

## 1. Freshness and index lifecycle

Three states remain separate:

- source change state: `NEW`, `CHANGED`, `UNCHANGED`, `MISSING`;
- persistent embedding/index availability: `PENDING`, `INDEXED`, `FAILED`, plus
  an internally derived stale decision;
- deterministic fact availability: whether the current stored record can be
  read by an exact/metadata query, independently of vector availability.

### Transition table

| Previous/current state | Input event | Result | Index action |
|---|---|---|---|
| no record | scraper publishes `NEW` current content | `PENDING`, version `null` | one content-change task |
| any existing record | scraper publishes a different hash as `CHANGED` | `PENDING`, version `null` | one content-change task |
| `UNCHANGED` + `PENDING` | same hash observed | preserve `PENDING` and version | none |
| `UNCHANGED` + `FAILED` | same hash observed | preserve `FAILED` and version | none |
| `UNCHANGED` + `INDEXED` | same hash observed | preserve `INDEXED` and version | none |
| `UNCHANGED` + `PENDING`/`FAILED` | indexing owner explicitly retries | stored state remains until result | explicit `RETRY`, not a content-change task |
| `UNCHANGED` + old successful version | indexing owner explicitly rolls out a target version | old stored state remains until result | explicit `REINDEX_VERSION` |
| matching task + real success | worker returns the task's target version | `INDEXED`, target version | compare-and-set success write is permitted |
| matching task + failure | worker fails | `FAILED`; never claim success | compare-and-set failure write is permitted |
| task hash/record ID no longer matches current row | late worker result | preserve current row | discard stale result |
| `MISSING`, fetch/parser failure, or `SUSPICIOUS_ZERO` | ingestion observation/run failure | preserve last-known-good data | no deletion and no re-embedding signal |

`NEW`/`CHANGED` paired with `INDEXED`, or with a non-null old embedding version,
is rejected at the policy boundary. A successful result must report the target
version captured by its task. The future writer must use record ID plus content
hash as a compare-and-set condition so an old task cannot overwrite newer
content.

### Derived stale semantics

No `STALE` database enum, field or TTL is added. A persistent index is stale or
unusable when any of these is proven:

- `index_status` is `PENDING` or `FAILED`;
- `embedding_version` is missing;
- a reviewed persistent retriever declares a target version and the stored
  version differs;
- an async task's captured record ID/content hash differs from the current row.

`last_seen_at` alone proves only a successful observation, not that content was
embedded. The local `LocalTfidfRetriever` is an ephemeral sparse lexical ranking
over the fresh record snapshot; it is not a persistent embedding, does not write
`INDEXED`, and does not claim embedding success. A future persistent semantic
adapter opts into the lifecycle filter and receives only usable indexed records.

### Exact/vector independence and responsibility split

Exact course/program reads continue to use stored facts for `PENDING`, `FAILED`,
missing embedding version, and vector-provider outage. Code normalization,
explicit years, entity type constraints, unknown-code no-fallback, and
multi-year clarification remain enforced. The implementation is generic; the
COMP1110 test is a regression example, not a hard-coded exception.

Will/scraper owns fetch/parse, hash comparison, record upsert, source change
states and ingestion-run writes. Carmen/RAG owns validated read models,
deterministic retrieval, the non-mutating lifecycle decision/worker boundary and
retrieval safety. No real dense embedding worker, queue, provider, pgvector
index or result writer exists in this runtime. Qasim must approve any shared
schema or worker write-contract change.

## 2. Current-session conversation

The implemented order is:

```text
request validation
-> constrained current-chat entity/year/intent resolution
-> existing query planner
-> fresh deterministic/metadata/sparse retrieval
-> grounded response
```

Precedence is current explicit entity/year/correction or topic switch, then a
valid pending selection, then a reliable adjacent reference, then a unique
non-adjacent current-chat reference. Multiple entities/years produce
`needs_clarification`; they are not selected by recency or ranking when the
reference remains ambiguous.

Pending `first`/`second` uses option order. `both` is accepted only with
`allow_multiple: true`. A direct displayed option can identify the selection,
but its option ID is validated against the current catalog and all facts/labels/
URLs are reloaded from the record. Invalid/stale selections, corrections and
topic switches cannot be locked to old pending state.

There is no process-global session map, persistent chat table, account history
or cross-request memory. The App carries bounded history and pending state in
the existing request. Clear Chat removes visible messages and local context,
sends empty history plus `pending_clarification: null`, and restores the App's
`Try asking` UI. The backend needs no reset endpoint and cannot clear UI itself.

Only constrained identity/year/intent is derived from untrusted history. Raw
history is not sent to Gemini and is not included in default logs. Forged facts,
instructions and URLs in history are not evidence. Every follow-up re-reads the
repository, so a changed stored prerequisite is returned on the next turn.

## 3. App guided-intent handoff

Guided cards generate ordinary user-visible questions and valid existing
`/api/v1/ask` payloads. They do not carry hidden authoritative facts and do not
bypass retrieval. From a new session, each current App card below returns
`needs_clarification` for only its missing identity before any unsupported
answer. On later turns the App appends only the bounded visible turns needed for
current-chat meaning and copies the latest response `clarification` object into
`conversation_state.pending_clarification`. After resolution, correction, topic
switch or Clear Chat, it sends `null`.

### Card 1: Plan degree

Current App question: **What courses do I need for my degree?**

Purpose: start from an explicit stored program/year, without promising a degree
audit.

Collect: program code/name and academic year. Do not collect a student number or
grades in the URL.

```json
{
  "question": "What courses do I need for my degree?",
  "history": [],
  "conversation_state": {"pending_clarification": null}
}
```

New-session response: `needs_clarification` — `Which program or degree do you
mean?` Current support after a specific selection is exact stored program
overview and metadata when available.
Not supported: a complete rule engine, remaining-requirements audit, timetable
or authoritative completion plan. Missing/ambiguous evidence must clarify or
return `insufficient_evidence`.

### Card 2: Prerequisite

Current App question: **What are the prerequisites for this course?**

Purpose: retrieve the course's stored prerequisite text.

Collect: course code and, when known, academic year.

```json
{
  "question": "What are the prerequisites for this course?",
  "history": [],
  "conversation_state": {"pending_clarification": null}
}
```

New-session response: `needs_clarification` — `Which course do you mean?`
Current support after selection is implemented exact course/year retrieval with
fresh stored evidence. If the selected code has several years, show the backend
year clarification and carry it on the next request.

### Card 3: Can I take this course?

Current App question: **Can I take this course in my study plan?**

Purpose: show source-grounded requisites while clearly separating them from
permission to enrol.

Collect: course code/year and only the current-chat background the user chooses
to provide. Treat that background as unverified context, not a student record.

```json
{
  "question": "Can I take this course in my study plan?",
  "history": [],
  "conversation_state": {"pending_clarification": null}
}
```

New-session response: `needs_clarification` — `Which course do you mean?`
Current support after selection is conservative: the backend can return stored
prerequisite evidence but does not verify completion, waivers, program rules or
permission to enrol. It must not equate satisfying one prerequisite statement
with approval. Unsupported conclusions return `insufficient_evidence`.

### Card 4: Honours

Current App question: **Can I still qualify for honours?**

Purpose: start an honours information question without implying an eligibility
decision.

Collect: subject/discipline and optionally an explicit academic year.

```json
{
  "question": "Can I still qualify for honours?",
  "history": [],
  "conversation_state": {"pending_clarification": null}
}
```

New-session response: `needs_clarification` — `I can help find official honours
information, but I cannot assess eligibility. Which program or discipline are
you exploring?`

**App copy needs correction.** The current copy, `Check your eligibility and
what you need to apply.`, promises an eligibility check beyond the backend's
capability. Replace it with `Explore honours requirements and official ANU
information.` or `Find official information about honours requirements and
applying.` Honours discovery or eligibility is not a completed vertical slice.

### Continuation payload

For any card, a clarification continuation remains within the frozen contract:

```json
{
  "question": "first",
  "history": [
    {"turn_id": "t1", "role": "user", "content": "Tell me about COMP1100."},
    {"turn_id": "t2", "role": "assistant", "content": "Which academic year do you mean?"}
  ],
  "conversation_state": {
    "pending_clarification": {
      "id": "clar-course-comp1100-academic-year",
      "type": "entity_selection",
      "options": [
        {"id": "courses:course:COMP1100_2026", "label": "COMP1100 (2026)"},
        {"id": "courses:course:COMP1100_2027", "label": "COMP1100 (2027)"}
      ],
      "allow_multiple": false
    }
  }
}
```

The App must carry the exact backend clarification object; it should not invent
record IDs. On Clear Chat it discards this object and all carried history.

### URL state

Use only non-sensitive navigation hints such as:

```text
/?card=prerequisite&course=COMP1110&year=2026
/?card=program&program=BACCT&year=2026
/?card=honours&discipline=computer-science&year=2026
```

Do not put raw messages, grades, student IDs, profile data, pending objects,
credentials or secrets in URLs. URL values prefill visible inputs; they are not
evidence and must still become a normal validated question.

No public `intent`, `context`, `session_id` or `profile` request field is needed
for today's implementation. If a future App/RAG integration genuinely requires
one, it is a separate proposal requiring Qasim approval and synchronized
contract tests before use.

## 4. Implementation and acceptance report

### Changed files

- `src/askanu_rag/index_lifecycle.py`: pure lifecycle decisions, stale
  derivation and safe async-result identity checks.
- `src/askanu_rag/conversation.py`: stateless history/pending resolution.
- `src/askanu_rag/main.py`: resolver before the existing planner/retrieval path,
  plus controlled handling for known repository dependency failures.
- `src/askanu_rag/hybrid_queries.py`: opt-in persistent-index stale filtering.
- `src/askanu_rag/retrieval/semantic.py`: explicitly marks TF-IDF as
  non-persistent.
- `tests/test_index_lifecycle.py`: lifecycle and exact/vector independence.
- `tests/test_conversation.py`: follow-up, ambiguity, pending, reset, isolation,
  malicious history and fresh-fact tests.
- `tests/test_ask_contract.py`: preserves the existing no-evidence expectation
  while exercising the now-active history resolver.
- `docs/CONVERSATION_CONTRACT.md`: clarifies the existing frozen session rules.
- this file: lifecycle, App/Qasim handoff and acceptance evidence.

### Acceptance checklist

- [x] Changed/unchanged/index failure/recovery states are explicit and tested.
- [x] Current-chat follow-up works without persistent storage.
- [x] Empty history plus null pending resets backend request context; App UI
  responsibility is documented.
- [x] Raw full history is neither sent to Gemini nor written to default logs.
- [x] COMP1110 exact retrieval and the frozen response contract remain green.
- [ ] Real production embedding worker execution/result writes: not present and
  not claimed.
- [ ] Qasim integration/deployment gate: pending review; not claimed.

### Local verification

Run with the repository `.venv` and a repository-local pytest temporary path:

- focused/release-relevant suite: 322 collected, 321 passed, 1 skipped;
- full `python -m pytest`: 323 collected, 321 passed, 2 skipped;
- `python -m pip check`: `No broken requirements found`;
- `python -m compileall -q src tests`: passed;
- `git diff --check`: passed;
- trailing-whitespace scan across tracked changes and new files: passed;
- high-confidence credential scan across tracked changes and new files: passed;
- frozen `API_CONTRACT`, `DATA_SCHEMA`, `DECISION_LOG` and migrations diff:
  empty.

The symlink hardening test was skipped because this Windows account lacks the
privilege required to create a test symlink (`WinError 1314`). The underlying
loader hardening remains covered by its non-symlink tests; rerun under Windows
Developer Mode or an account with Create symbolic links permission.

`tests/test_postgres_integration.py` was skipped because
`ASKANU_TEST_DATABASE_URL` is unset. Inspection confirms the test refuses
non-loopback hosts and database names without an `_test` suffix, then performs
`TRUNCATE` and writes `course_program_records` plus `ingestion_runs`. This machine
has an existing running PostgreSQL 12 service of unknown ownership, which was
not used or modified. PostgreSQL 18, Docker and Podman were not available in
PATH or their standard Docker Desktop locations, so PostgreSQL 18 version,
migration head and the real integration test remain unverified. To run safely,
create a disposable PostgreSQL 18 database on loopback with a name ending
`_test`, set only `ASKANU_TEST_DATABASE_URL`, apply `python -m alembic upgrade
head`, confirm `20260911_0001 (head)`, and run the integration test.

Container build/startup could not be run because no container runtime is
installed at the checked locations. As a non-container runtime check, the
production app process started locally on port 8092, `/health` returned HTTP 200
with `{"status":"ok"}`, and an `/ask` call without production DB configuration
returned the frozen controlled HTTP 500 JSON. After the explicit repository
error handler was added, server logs contained the bounded request metrics and
no exception traceback. No external model, Cloud SQL, secret, image push or
deployment was used.

## 5. Review and decision handoff

Qasim should review that the internal task identity (`record_id`, `content_hash`,
target version) is sufficient for the future worker's compare-and-set write. No
schema/migration is requested today. If the future worker requires durable task
identity, retry counters, queue metadata or a new target-version field, stop and
approve that shared contract separately.

Ben/App can implement the four cards immediately using the legal payloads above,
with the stated capability labels and Clear Chat behavior. App UI completion is
not part of this RAG repository change.

## 6. Suggested commit and PR draft

Suggested commit message:

```text
feat: add V5 freshness policy and session conversation resolution
```

Suggested PR title:

```text
V5: add freshness lifecycle and current-session conversation resolution
```

PR draft status: prepared below; no commit or PR has been created.

```markdown
## V3 task
Day / task: **V5 — 12 Sep 2026: Freshness/index lifecycle + session conversation contract**

## What changed?

- Added a pure lifecycle policy for NEW/CHANGED/UNCHANGED/MISSING and
  PENDING/INDEXED/FAILED, including explicit retry/version-rollout decisions,
  derived stale semantics and content-hash task-result protection.
- Kept local TF-IDF explicitly non-persistent and added an opt-in stale filter
  boundary for a future persistent semantic adapter.
- Added stateless current-chat resolution before the existing planner for
  adjacent/non-adjacent course follow-ups, explicit switch/correction,
  multi-entity/year ambiguity and pending first/second/both/direct selections.
- Revalidate pending IDs and rebuild option labels from fresh stored records;
  raw history remains outside Gemini and default logs.
- Added a specific controlled repository dependency handler so production-path
  DB-unavailable responses remain HTTP 500 contract JSON without a Uvicorn
  exception traceback.
- Documented App Clear Chat responsibilities and legal guided-card payloads for
  Plan degree, Prerequisite, Can I take this course?, and Honours.
- Added lifecycle, conversation, freshness, isolation, security and documentation
  payload validation tests.

No API request/response field, status, schema-v1 field/enum, migration, source
or cloud configuration changed. The existing conversation contract is clarified
for V5 current-session and empty-session guided-card behavior, with Qasim's
approval recorded in `docs/DECISION_LOG.md`. No embedding worker, queue,
pgvector workflow, deployment, commit or PR was created.

## Acceptance criteria / verification

- [x] Today's listed V5 verification completed locally where tooling exists
- [x] Relevant tests pass
- [x] `git diff --check`
- [x] No unrelated scope added

Focused/release-relevant suite:

`python -m pytest -p no:cacheprovider --basetemp=.test-tmp/focused-final -o addopts= --disable-warnings tests/test_index_lifecycle.py tests/test_conversation.py tests/test_ask_contract.py tests/test_course_api.py tests/test_exact_retrieval.py tests/test_hybrid_planner.py tests/test_grounded_synthesis.py tests/test_gemini_provider.py tests/test_migrations.py tests/test_postgres_repository.py tests/test_handoff_loading.py tests/test_health.py tests/test_server.py`

Result: 322 collected; 321 passed; 1 skipped (Windows symlink privilege).

Full suite:

`python -m pytest -p no:cacheprovider --basetemp=.test-tmp/full-final -o addopts= --disable-warnings -ra`

Result: 323 collected; 321 passed; 2 skipped. The additional skip is the opt-in
PostgreSQL integration test because `ASKANU_TEST_DATABASE_URL` is unset.

`python -m pip check`, `python -m compileall -q src tests`, `git diff --check`,
changed/new-file whitespace scan and changed/new-file high-confidence credential
scan all pass.

## Contracts / architecture

- [x] No API field/schema/status contract changed
- [x] Existing conversation contract clarified for V5 current-session and
  empty-session guided-card behavior; Qasim approval recorded in the decision log

The frozen Browser -> App -> private RAG -> Cloud SQL/Gemini architecture,
response envelope/statuses, request fields, schema v1 and migration head remain
unchanged. The conversation behavior clarification is approved for this PR;
remaining Qasim integration checks still apply.

## Security / data

- [x] No secrets committed
- [x] No unapproved source introduced
- [x] No raw production prompt/history logging introduced

Pending clarification labels and history are untrusted context only. Record IDs
are revalidated against the current catalog; answer facts and URLs come from
fresh stored records. Known repository dependency failures return controlled
JSON without provider/connection details or server traceback logging.

## Evidence / screenshots

- Full suite: 321 passed, 2 environment skips.
- Local production-process `/health`: HTTP 200, `{"status":"ok"}`.
- Local production-process `/ask` without DB config: controlled HTTP 500 frozen
  envelope; bounded request log, no traceback.
- All five documented guided/continuation JSON payloads validate against the
  existing `AskRequest` model.
- No cloud mutation, deployment, image push, live request ID or Qasim integration
  approval is claimed.

## Blockers / carry-over

- A real embedding/index worker and DB result writer do not exist. Qasim should
  review the proposed internal task identity and compare-and-set boundary before
  any worker/shared-contract implementation.
- PostgreSQL 18 integration remains unverified: this host has only an unrelated
  PostgreSQL 12 service, no safe `_test` URL, and no Docker/Podman. Provision a
  disposable loopback PostgreSQL 18 database ending `_test`, apply migration
  `20260911_0001`, then rerun `tests/test_postgres_integration.py`.
- Container build/startup remains unverified because no container runtime is
  installed. Run the documented local build/health/API smoke when available.
- App UI Clear Chat and guided-card wiring remain Ben/App work. Carmen's local
  implementation is complete; Qasim's cross-repo integration gate remains open.
```
