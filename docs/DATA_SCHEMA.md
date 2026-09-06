# DATA_SCHEMA.md

Shared Scraper -> storage/DB -> RAG normalized record contract.

## Schema version

**Courses/Programs schema v1**

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
| `embedding_version` | string | yes | Embedding version if/when embedding has occurred |
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

The scraper owns calculation of `content_hash`.

RAG:

- accepts it,
- preserves it,
- does not recalculate it during retrieval,
- and does not use an LLM to generate it.

Change-detection behaviour:

```text
no previous record -> NEW
same record_id + different content_hash -> CHANGED
same record_id + same content_hash -> UNCHANGED
```

`record_id` and `entity_id` do not change merely because source content
changes.

---

# 13. Courses metadata v1

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
| `prerequisites` | string | yes |
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
  "prerequisites": null,
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

# 14. Programs metadata v1

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
| `learning_outcomes` | array of strings | yes |

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
  "learning_outcomes": null
}
```

Optional metadata follows the same missing-value rule as course metadata.

Unknown/missing source evidence is represented as `null`, never as an invented
answer.

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

`effective_from` and `effective_to` remain nullable because many course/program
pages do not provide source-supported effective dates.

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

The canonical URL is the URL stored from the official ANU Programs & Courses
source.

The exact `content_hash`, timestamps and optional metadata depend on the
normalized record instance and MUST NOT be invented in documentation.

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
- owns the first migration code required by RAG retrieval,
- owns deterministic course/program read/query behaviour.

**Will — Scraper/data**

- owns normalized record production,
- owns scraper-side write/handoff integration against this contract,
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