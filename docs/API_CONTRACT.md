# API_CONTRACT.md

Version `v1`.

## POST /api/v1/ask

Request:
```json
{
  "question": "Does it have prerequisites?",
  "history": [
    {"turn_id":"t1","role":"user","content":"Tell me about COMP1110"},
    {"turn_id":"t2","role":"assistant","content":"..."}
  ],
  "conversation_state":{
    "schema_version":1,
    "turn_index":3,
    "recent_entities":[],
    "focus":null,
    "student_facts":[],
    "constraints":{"items":[]},
    "result_sets":[],
    "selected_result":null,
    "pending_clarification":null
  }
}
```

`conversation_state` is optional for backwards compatibility. If omitted, RAG
initialises an empty schema-version-1 state. RAG validates this untrusted,
client-carried structure, applies bounded deterministic transitions, and returns
the authoritative updated structure on every `/api/v1/ask` response. The App
stores it only for the current chat and sends it back unchanged on the next
turn. The App does not semantically interpret it.

History and state have different roles: `history` is bounded recent language
context; `conversation_state` is bounded structured semantic context. Neither
is institutional factual evidence. There is no server session ID/store,
persistent profile, account memory, Redis/cache or sticky-session requirement.

Initial V3 limits:
- question max 2,000 characters
- history max 10 prior turns
- output target about 800 model tokens
- backend timeout target about 30 seconds

### Status enum — frozen
- `ok`
- `partial`
- `needs_clarification`
- `insufficient_evidence`
- `off_topic`
- `error`

No Relief Mate confidence labels.

### HTTP error behaviour — frozen

| Failure | HTTP status |
|---|---|
| Malformed JSON | 400 |
| Request validation failure other than oversized input | 400 |
| Oversized input, including question/history exceeding the documented limits | 413 |
| Rate limit exceeded | 429 |
| DB, model or internal dependency failure | Controlled 5xx |

Error responses use controlled JSON with the existing `error` status and response envelope:

```json
{
  "status":"error",
  "answer":"The request could not be completed.",
  "items":[],
  "sources":[],
  "clarification":null,
  "request_id":"req_...",
  "conversation_state":{"schema_version":1,"turn_index":4,"recent_entities":[],"focus":null,"student_facts":[],"constraints":{"items":[]},"result_sets":[],"selected_result":null,"pending_clarification":null}
}
```

The additive `conversation_state` response field is present for every Ask
status. Existing response status, answer, item, source, clarification and
request-ID semantics are unchanged.

The answer may provide a safe, user-facing explanation. Never return stack traces, credentials, secrets, prompts or internal dependency diagnostics. The exact 5xx code depends on the failure; this contract does not prescribe a separate code for each dependency.

### Response
```json
{
  "status":"ok",
  "answer":"...",
  "items":[],
  "sources":[
    {
      "record_id":"course:COMP1110:2026",
      "source_id":"programs-and-courses",
      "title":"...",
      "url":"https://...",
      "domain":"courses"
    }
  ],
  "clarification":null,
  "request_id":"req_...",
  "conversation_state":{"schema_version":1,"turn_index":1,"recent_entities":[],"focus":null,"student_facts":[],"constraints":{"items":[]},"result_sets":[],"selected_result":null,"pending_clarification":null}
}
```

### Source object identifiers

Every source object contains `record_id`, `source_id`, `title`, `url`, and `domain`.

- `record_id` identifies the retrieved evidence record, for example `course:COMP1110:2026`.
- `source_id` identifies the authoritative source in the source registry. `programs-and-courses` above is illustrative; use the actual stored registry identifier.
- `title` and `domain` come from the stored record; `url` comes programmatically from its stored `canonical_url`, never Gemini.

### Clarification
```json
{
  "status":"needs_clarification",
  "answer":"Do you mean COMP1110 or COMP1600?",
  "items":[],
  "sources":[],
  "clarification":{
    "id":"clar-42",
    "type":"entity_selection",
    "options":[
      {"id":"course:COMP1110","label":"COMP1110"},
      {"id":"course:COMP1600","label":"COMP1600"}
    ],
    "allow_multiple":true
  },
  "request_id":"req_...",
  "conversation_state":{"schema_version":1,"turn_index":1,"recent_entities":[],"focus":null,"student_facts":[],"constraints":{"items":[]},"result_sets":[],"selected_result":null,"pending_clarification":{"id":"clar-42","type":"entity_selection","options":[{"id":"course:COMP1110","label":"COMP1110"},{"id":"course:COMP1600","label":"COMP1600"}],"allow_multiple":true,"original_intent":{"name":"legacy_clarification","operation":"select_option","required_slots":["selection"],"resolved_slots":[]},"resolved_entities":[],"resolved_slots":[],"missing_slots":["selection"],"constraints":{"items":[]},"created_turn":1}}
}
```

### Structured conversation state

Schema version 1 is defined by the RAG models and the Day 1 shared-contract
handoff in `docs/v7/DAY_01_SHARED_CONTRACTS.md`. Unknown fields, malformed
values, incompatible versions, duplicate semantic identities, dangling focus
references and collection-limit violations return the controlled HTTP 400
error envelope. A malformed state is never partially trusted or used as
evidence.

The implemented Day 1 schema-version-1 top-level fields submitted for PM review
are:

| Field | Type | Bound |
|---|---|---:|
| `schema_version` | literal integer `1` | required after defaulting |
| `turn_index` | non-negative integer | at most 1,000,000 |
| `recent_entities` | typed entity array | 12 |
| `focus` | typed semantic focus or null | one |
| `student_facts` | explicitly user-stated fact array | 12 |
| `constraints.items` | typed scoped constraint array | 16 |
| `result_sets` | typed ResultSet array | 6 |
| `selected_result` | stable ResultSet selection or null | one |
| `pending_clarification` | resumable clarification or null | one |

Each ResultSet contains at most 20 ordered canonical identities. Clarification
options contain at most 20 items. State strings and scalar values are bounded;
arbitrary nested JSON is not accepted.

Day 2 replaces the former single temporal semantic value with independent
`date_window` and `time_of_day_window` constraint types. This changes neither
the schema-version-1 envelope nor its collection bounds. It allows a scoped
date and time-of-day rule to coexist and be replaced independently. Existing
schema-version-1 state carrying `temporal_window` remains accepted and
round-trippable for wire compatibility, but the Day 2 interpreter never emits
that legacy combined value.

### Pending clarification in the next request

`conversation_state.pending_clarification` is either `null` or a bounded
resumable clarification. The legacy fields remain `id`, `type`, `options`, and
`allow_multiple`; each option contains `id` and `label`. Schema v1 additionally
supports `original_intent`, already resolved entities/slots, missing slots,
applicable constraints and creation turn. Old pending-only callers remain
accepted and are upgraded into the versioned response state.

```json
{
  "conversation_state":{
    "pending_clarification":{
      "id":"clar-42",
      "type":"entity_selection",
      "options":[
        {"id":"course:COMP1110","label":"COMP1110"},
        {"id":"course:COMP1600","label":"COMP1600"}
      ],
      "allow_multiple":true
    }
  }
}
```

The client stores the complete authoritative `conversation_state` response and
returns it unchanged on the next request, alongside the user's answer in
`question` and bounded history. RAG, not the client, copies public clarification
details into `pending_clarification` and owns all subsequent state transitions.
Preserve option order for `first`/`second`; `allow_multiple` supports `both`.
Clear pending clarification when resolved, corrected, switched to a new topic,
or cleared with Clear Chat. This is untrusted current-session context, not
factual evidence.

## GET /api/v1/events/upcoming?limit=5
Deterministic; `Australia/Canberra`; upcoming only; ascending start time; default 5.

Minimal successful response (HTTP 200):

```json
{
  "status":"ok",
  "items":[
    {
      "record_id":"<stored event record ID>",
      "source_id":"<stored source-registry ID>",
      "title":"<stored event title>",
      "start_at":"<stored event start time>",
      "end_at":"<stored event end time>",
      "venue":"<stored event venue>",
      "organiser":"<stored event organiser>",
      "status":"<stored source-backed status or null>",
      "url":"<stored canonical URL>",
      "domain":"events"
    }
  ],
  "request_id":"req_..."
}
```

`items` is an ordered array of event objects containing the fields shown above, with at most the requested limit. `record_id` identifies the evidence record and `source_id` identifies its source registry entry. This dedicated endpoint reads `events_anu_official` only. Include upcoming events only: when a source-backed `end_at` is known, the Event remains current until that instant; otherwise currentness uses `start_at`. Exclude past Events and order by ascending `start_at`, then stable `record_id`, in `Australia/Canberra`. Missing optional values remain JSON `null`. No qualifying records returns `status: "ok"` with `items: []`. Events conversation retrieval may use both `events_anu_official` and `rubric_unified_search` while preserving each source record's provenance.

## GET /api/v1/jobs/current?limit=5
Deterministic; current only; nearest known closing date first; undated current
roles after dated roles. The default is 5 and the accepted range is 1–20.

Minimal successful response (HTTP 200):

```json
{
  "status":"ok",
  "items":[
    {
      "record_id":"<stored job record ID>",
      "source_id":"<stored source-registry ID>",
      "job_id":"<stored numeric requisition ID>",
      "title":"<stored job title>",
      "employment_types":["<stored employment type>"],
      "location":"<stored job location>",
      "classification":"<stored classification>",
      "salary":"<stored source salary wording>",
      "closing_text":"<stored closing wording>",
      "closing_date":"<stored Canberra-local YYYY-MM-DD date>",
      "closing_at":"<stored closing time>",
      "status":"current",
      "url":"<stored canonical URL>",
      "domain":"jobs"
    }
  ],
  "request_id":"req_..."
}
```

`items` is an ordered array of job objects containing exactly the fields shown
above, with at most the requested limit. Nullable stored scalar fields remain
JSON `null`; missing `employment_types` is `[]`. Include only records whose
normalized Jobs status is `current` and whose `closing_date` is null or is on/
after the current `Australia/Canberra` calendar date. `closed`, null status and
past closing dates are excluded. Order dated roles by `closing_date` ascending
then numeric `job_id` ascending; order undated roles afterward by numeric
`job_id`. `closing_at` is returned only when stored and does not determine
currentness. No qualifying records returns `status: "ok"` with `items: []`.

Both list endpoints use the controlled error behaviour above. URLs come programmatically from stored canonical URLs, never Gemini. Angle-bracket values are illustrative placeholders, not field type or nullability declarations; domain field types/nullability remain scheduled Day 2 data-schema work.

## GET /health
Must not expose secrets, prompts, credentials or stack traces.

## Provenance invariant
Source URLs come programmatically from retrieved stored records. The model must never invent source URLs.
