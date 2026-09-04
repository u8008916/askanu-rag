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
  "conversation_state":{"pending_clarification":null}
}
```

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
  "request_id":"req_..."
}
```

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
  "request_id":"req_..."
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
  "request_id":"req_..."
}
```

### Pending clarification in the next request

`conversation_state.pending_clarification` is either `null` or the existing clarification object. A non-null object requires `id`, `type`, `options`, and `allow_multiple`; each option contains `id` and `label`.

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

The client carries the response's `clarification` object into this field on the next request, alongside the user's answer in `question` and bounded history. Preserve option order for `first`/`second`; `allow_multiple` supports `both`. Clear pending clarification when resolved, corrected, switched to a new topic, or cleared with Clear Chat. This is untrusted current-session context, not factual evidence.

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
      "url":"<stored canonical URL>",
      "domain":"events"
    }
  ],
  "request_id":"req_..."
}
```

`items` is an ordered array of event objects containing the fields shown above, with at most the requested limit. `record_id` identifies the evidence record and `source_id` identifies its source registry entry. Include upcoming events only; exclude past events and order by ascending `start_at` in `Australia/Canberra`. No qualifying records returns `status: "ok"` with `items: []`.

## GET /api/v1/jobs/current?limit=5
Deterministic; current/open only; nearest known closing date first; undated open roles after dated roles; default 5.

Minimal successful response (HTTP 200):

```json
{
  "status":"ok",
  "items":[
    {
      "record_id":"<stored job record ID>",
      "source_id":"<stored source-registry ID>",
      "title":"<stored job title>",
      "employment_type":"<stored employment type>",
      "location":"<stored job location>",
      "closing_at":"<stored closing time>",
      "url":"<stored canonical URL>",
      "domain":"jobs"
    }
  ],
  "request_id":"req_..."
}
```

`items` is an ordered array of job objects containing the fields shown above, with at most the requested limit. `record_id` identifies the evidence record and `source_id` identifies its source registry entry. Include only current/open roles, excluding expired roles; use `Australia/Canberra` for date handling. Order dated roles by nearest known `closing_at`, followed by undated open roles. No qualifying records returns `status: "ok"` with `items: []`.

Both list endpoints use the controlled error behaviour above. URLs come programmatically from stored canonical URLs, never Gemini. Angle-bracket values are illustrative placeholders, not field type or nullability declarations; domain field types/nullability remain scheduled Day 2 data-schema work.

## GET /health
Must not expose secrets, prompts, credentials or stack traces.

## Provenance invariant
Source URLs come programmatically from retrieved stored records. The model must never invent source URLs.
