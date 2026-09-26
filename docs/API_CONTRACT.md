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
  },
  "selected_result":null,
  "clarification_selection":null
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

`selected_result` is an optional generic clicked-result input containing
`result_set_id`, `canonical_id`, and one-based `ordinal`. All three values must
agree with a retained ResultSet and RAG re-resolves the identity against current
approved repository evidence before use. `clarification_selection` is an
optional generic structured response containing the current `clarification_id`
and one or more `option_ids`. IDs must belong to the current pending option set;
multiple IDs additionally require `allow_multiple: true`. Both inputs are
untrusted context and cannot supply institutional facts, URLs, or arbitrary
record identities.

Frozen request transport limits:

- question max 2,000 Unicode characters/code points and max 8,192 UTF-8 bytes;
- history max 10 prior turns and max 98,304 serialized UTF-8 bytes;
- each `HistoryTurn.turn_id` max 128 characters;
- each `HistoryTurn.content` max 10,000 characters;
- `conversation_state` max 131,072 serialized UTF-8 bytes; and
- complete `/api/v1/ask` request body max 262,144 bytes as received.

Binary units are used (`1 KiB = 1,024 bytes`). Component serialization size
for `history` and `conversation_state` is measured using compact JSON with
UTF-8, `ensure_ascii=False`, no non-finite numbers, separators `,` and `:`, and
lexicographically sorted object keys. Complete-body size is the raw HTTP body
byte count before JSON parsing. The App proxy shares the 262,144-byte complete
request target so every production-valid Ask request can traverse App to RAG.

No over-limit component or body is truncated. It is rejected through the
controlled HTTP 413 path. RAG also refuses to emit an authoritative
`conversation_state` above 131,072 bytes, so every returned state remains
eligible for the next client-carried request.

The 8 KiB question byte guard is intentionally defense-in-depth under the
current character cap. A valid Unicode code point uses at most four UTF-8
bytes, so 2,000 code points can use at most 8,000 bytes and therefore cannot
exceed 8,192 bytes. The separate byte validator keeps the transport contract
stable if the character cap changes later; it does not imply an impossible
case where a question is both at most 2,000 code points and above 8,192 bytes.

Other initial V3 operational limits:

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
| Oversized input, including any documented component or complete-body limit | 413 |
| Rate limit exceeded | 429 |
| DB, model or internal dependency failure | Controlled 5xx |

Error responses use controlled JSON with the existing `error` status and response envelope:

```json
{
  "status":"error",
  "answer":"The request could not be completed.",
  "items":[],
  "answer_state":null,
  "actions":[],
  "sources":[],
  "clarification":null,
  "request_id":"req_...",
  "conversation_state":{"schema_version":1,"turn_index":4,"recent_entities":[],"focus":null,"student_facts":[],"constraints":{"items":[]},"result_sets":[],"selected_result":null,"pending_clarification":null}
}
```

The additive `conversation_state`, `answer_state`, and `actions` response fields
are present for every Ask status. `answer_state` is null when the route does not
produce a shared evidence state; otherwise it is `CONFIRMED`, `DERIVED`,
`PARTIAL`, or `UNKNOWN`. `actions` contains only validated backend projections,
never links parsed from generated prose, history, or user input.

The answer may provide a safe, user-facing explanation. Never return stack traces, credentials, secrets, prompts or internal dependency diagnostics. The exact 5xx code depends on the failure; this contract does not prescribe a separate code for each dependency.

### Response
```json
{
  "status":"ok",
  "answer":"...",
  "items":[],
  "answer_state":null,
  "actions":[],
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

Accommodation and later verticals reuse `items` for shared structured results.
A result item has `type: "result"`, stored provenance (`record_id`, `source_id`,
`url`, `domain`), stable `canonical_id`, title, optional ResultSet identity and
ordinal, and a `fields` object containing only source-backed display values. A
backend-authored comparison uses `type: "comparison"`, ordered record
identities, and named fields whose per-record values explicitly state
`published` or `not_published`. The App does not reconstruct comparisons from
answer prose or compare cards itself.

A structured action currently uses this reusable shape:

```json
{
  "type":"application",
  "label":"Apply now",
  "url":"https://anu.starrezhousing.com/StarRezPortalX",
  "record_id":"accommodation:residence:example-hall",
  "source_id":"accommodation_anu_study"
}
```

Only a stored, model-validated approved `application_url` may populate this
action.

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
  "answer_state":null,
  "actions":[],
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
that legacy combined value. On the first explicit split-temporal refinement,
the overlapping legacy meaning is superseded and the legacy entry is removed.
Any recognised independent date or time component is preserved as its split
equivalent, so the returned state has one deterministic authority per temporal
dimension.

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

The equivalent structured multi-selection request is:

```json
{
  "question":"Use those options",
  "history":[],
  "conversation_state":{"pending_clarification":{"id":"clar-42","type":"entity_selection","options":[{"id":"record-a","label":"A"},{"id":"record-b","label":"B"}],"allow_multiple":true}},
  "clarification_selection":{"clarification_id":"clar-42","option_ids":["record-a","record-b"]}
}
```

Every selected ID is checked against both the pending options and current
approved repository evidence. Foreign or stale values cannot produce facts.

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
