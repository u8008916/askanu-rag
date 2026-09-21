# V6 Day 16 six-domain RAG release verification

Date: 2026-09-21

Status: **GO for the RAG release candidate**. The six-domain application,
contract, migration, PostgreSQL 18 + pgvector, offline-SQL, dependency and
source-tree gates pass. Production migration and deployment remain separate
release-owner actions and were not performed.

## Git and scope

- PR: [#33 — Day 16: verify six-domain RAG release readiness](https://github.com/u8008916/askanu-rag/pull/33)
- Branch: `carmen/day16-six-domain-release-verification`
- Verification base/main SHA:
  `34f67acfcfb2085b347a38d7565b2aa1c1ec85b4`
- PR head before this documentation-only reconciliation:
  `87715fcf3edbc4a044b99342e33afcdfba593128`
- Day 16 implementation and verification changes: committed and pushed to PR
  #33
- Scraper evidence: merged scraper `main` at `c23d4f1`
  (`Day 15: complete Events ingestion safeguards (#32)`)
- Alembic head: exactly `20260921_0010`
- This handoff correction changes documentation only; the resulting current PR
  head is the latest commit shown on PR #33
- V7 work: none

## Producer-to-consumer Event gate

The deterministic official and Rubric serializations from the merged scraper
evidence were copied without semantic changes into
`fixtures/day16_scraper_event_records.json`. Both pass the actual RAG
`CommonRecord -> EventRecord` boundary and the fresh PostgreSQL persistence
gate.

| Field | Official representative | Rubric representative |
|---|---|---|
| `source_id` | `events_anu_official` | `rubric_unified_search` |
| `domain` | `events` | `events` |
| `entity_type` | `event` | `event` |
| `source_event_id` | `1001` | `78459` |
| `entity_id` | `1001` | `rubric-78459` |
| `record_id` | `events:event:1001` | `events:event:rubric-78459` |
| canonical URL | `https://www.anu.edu.au/events/window-opening` | `https://campus.hellorubric.com/?eid=78459` |
| content hash | `31a1c414bd822e2e35c895a05799b6eb3494dca89800ed7efdf13b78f4c821b7` | `3e103cb9abcb83dc6c5138083b4837a3b9b6fd00fcfafd489faf430dda78b9bf` |

Title, content, timestamps, frozen metadata, canonical URL, source ID and hash
survive without identity rewriting, aliases, invented fields, source mutation
or provenance loss.

- Official producer -> consumer -> PostgreSQL: **PASS**
- Rubric producer -> consumer -> PostgreSQL: **PASS**

## Release-critical defects found and fixed

Two consumer defects were exposed by Day 16 verification.

1. Upcoming currentness used only `start_at >= now`, excluding an official
   Event that had started but had a known future `end_at`. In-memory, chat and
   PostgreSQL Upcoming paths now use known `end_at` as the currentness boundary
   and fall back to `start_at` only when the end is unknown. Ordering remains
   ascending `start_at`, then `record_id`.
2. The consumer accepted disagreement between `source_event_id` and stable
   source identity. Python and additive migration `20260921_0010` now enforce
   official `entity_id == source_event_id`; Rubric requires
   `entity_id == "rubric-" + source_event_id` and the same public URL `eid`.
   `record_id` remains the established `events:event:<entity_id>` convention.

Both are consumer regressions. The merged producer records are correct and pass
the tightened boundary unchanged. No new contract or compatibility alias was
invented.

## Migration-history correction

`migrations/versions/20260919_0009_events_contract.py` is restored exactly to
the merged-main version. The Day 16 source-identity check is preserved in the
new append-only migration:

```text
20260919_0009 -> 20260921_0010
```

Revision `20260921_0010`:

- creates only `ck_source_records_event_source_identity` on `source_records`;
- adds no table, column, metadata key or changed identity rule;
- enforces the frozen official and Rubric identity relationships; and
- has a safe downgrade that drops only that new check constraint.

Static and real-PostgreSQL regressions prove that 0009 has no Day 16 edit, 0010
upgrades from 0009, the identity check is enforced, downgrade removes only the
new check, pre-existing 0009 constraints/index remain, and exactly one Alembic
head exists.

## Strict metadata and provenance

The only accepted Event metadata keys remain:

`entity_type`, `source_event_id`, `start_at`, `end_at`, `timezone`,
`organiser_name`, `venue_name`, `address`, `latitude`, `longitude`, `category`,
`tags`, `registration_url`, `source_status`, `cancellation_status`, `audience`.

Verification proves:

- the merged producer vocabulary passes and arbitrary keys fail;
- `format`, `registration_links` and generic metadata `status` are not aliases;
- date-only timestamps fail rather than becoming invented midnight;
- official provenance remains on the approved public ANU Event detail boundary;
- Rubric provenance remains the public Rubric Event page;
- the internal Rubric detail API is rejected; and
- missing optional facts remain null/unknown, with no invented admission,
  ticket, registration, modality, address, organiser or cancellation claim.

## Event API, chat and temporal behavior

`GET /api/v1/events/upcoming` is **PASS**:

- admits `events_anu_official` only and excludes Rubric;
- excludes ended/past official Events;
- retains an Event until a known `end_at`;
- safely serializes missing optional fields as null;
- sorts by aware start instant then stable record ID;
- applies the deterministic limit after filtering and ordering;
- accepts `1..20` and returns controlled HTTP 400 outside that range; and
- returns `status=ok, items=[]` when no Events exist.

Events chat is **PASS**: both stored sources enter the candidate set, provenance
stays distinct, no evidence returns `insufficient_evidence`, and missing
optional facts are not invented.

Temporal tests cover today, tomorrow, this Friday, next week, past and ongoing
Events, inclusive start/exclusive window end, stable ties, aware UTC and
Canberra inputs, and the daylight-saving transition. Naive and date-only
instants fail closed.

## No live Rubric request from RAG

RAG contains no runtime call to Rubric search/detail endpoints. It only selects
stored Rubric records and validates public canonical URLs. The architecture
remains:

```text
source -> scraper -> source_records -> RAG -> App/chat
```

## Cross-source duplicates

RAG identity is exact `record_id`; there is no fuzzy title/time/venue merge.
Dedicated Upcoming is official-only. Conversational retrieval may expose an
official and Rubric representation of the same real-world Event, each with its
own provenance. This remains an informational presentation risk, not a V6 RC
blocker while provenance is explicit.

## Six-domain regression

The explicit-path matrix passed 277 tests:

- Courses: exact course/prerequisite retrieval and official source — **PASS**
- Scholarships: named Scholarship retrieval and provenance — **PASS**
- Jobs: current-job fixture/API behavior and approved source — **PASS**
- Accommodation: exact residence and unknown/safety behavior — **PASS**
- Support: exact topic/service routing and safety behavior — **PASS**
- Events: official Upcoming plus official/Rubric chat behavior — **PASS**

No Events change regressed the shared repository or retrieval envelope.

## Fresh PostgreSQL 18 + pgvector gate

A new empty disposable database in the existing local
`pgvector/pgvector:pg18` container was used. It was not Cloud SQL. PostgreSQL
reported version 18.6. The complete migration chain ran from base through 0009
and additive 0010.

- `alembic upgrade head`: **PASS**
- `alembic current`: `20260921_0010 (head)`
- PostgreSQL integration: `88 passed, 3 warnings`
- Events migration: `7 passed`
- Full RAG suite: `909 passed, 1 skipped, 3 warnings`
- Existing skip: Windows symlink privilege only

The real database suite covers exact producer records, Event source-identity
negatives, the 0010 downgrade/upgrade round trip, preservation of the five
pre-Event domains, Event index existence, official-only Upcoming SQL, and
non-destructive migration behavior.

## Failure, observability and security

- Database unavailable: controlled error envelope; no knowledge fallback.
- No Events: empty successful Upcoming list and grounded chat abstention.
- Malformed metadata: rejected at model/database boundaries.
- Optional fields missing: safe null/unknown behavior.
- No raw prompt/history, credential or secret logging change.
- Production credentials remain injected, not committed.
- Private App-to-RAG authentication expectations are unchanged.
- No startup schema mutation was added.

No security regression was found.

## Production delta — read only

- Current merged main SHA: `34f67acfcfb2085b347a38d7565b2aa1c1ec85b4`
- Deployed Cloud Run revision/image digest: unavailable from this host
- Current production migration revision: unverified
- Target migration revision: `20260921_0010`
- Events API/consumer contract deployed: unverified
- Deployment required to release the application delta: **YES**

No production state is inferred from missing access. This uncertainty does not
invalidate the tested RAG release-candidate artifact; it remains an external
production rollout gate.

## Verification results

- Focused Events: `44 passed, 3 warnings`
- Six-domain explicit matrix: `277 passed, 3 warnings`
- Events migration: `7 passed`
- PostgreSQL integration: `88 passed, 3 warnings`
- Full RAG: `909 passed, 1 skipped, 3 warnings`
- `python -m pip check`: **PASS**, no broken requirements
- `python -m compileall -q src tests migrations`: **PASS**
- `python -m alembic heads`: `20260921_0010 (head)`
- `python -m alembic upgrade head --sql`: **PASS** through 0010
- `git diff --check`: **PASS**; line-ending notices only

The warnings are dependency deprecations from Starlette/FastAPI/Google GenAI,
not Day 16 failures.

## Safety confirmations

- Historical migration 0009 edited: **NO; it matches merged main exactly**
- Earlier migration edited: **NO**
- Production DB write/migration: **NO**
- Cloud SQL access: **NO**
- Deployment or production indexing: **NO**
- Live Rubric call: **NO**
- Scraper checkout/source modification: **NO**
- Day 16 implementation committed and pushed to PR #33: **YES**
- This documentation correction committed and pushed to PR #33: **YES**

## Day 16 decision and blockers

- RAG Day 16: **GO**
- Migration `20260921_0010`: **READY**
- Six-domain RAG RC: **GO**

Carmen-owned blockers: **none identified**.

External production dependencies, not RAG RC blockers:

1. Qasim/release-owner confirmation of the deployed revision, immutable image
   digest and production migration revision before authorizing migration and
   deployment.

Informational non-blockers:

- conversational Event results may show separate official and Rubric records
  for one real-world Event because V6 adds no fuzzy entity resolution; and
- production state was not queried or changed during this verification.
