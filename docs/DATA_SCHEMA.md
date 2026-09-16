# DATA_SCHEMA.md

Shared Scraper -> storage/DB -> RAG normalized record contract.

## Schema version

**Shared normalized record schema v1**

Frozen for the first AskANU Courses/Programs vertical slice on 2026-09-06.

This document defines the serialized boundary between:

```text
askanu-scraper
    -> normalized record
    -> local storage / DB
    -> askanu-rag
```

The scraper and RAG repositories may use different internal Python classes,
but the serialized record crossing this boundary MUST follow this contract.

Do not copy scraper implementation into the RAG repository.

---

# 1. Common normalized record

A normalized record contains these top-level fields:

| Field | Serialized type | Nullable | Meaning |
|---|---|---:|---|
| `record_id` | string | no | Stable globally unique AskANU record identifier |
| `source_id` | string | no | Stable ID of the approved source registry entry |
| `entity_id` | string | no | Stable logical entity identity for this academic-year record |
| `domain` | string | no | AskANU domain |
| `title` | string | no | Source-derived normalized title |
| `content` | string | no | Canonical normalized text used for retrieval/embedding and hashing |
| `canonical_url` | URL string | no | Official source URL for this record |
| `status` | string enum | no | Scraper ingestion/change state |
| `effective_from` | ISO-8601 datetime | yes | Source-supported effective start, when available |
| `effective_to` | ISO-8601 datetime | yes | Source-supported effective end, when available |
| `collected_at` | ISO-8601 datetime | no | Time this source record was collected |
| `last_seen_at` | ISO-8601 datetime | no | Most recent successful observation of this record |
| `content_hash` | string | no | Lowercase SHA-256 hex digest of `content` |
| `embedding_version` | string | yes | Effective model plus retrieval-policy rollout version if/when embedding has occurred |
| `index_status` | string enum | no | Indexing state |
| `metadata_json` | JSON object | no | Domain-specific normalized metadata |

Unknown top-level fields are not part of schema v1.

RAG models MAY use strict validation such as `extra="forbid"` provided they
declare every schema-v1 top-level field above.

---

# 2. Required vs optional fields

The following top-level fields are REQUIRED and MUST NOT be null:

```text
record_id
source_id
entity_id
domain
title
content
canonical_url
status
collected_at
last_seen_at
content_hash
index_status
metadata_json
```

The following top-level fields MAY be null when no supported value exists:

```text
effective_from
effective_to
embedding_version
```

A missing required identity/provenance field makes the normalized record invalid.

Do not invent a replacement value for a missing required source identity field.
Reject/flag the record instead.

---

# 3. Domain values

Current schema-v1 domain values remain:

```text
courses
scholarships
jobs
accommodation
support
events
```

`events` is reserved/planned contract vocabulary. It is not accepted by the
current `CommonRecord` runtime union and no Events ingestion/retrieval behavior
is implemented by the V6 work.

ANU Courses and ANU Programs both use:

```text
domain = "courses"
```

Their entity type is distinguished inside `metadata_json` and in `record_id`.

---

# 4. Record status

Allowed `status` values:

```text
NEW
CHANGED
UNCHANGED
MISSING
```

Meanings:

- `NEW`: no previous logical record exists.
- `CHANGED`: same logical record exists but `content_hash` changed.
- `UNCHANGED`: same logical record and same `content_hash`.
- `MISSING`: previously known record was not observed; this does not mean immediate deletion or cancellation.

Fetch/parser failures preserve last-known-good data.

A suspicious many-to-zero result MUST fail/review the run rather than mark all
records missing or delete them.

The scraper owns record upsert, `content_hash` comparison and assignment of these
change states. The indexing side consumes the resulting `index_status`; it does
not independently re-detect `NEW` or `CHANGED`.

---

# 5. Index status

Allowed `index_status` values:

```text
PENDING
INDEXED
FAILED
```

Meanings:

- `PENDING`: DB/record exists but indexing/embedding is not complete.
- `INDEXED`: required indexing/embedding completed successfully.
- `FAILED`: indexing/embedding failed.

DB success plus embedding failure MUST NOT appear as `INDEXED`.

Day 2 deterministic exact retrieval does not need to use this field for lookup
yet, but it MUST be able to accept/preserve it.

The approved scraper-to-indexing handoff is:

- `NEW` -> `index_status = PENDING` and `embedding_version = null`.
- `CHANGED` -> `index_status = PENDING` and `embedding_version = null`.
- `UNCHANGED` -> update `last_seen_at`, preserve the existing `index_status` and
  `embedding_version`, and emit no new indexing signal.
- indexing success -> `index_status = INDEXED` and set `embedding_version`.
- indexing failure -> `index_status = FAILED`; do not claim the current content
  is embedded.

`PENDING` is the downstream indexing handoff signal. If an `UNCHANGED` record is
already `PENDING` or `FAILED`, the scraper preserves that exact state and its
existing `embedding_version`; it does not reset the state or create a second
change signal. The indexing/retry owner may retry it independently.

`MISSING`, fetch failure and parser failure preserve the last-known-good record.
They do not delete it and do not create a re-embedding signal.

The scraper may clear `embedding_version` for `NEW` or `CHANGED`, but it never
sets a new successful embedding version. The indexing side owns that successful
update. This contract does not imply that dense embeddings or pgvector are
implemented in the current Day 7 runtime.

---

# 6. ID semantics

## `source_id`

`source_id` identifies the approved source definition.

It does NOT identify:

- the course,
- the program,
- an academic year,
- or an individual webpage.

For ANU Programs & Courses schema v1:

```text
source_id = "courses_programs_and_courses"
```

The source registry remains owned by the scraper/data side.

---

## `entity_id`

`entity_id` identifies one normalized course/program entity for one academic
year.

### Course

Format:

```text
<COURSE_CODE>_<ACADEMIC_YEAR>
```

Example:

```text
COMP1100_2026
```

### Program

Format:

```text
<PROGRAM_CODE>_<ACADEMIC_YEAR>
```

Example:

```text
BACCT_2026
```

Academic year is part of `entity_id` because multiple years of the same
course/program MUST be able to coexist.

The same `entity_id` remains stable when source content changes during that
academic year. Content changes are represented by `content_hash`, not by
creating a new entity ID.

---

## `record_id`

`record_id` is the stable persisted AskANU record key.

### Course format

```text
courses:course:<ENTITY_ID>
```

Example:

```text
courses:course:COMP1100_2026
```

### Program format

```text
courses:program:<ENTITY_ID>
```

Example:

```text
courses:program:BACCT_2026
```

`record_id` remains stable when the normalized source content changes.
`content_hash` is used to detect those changes.

---

# 7. Course/program code normalization

## Course code

Normalize for deterministic lookup by:

1. removing whitespace,
2. converting to uppercase.

Schema-v1 course-code validation:

```regex
^[A-Z]{4}\d{4}[A-Z]?$
```

Examples:

```text
COMP 1100 -> COMP1100
comp1100  -> COMP1100
BIOL9001P -> BIOL9001P
```

The normalized source-supported value is stored in:

```text
metadata_json["course_code"]
```

---

## Program code

For schema v1:

1. trim surrounding whitespace,
2. convert to uppercase.

Do not introduce a stricter program-code regex until supported by actual ANU
program source evidence.

The normalized source-supported value is stored in:

```text
metadata_json["program_code"]
```

---

# 8. Academic year

For Courses/Programs schema v1, academic year is REQUIRED.

Serialized type:

```text
string
```

Format:

```regex
^\d{4}$
```

Example:

```text
"2026"
```

It is stored explicitly in:

```text
metadata_json["academic_year"]
```

RAG MUST NOT infer academic year from:

- current system date,
- `record_id`,
- `entity_id`,
- or `canonical_url`.

The scraper may derive academic year from approved source evidence during
parsing, including the page's explicit Academic Year control or the approved
page URL when necessary.

After normalization, the explicit `metadata_json["academic_year"]` value is
the cross-repo value consumed by RAG.

---

# 9. Multi-year retrieval rule

RAG storage/repository indexing MUST permit multiple records with the same
course/program code across different academic years.

Do not index only by code.

Conceptually the deterministic key is:

```text
(entity_type, normalized_code, academic_year)
```

Examples:

```text
("course", "COMP1100", "2026")
("course", "COMP1100", "2027")
("program", "BACCT", "2026")
```

Code-only lookup may return:

- zero matching years,
- one matching year,
- multiple matching years.

If multiple years exist and the retrieval/planner layer has not resolved an
academic year, the repository MUST NOT:

- overwrite one record with another,
- silently choose an arbitrary year,
- or infer the current year from system time.

The ambiguity must remain visible to the retrieval/planner layer so it can
resolve or clarify it.

---

# 10. Canonical URL

`canonical_url` is REQUIRED.

The scraper owns canonical-URL extraction.

Priority:

1. use an official canonical URL explicitly supplied by the approved source;
2. otherwise use the approved fetched page URL.

Allowed normalization:

- trim surrounding whitespace,
- remove an unnecessary trailing slash where safe.

Do NOT:

- synthesize an ANU URL inside RAG,
- reconstruct it from course/program code,
- lowercase source URL paths,
- or ask the LLM to produce it.

RAG consumes the stored `canonical_url` directly.

For source/evidence responses, URLs come from stored records, never Gemini.

---

# 11. Content

`content` is REQUIRED and non-empty.

It is the canonical normalized textual representation of the source fields
that are useful for retrieval/answering.

Examples may include:

```text
Title
Course/Program Code
Academic Year
Career
Units
Mode of Delivery
Description/Overview
Prerequisites/Requisites
Incompatibilities
Assumed Knowledge
Offerings
Learning Outcomes
```

Only source-supported values may appear.

Do not add placeholder claims for missing fields.

---

# 12. `content_hash`

`content_hash` is REQUIRED.

Schema-v1 rule:

```text
content_hash =
    SHA-256(content encoded as UTF-8)
    represented as a lowercase hexadecimal string
```

Equivalent Python:

```python
hashlib.sha256(content.encode("utf-8")).hexdigest()
```

Expected format:

```regex
^[0-9a-f]{64}$
```

The scraper is the trusted canonical normalization and `content_hash` writer.
It guarantees that the stored digest is SHA-256 of the canonical persisted
UTF-8 `content`.

RAG:

- accepts it,
- validates the lowercase 64-character hexadecimal format,
- preserves it,
- does not recalculate it during retrieval,
- trusts the scraper's persisted hash/content invariant,
- and does not use an LLM to generate it.

Stale-index result safety assumes that only approved writer paths may persist
records and that each approved writer enforces the canonical content/hash
invariant. Equality proof belongs in Will's scraper tests, not a second RAG
normalizer.

Change-detection behaviour:

```text
no previous record -> NEW
same record_id + different content_hash -> CHANGED
same record_id + same content_hash -> UNCHANGED
```

`record_id` and `entity_id` do not change merely because source content
changes.

---

# 13. Courses metadata (V6 Courses-family addendum)

For a course record, these keys are REQUIRED inside `metadata_json`:

| Key | Type | Nullable |
|---|---|---:|
| `entity_type` | string literal `"course"` | no |
| `course_code` | string | no |
| `academic_year` | four-digit string | no |

Schema-v1 currently recognises these optional course metadata keys:

| Key | Type when present | Nullable |
|---|---|---:|
| `career` | string | yes |
| `units` | string | yes |
| `delivery_mode` | string | yes |
| `description` | string | yes |
| `learning_outcomes` | array of strings | yes |
| `prerequisites` | string | yes |
| `corequisites` | string | yes |
| `incompatibilities` | string | yes |
| `assumed_knowledge` | string | yes |
| `offerings` | array of JSON objects | yes |

Representative structure:

```json
{
  "entity_type": "course",
  "course_code": "COMP1100",
  "academic_year": "2026",
  "career": "UGRD",
  "units": "6",
  "delivery_mode": "In Person",
  "description": null,
  "learning_outcomes": null,
  "prerequisites": null,
  "corequisites": null,
  "incompatibilities": "COMP1130",
  "assumed_knowledge": null,
  "offerings": null
}
```

Optional metadata MUST NOT be fabricated.

If the source does not provide an optional value, use `null` for the documented
schema-v1 key.

In particular:

```text
missing prerequisites != "no prerequisites"
missing offerings != "no offerings"
```

An empty list MUST only mean the source was successfully interpreted as
explicitly containing zero items.

It MUST NOT be used as a substitute for unknown/missing evidence.

Additional source-supported course metadata may be added inside `metadata_json`
in later schema versions without adding arbitrary new top-level fields.

---

# 14. Programs metadata (V6 Courses-family addendum)

For a program record, these keys are REQUIRED inside `metadata_json`:

| Key | Type | Nullable |
|---|---|---:|
| `entity_type` | string literal `"program"` | no |
| `program_code` | string | no |
| `academic_year` | four-digit string | no |

Schema-v1 currently recognises these optional program metadata keys:

| Key | Type when present | Nullable |
|---|---|---:|
| `career` | string | yes |
| `units` | string | yes |
| `duration` | string | yes |
| `delivery_mode` | string | yes |
| `overview` | string | yes |
| `learning_outcomes` | array of strings | yes |
| `program_requirements` | string | yes |
| `admission_requirements` | string | yes |
| `prerequisites` | string | yes |

Representative structure:

```json
{
  "entity_type": "program",
  "program_code": "BACCT",
  "academic_year": "2026",
  "career": null,
  "units": null,
  "duration": null,
  "delivery_mode": null,
  "overview": null,
  "learning_outcomes": null,
  "program_requirements": null,
  "admission_requirements": null,
  "prerequisites": null
}
```

Optional metadata follows the same missing-value rule as course metadata.

Unknown/missing source evidence is represented as `null`, never as an invented
answer.

Source-present `Minors`, `Elective Study`, and `Study Options` sections remain
in deterministic `content` even when they do not have dedicated metadata keys.

## 14.1 Major, Minor and Specialisation metadata

The 363 reviewed 2026 subplans are first-class records in the existing Courses
domain and source. They are not Programs and do not use separate tables or
vector stores.

```text
domain = courses
source_id = courses_programs_and_courses
entity_type = major | minor | specialisation
entity_id = <SUBPLAN_CODE>_<ACADEMIC_YEAR>
record_id = courses:<entity_type>:<entity_id>
```

`SubplanMetadata` contains:

| Key | Type | Nullable |
|---|---|---:|
| `entity_type` | `major`, `minor`, or `specialisation` | no |
| `subplan_code` | trimmed uppercase string | no |
| `academic_year` | four-digit string | no |
| `career` | string | yes |
| `units` | string | yes |
| `subplan_type` | string | yes |
| `overview` | string | yes |
| `learning_outcomes` | array of strings | yes |
| `requirements` | faithful source text | yes |
| `relevant_degrees` | array of strings | yes |
| `other_information` | string | yes |

This key set is exact: Subplan metadata rejects unknown keys in both the model
and the `20260915_0006` database check. Course and Program metadata retain their
previous extension-compatible behavior.

The same code in two different entity types remains distinct because logical
uniqueness is `(entity_type, code, academic_year)`. Requirements stay as
faithful normalized source text; complex rules are not reduced to lossy or
inferred structures.

## 14.2 Courses-family canonical URLs

Metadata codes are trimmed uppercase. The canonical URL path code is exactly
the lowercase metadata code:

```text
https://programsandcourses.anu.edu.au/<year>/<entity_type>/<code.lower()>
```

Only HTTPS on the exact host is accepted, with no credentials, port, query,
fragment, trailing slash, mismatched year/entity/code, or alternate origin.
This rule applies equally to Course, Program, Major, Minor and Specialisation.

---

# 15. Missing/null value policy

Global rule:

```text
No source evidence -> no invented value.
```

For documented optional scalar/list metadata:

```text
missing / unknown -> null
```

Do not convert missing evidence into:

```text
"None"
"N/A"
"Unknown"
"Not applicable"
[]
{}
false
0
```

unless the source explicitly supports that value or the field's semantics
explicitly define it.

Required identity fields must not be silently replaced with placeholders.

If required identity cannot be established, the scraper must reject/flag the
record rather than publish a misleading normalized record.

---

# 16. Datetimes and timezone

Serialized datetimes MUST be timezone-aware ISO-8601 values.

Operational source collection uses:

```text
Australia/Canberra
```

`collected_at` and `last_seen_at` are required.

`effective_from` and `effective_to` remain nullable because many Courses-family
pages do not provide source-supported effective dates. Academic year must never
be converted into invented start/end dates.

---

# 17. Representative normalized course identity

The verified live COMP1100 collection has this identity:

```text
domain        = courses
source_id     = courses_programs_and_courses
entity_id     = COMP1100_2026
record_id     = courses:course:COMP1100_2026
title         = Programming as Problem Solving
academic_year = 2026
course_code   = COMP1100
career        = UGRD
units         = 6
delivery_mode = In Person
```

The canonical URL is the exact official lower-path form:
`https://programsandcourses.anu.edu.au/2026/course/comp1100`.

The exact `content_hash`, timestamps and optional metadata depend on the
normalized record instance and MUST NOT be invented in documentation.

## 17.1 Frozen 2026 Courses-family coverage gates

| Entity family | Frozen count | Independent 99% gate |
|---|---:|---:|
| Courses | 500 | at least 495 |
| Programs | 393 | at least 390 |
| Majors | 109 | at least 108 |
| Minors | 126 | at least 125 |
| Specialisations | 128 | at least 127 |
| **Total** | **1,256** | evaluated per family, not as one pooled gate |

Required source-present field coverage is at least 99%; identity and provenance
correctness is 100%. A field absent on the ANU page is not a failure. A required
published field that is not preserved correctly is a coverage failure. The V6
denominator is limited to the identity, academic/delivery, descriptive,
learning-outcome, academic-rule, offering, and subplan fields documented above.
Workload, fees, prescribed readings and similar optional sections are not added
to that mandatory denominator.

Courses-family `content` is deterministic, source-backed section serialization,
never a model summary or title/code-only placeholder. It retains all
source-present required fields and the specified Program/Subplan sections so
that `content_hash` remains a meaningful indexing-freshness identity.

Revision `20260915_0006` follows `20260915_0005`, expands Courses constraints
and uniqueness to all five entity types, and preserves the historical
`course_program_records` view as Course + Program only using an explicit
entity-type predicate plus the existing structural `OFFSET 0` read-only guard.
Subplans remain readable from `source_records` and enter the shared embedding
pipeline, but never leak into that compatibility view.

---

# 18. Source registry

Source registry fields remain:

```text
source_id
canonical_root
domain
authority_rank
poll_cadence
parser_name
active
notes
```

Rules:

- only approved/active production sources may be collected,
- pending-approval sources remain inactive,
- Rubric remains `PENDING_APPROVAL` / non-production until explicitly approved,
- do not use undocumented/internal Rubric APIs.

---

# 19. Ingestion run

The shared database contains a durable `ingestion_runs` table for bounded scraper
run audit, persisted counts and operational traceability. Cloud Run structured
logs are supplementary; they are not the durable count store. These rows are not
RAG evidence and are never included in retrieval, Gemini context or the public
API.

Ingestion-run fields remain:

```text
run_id
source_id
started_at
completed_at
records_seen
records_added
records_changed
records_unchanged
records_missing
status
error
```

Allowed ingestion-run status values:

```text
RUNNING
SUCCESS
FAILED
SUSPICIOUS_ZERO
```

`records_added` is the persisted `NEW` count. `records_changed` and
`records_unchanged` are the corresponding `CHANGED` and `UNCHANGED` counts.
`records_missing` records bounded missing observations; it is not permission to
delete records. Run failure is represented by `status` plus the nullable `error`
field rather than by adding a second, incompatible count contract.

The table stores no raw scraped payload, prompt, history or credential. Carmen's
RAG repository owns its shared migration; Will's scraper owns inserting and
updating ingestion-run rows.

On fetch/parser failure:

```text
FAILED
preserve last-known-good data
```

On suspicious many-to-zero:

```text
SUSPICIOUS_ZERO
do not wipe current data
```

---

# 20. First DB / migration ownership

For the first Courses/Programs vertical slice:

**Carmen — RAG/backend**

- owns the RAG-side DB model/data-access implementation,
- owns the shared migration/schema for course/program records and ingestion runs,
- owns deterministic course/program read/query behaviour.

**Will — Scraper/data**

- owns normalized record production,
- owns scraper-side record upsert, `content_hash` change detection and
  `NEW`/`CHANGED`/`UNCHANGED` assignment,
- owns record and ingestion-run writes against this shared schema,
- does not independently redefine shared field semantics.

**Qasim — PM/integration/contracts/GCP**

- owns cross-repo schema approval,
- coordinates the scraper -> DB -> RAG integration,
- coordinates Cloud SQL/GCP provisioning,
- reviews shared migration/contract changes,
- ensures affected contract documents remain synchronized.

No shared schema change should be made independently in one repo without
coordinating the affected repo(s).

---

# 21. RAG implementation boundary

The RAG repository MUST NOT copy scraper implementation such as:

```text
HTML parsers
HTTP fetchers
source registry implementation
LocalDataStore
scraper ingestion-run implementation
scraper change-detection implementation
```

RAG owns:

```text
its own validated record model
fixture loader
DB/data-access repository
exact/deterministic retrieval
planner/retrieval behaviour
```

The RAG record model may use strict validation (`extra="forbid"`) against the
schema-v1 top-level fields.

`metadata_json` remains the controlled domain-specific extension object.

---

# 22. Day 2 exact-retrieval expectations

For Courses/Programs exact retrieval:

- normalize course/program code deterministically,
- retrieve using entity type + code + academic year,
- support multiple academic years without collisions,
- do not infer missing year inside the repository,
- preserve the complete normalized record,
- preserve `canonical_url`,
- preserve `content_hash`,
- tolerate null optional metadata,
- return no-evidence behaviour for unknown codes,
- never invent missing course/program facts.

The exact-retrieval layer does not require Gemini or vector search.

---

# 23. Change workflow

Any future change to:

- common field names,
- top-level types,
- top-level nullability,
- ID formats,
- `content_hash` semantics,
- canonical URL semantics,
- academic-year semantics,
- required domain metadata,
- or DB ownership

is a shared contract change.

Such changes must:

1. be recorded in `docs/DECISION_LOG.md`,
2. be synchronized across affected repos,
3. be reviewed before dependent implementations silently diverge.

---

# Day 9 Scholarships shared-persistence candidate (frozen record contract)

This local Day 9 implementation proposes `source_records` as the canonical
writable table for approved source records. The deployed
`course_program_records` table is renamed in place by revision
`20260913_0002`; a `course_program_records` compatibility view continues to
expose only Courses/Programs rows for legacy reads. There is no row copy,
Scholarship-only table, or Scholarship-only top-level column. The table/view
name and live permission behavior remain pre-migration operational gates.

All domains continue to use the same 16 top-level fields defined in section 1.
The only approved source/domain pairs in this migration are:

```text
courses_programs_and_courses + courses
scholarships_anu_finder      + scholarships
```

Courses/Programs keep their existing academic-year, normalized-code,
`entity_id`, `record_id`, and unique identity rules. Those checks become
conditional on `domain = courses`; they do not apply course/year assumptions to
Scholarships.

## Scholarship identity

```text
domain    = scholarships
source_id = scholarships_anu_finder
entity_id = <slug matching ^[a-z0-9]+(?:-[a-z0-9]+)*$>
record_id = scholarships:scholarship:<entity_id>
canonical_url = https://study.anu.edu.au/scholarships/find-scholarship/<entity_id>
```

The canonical URL must be exactly the constant prefix above plus the literal
`entity_id`, with no alternate host/path, query, fragment, trailing slash or
extra segment. Identity comes from that URL path, never the title, year,
deadline, status, or value. The URL remains the top-level `canonical_url`; it
is not duplicated in metadata.

The database validates the frozen slug grammar, compares the full URL to the
constant prefix plus `entity_id`, and compares the final path segment to
`entity_id` using literal equality. Record data is never concatenated into a
regular-expression pattern.

`course_program_records` is a legacy read-compatibility view, not a second
authoritative store or an approved upsert target. Revision `20260914_0003`
recreates it with a semantics-neutral top-level `OFFSET 0`, so PostgreSQL
classifies it as structurally non-updatable. Exact old-RAG, new-RAG and scraper
live-role permissions must still be verified before migration rollout.

## Scholarship metadata_json v1

Scholarship metadata contains exactly these 13 keys:

| Key | Serialized type | Missing value |
|---|---|---|
| `entity_type` | literal `scholarship` | invalid |
| `featured` | boolean | `null` |
| `status` | string | `null` |
| `application_required` | boolean | `null` |
| `study_stage` | array of strings | `[]` |
| `student_type` | array of strings | `[]` |
| `study_level` | array of strings | `[]` |
| `area_of_study` | array of strings | `[]` |
| `value` | string | `null` |
| `selection_basis` | string | `null` |
| `opening_date` | ISO `YYYY-MM-DD` string | `null` |
| `closing_date` | ISO `YYYY-MM-DD` string | `null` |
| `eligibility` | string | `null` |

Only official source-supported facts are stored. A null or empty filter list is
not evidence of the opposite value. RAG does not derive open/closed state from
dates, infer value/deadline, or decide personal eligibility.

Top-level `status` remains the generic record lifecycle state. Scholarship
`metadata_json.status` is the source's public Scholarship status. Opening and
closing dates remain domain metadata. Scholarship top-level `effective_from`
and `effective_to` are frozen as `NULL` and enforced in both model and database.

## Cross-domain index/freshness behavior

The Day 8 lifecycle applies to every `source_records` row:

- `NEW`: set `collected_at` and `last_seen_at`; use `PENDING` with
  `embedding_version = null`.
- `CHANGED`: preserve `collected_at`, update `last_seen_at`; use `PENDING` with
  `embedding_version = null`.
- `UNCHANGED`: preserve `collected_at`, update `last_seen_at`, and preserve the existing index state/version;
  emit no new content-change signal.
- `MISSING` or source failure: preserve the last-known-good row and both
  timestamps; do not delete or request re-embedding.
- `PENDING`/`FAILED`: current stored source facts remain available to
  deterministic relational retrieval, but the persistent semantic path must not
  claim that current content is indexed.
- derived stale indexed state: current DB content remains authoritative; a
  result whose `record_id`/`content_hash` or target version is stale is excluded
  or discarded.
- `INDEXED`: usable only when the successful version represents current content
  and the requested target version.

An explicit model/retrieval-policy version rollout over unchanged content is a
separate case from failed indexing of new content. If that rollout fails while
the prior `INDEXED` row/version still represents the same current
`content_hash`, preserve that prior state as last-known-good. Queries for the
new target version cannot use it because version matching remains mandatory.
Failure persistence must compare the task's starting content hash, index state
and version so a late failure cannot overwrite a concurrent success. For
`NEW`/`CHANGED` or any row without a usable prior index, failure remains
`FAILED` and historical vectors are ineligible.

Revision `20260915_0005` adds the explicit RAG-side indexing primitive and the
shared `source_record_embeddings` table described below. It does not add a
`STALE` column/enum or change scraper ownership. Will continues to own scraper
upserts/change detection; Carmen owns the shared migrations, RAG reads and
index-state meaning; Qasim owns contract approval and live migration/deployment
ordering.

## Frozen bounded-run transaction contract

1. Create the `RUNNING` `ingestion_runs` row in a short transaction.
2. Commit the complete accepted bounded record batch and the matching `SUCCESS`
   status/counts together in one atomic transaction.
3. Any record write or final run update failure rolls back the whole batch.
4. A separate recovery transaction then marks the existing run `FAILED`.
5. For an unknown commit outcome, reconcile by `run_id`, stable identity and
   hash; never issue a blind duplicate write.

A partially committed successful batch is invalid. The writer implementation
remains in the scraper repository.

---

# Jobs normalized contract v1 plus approved V6 requirements v2

Revision `20260914_0004` extends the shared `source_records` table without
adding or changing any of its 16 top-level fields. The approved Jobs identity is:

```text
domain    = jobs
source_id = jobs_anu_search
entity_type = job
entity_id = <digits-only ANU requisition/job ID as a string>
record_id = jobs:job:<entity_id>
metadata_json.job_id = entity_id
```

The public canonical URL is exactly `https://jobs.anu.edu.au/jobs/<slug>` with
one non-empty final slug, no trailing slash, query, fragment, port, alternate
host or extra path component. The slug is not the numeric job identity and RAG
never derives one from the other.

Revision `20260914_0004` introduced the exact 12-key v1 shape. Revision
`20260915_0005` adds one approved nullable key, backfilling existing Jobs rows
with JSON null rather than inferring content. Jobs metadata v2 has exactly these
13 keys:

| Key | Serialized type | Missing value |
|---|---|---|
| `entity_type` | literal `job` | invalid |
| `job_id` | digits-only string equal to `entity_id` | invalid |
| `category` | string | `null` |
| `employment_types` | array of strings | `[]` |
| `location` | string | `null` |
| `classification` | string | `null` |
| `salary` | source wording string | `null` |
| `closing_text` | source wording string | `null` |
| `closing_date` | real ISO `YYYY-MM-DD` Canberra-local date | `null` |
| `closing_at` | timezone-aware ISO-8601 datetime string | `null` |
| `status` | `current`, `closed` or `null` | `null` |
| `summary` | source/listing summary string | `null` |
| `role_requirements` | array of direct-page source strings | `null` |

Unknown metadata keys are invalid. Fixed-term is represented only by stored
`employment_types` wording and never determines currentness. Jobs top-level
`effective_from` and `effective_to` are null. No opening/posting/start date is
part of v1, and ingestion timestamps must not be reinterpreted as one.

RAG includes a Job in Current Jobs only when metadata status is `current` and
`closing_date` is null or on/after the Canberra evaluation date. It excludes
`closed`, null status and past dates. It orders dated records by closing date and
numeric entity ID, followed by undated records by numeric entity ID. This is
deterministic relational retrieval and does not depend on `index_status`, Gemini
or vector search.

`role_requirements` is populated only when the approved public canonical ANU
Jobs page directly publishes usable requirement or selection content. It
preserves source meaning and order. It is never inferred from title,
classification, summary, category, salary or employment type. Missing or
Position-Description-only content is stored as `null`; a requirements question
then returns `insufficient_evidence` with the stored official source. Position
Description collection remains outside the approved source boundary.

---

# V6 Accommodation metadata v1

Identity uses the active scraper-registry source `accommodation_anu_study`,
`domain = accommodation`, slug `entity_id`, and
`record_id = accommodation:residence:<entity_id>`. The canonical URL is exactly
`https://study.anu.edu.au/accommodation/our-residences/<entity_id>` and its slug
must equal `entity_id`.

Metadata contains exactly:

- `entity_type = residence`;
- nullable strings `category`, `location`, `advertised_rate`, `cost_period`,
  `overview`, `accessibility`, `application_text`, `application_url`,
  `eligibility` and `vacancy_status`;
- string arrays `catering_options`, `audiences` and `features`;
- `rooms`, an array of exact objects containing `name`, nullable `rate`,
  `contract`, `inclusions` and `other_fees`; and
- exact `contact` object containing nullable `email`, `phone`, `location` and
  `hours`.

`source_authority` is not metadata. Authority comes from the approved
`source_id`, domain and exact canonical boundary. Residence `location` and
contact `location` are independent source facts. `application_url`, when
present, is an explicitly published HTTPS `*.starrezhousing.com` navigation
destination; RAG never fetches or authenticates to it.

Advertised rates are source wording, not guaranteed prices. `vacancy_status`
is strictly source-backed. Null means no approved evidence about current
vacancy, not available or unavailable, and RAG never derives it from an
application link, room/rate table, dates or any other proxy.

# V6 Support metadata v1

Identity uses the active scraper-registry source
`support_anusa_student_assistance`, `domain = support`, slug `entity_id`, and
`record_id = support:support_service:<entity_id>`. Canonical URLs remain under
the exact boundary
`https://anusa.com.au/student-assistance/<entity_id>/`, with literal slug
equality.

Metadata contains exactly `entity_type = support_service`; nullable strings
`category`, `purpose`, `hours`, `access` and `cost`; string array `audiences`;
exact `contact` object containing nullable `email`, `phone` and `location`;
`topics` containing exact `title`, nullable `description`, and an internal
ANUSA Student Assistance `url`; and `referrals` containing exact `label` and an
explicit external HTTP(S) `url`.

`source_authority` is not metadata. Topics remain nested under their parent
service. Referrals are navigation evidence only: they are not Topics, are not
promoted into source-record entities and are not fetched by this path. Null
hours/access stay unknown; referred-service facts are never inherited. RAG does
not diagnose, invent medical/legal advice, or guarantee service availability,
emergency coverage, response time or hours.

# V6 shared retrieval-unit embeddings

Revision `20260915_0005` enables pgvector and creates one shared table:

```text
source_record_embeddings
  source_record_id        FK -> source_records.record_id ON DELETE CASCADE
  retrieval_unit_id       stable whole/chunk identity
  source_content_hash     source snapshot hash
  retrieval_content_hash  exact retrieval-unit text hash
  embedding_model         provider/model identity
  embedding_version       preprocessing/model rollout identity
  embedding               vector (dimension intentionally not frozen yet)
  created_at              timestamptz
  updated_at              timestamptz
```

The composite primary key is `(source_record_id, retrieval_unit_id,
retrieval_content_hash, embedding_model, embedding_version)`. One source record
may have many retrieval units. Historical hashes and versions are retained
intentionally; V6 defines no garbage-collection policy. Index-time existence
checks therefore treat each unit as a set of stored retrieval hashes rather
than selecting an arbitrary historical row, scoped to the current source
`content_hash`.

Retrieval units are built only from canonical `content`, because `content_hash`
is exactly SHA-256 of that field. Display `title` is not independently embedded,
so a title-only mutation cannot change embedding input without changing the
freshness identity. Scraper canonical content remains responsible for retaining
all source text required for retrieval.

`embedding_version` is the effective combination of provider/model rollout and
retrieval-unit policy (including chunk bounds). A model-stable chunking or
normalization policy change therefore requires a new effective version and an
explicit reindex; old-policy rows cannot satisfy the new query version.

Semantic queries join to `source_records` and accept a row only when source ID,
current source hash, effective model/policy version, embedding model and
`INDEXED` state all match. Vector rows are candidate-ranking data, never
independent factual authority.
