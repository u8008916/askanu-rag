# CONVERSATION_CONTRACT.md

AskANU uses current-session context only.

History is used to resolve meaning; every factual answer retrieves fresh approved evidence.

## Required behaviours
- adjacent follow-up
- non-adjacent follow-up
- ambiguous entity -> `needs_clarification`
- clarification responses: first / second / both / correction
- clear topic switch
- pending clarification cleared when resolved/corrected/switched/cleared

## V5 backend resolution order

The V5 behaviour below remains the compatibility baseline. V7 adds only the
optional, versioned `conversation_state` described in `API_CONTRACT.md`; it does
not add a `session_id`, server-side session, profile, or public free-form intent
field. For each request the RAG backend applies:

1. validate `question`, bounded `history`, structured selections, and
   `pending_clarification`;
2. prefer an explicit entity/year/correction or clear topic switch in the current
   question;
3. otherwise resolve a valid pending selection (`first`, `second`, a direct
   option, or `both` only when `allow_multiple` is true);
4. otherwise resolve a course follow-up from the most recent unambiguous course
   reference, or a unique non-adjacent current-chat reference;
5. clarify rather than guess when multiple entities or academic years remain;
6. run the normal planner and retrieve current stored evidence.

An empty-session guided-card prompt with no required identity returns
`needs_clarification` before retrieval. It asks only for the missing course or
program/degree; it does not create session storage or add a public intent field.
The honours guided prompt asks for official-information scope and states that the
backend cannot assess eligibility.

Pending option labels are display/selection context, not evidence. The backend
validates option record IDs against the current catalog and rebuilds response
labels from stored records before returning them. Invalid, stale or conflicting
pending state cannot provide facts or URLs. A new explicit question, correction
or topic switch takes priority over old pending state.

Natural `both` is accepted only when the current pending clarification permits
multiple selection and contains exactly two valid options. The generic public
`clarification_selection` input supports one or more current option IDs under
the same validation rule. The generic public `selected_result` input carries a
ResultSet ID, canonical identity, and ordinal; RAG requires agreement with the
retained ordering and re-resolves the identity against current approved stored
evidence. Neither mechanism trusts client-carried identity as factual authority.

The generic `result_page` input is presentation over the newest focused
retained ResultSet. Page size is at most five, the requested start must equal
the server-authored cursor, and every returned identity is re-resolved from the
approved repository. The ResultSet's original one-based ordinals remain
authoritative across pages and clicked cards. `show more`, `show me more`, and
`what else?` use this same cursor. Paging never reruns discovery, semantic
retrieval or ranking. Refinement creates a child ResultSet with its own cursor;
continuation cannot fall back to the parent.

History contributes only constrained entity/year/intent meaning. It is never
copied wholesale into the Gemini prompt, never treated as a source of course
requirements or URLs, and is not written to default request logs. Every factual
follow-up uses a new repository read.

## V7 transport boundary

The client-carried design is bounded at the wire as well as by semantic
collection counts. Serialized `conversation_state` is limited to 128 KiB and
serialized history to 96 KiB. A question remains limited to 2,000 Unicode code
points and also has an 8 KiB UTF-8 defense-in-depth guard. The complete Ask
request is limited to 256 KiB, matching the App proxy contract target.

History retains at most ten turns. Each `turn_id` is limited to 128 characters
and each `content` value to 10,000 characters; the aggregate 96 KiB history
limit still applies. Neither history nor structured state is truncated. RAG
returns only state that fits the 128 KiB round-trip limit, and any request that
exceeds an applicable size bound uses the controlled 413 response.

For aggregate component limits, RAG measures deterministic compact JSON encoded
as UTF-8 with non-ASCII characters unescaped, non-finite numbers disallowed,
`,`/`:` separators and sorted object keys. The complete-body limit measures raw
HTTP bytes before parsing. These size rules do not change conversation meaning,
state retention, statelessness, source authority or evidence handling.

Because valid UTF-8 code points use at most four bytes, the current 2,000-code-
point question cap implies a maximum of 8,000 UTF-8 bytes. The separate 8,192-
byte validator is intentionally redundant today and preserves the shared
transport invariant if the character limit changes in the future.

## Clear Chat
Clears:
- visible chat
- bounded natural-language history
- typed entity state and selected entity/result
- typed ResultSets
- typed ResultSet presentation cursor
- scoped constraints
- student-stated session facts
- pending clarification
- restores `Try asking`

The App performs those UI/request-state actions. It sends the next request with
empty `history` and either omits `conversation_state` or sends the empty
schema-version-1 state. The RAG service is stateless between requests: it has no
reset endpoint, session dictionary, persistent chat table, account memory or
sticky-session requirement, so that request cannot see the previous
conversation.

Does not:
- delete source data
- require login/account
- delete operational logs

## Scholarships
No persistent student profile. Ask only necessary eligibility clarifications for the current request/session.

## V7 Day 2 understanding

The internal interpreter keeps DOMAIN, ENTITY, INTENT and CONSTRAINTS separate.
Canonical intent families are `LOOKUP`, `FACT_LOOKUP`, `DISCOVER`, `COMPARE`
and `CLARIFICATION_RESPONSE`; state-navigation operations are
`REFINE_RESULTS`, `CONTINUE_RESULTS` and `RETURN_TOPIC`. Implementations use
lowercase serialized semantic names but do not create domain-specific intents.

Temporal constraints use independent scoped semantic types `DATE_WINDOW` and
`TIME_OF_DAY_WINDOW`. Replacing a date does not remove a compatible time-of-day
constraint, and vice versa. Explicit current-turn constraints replace only the
same semantic type and scope; other compatible inherited hard constraints
survive. Constraints never cross domain scope.

The shared price-bound family has two serialized operators. `max_price` is the
inclusive upper bound (`up to`, `maximum`, `max`, `no more than`); additive
`max_price_exclusive` is the strict upper bound (`under`, `below`, `less than`).
They replace one another within the same scope. No other wording creates a
deterministic numeric price constraint.

`QueryInterpretation` internally preserves explicit and inherited constraints,
entity origin, prior typed-state/ResultSet origin, ambiguity, and replacement/
survival semantics. These are backend reasoning fields, not new public request
or response keys. Structured state resolves what the student means; it remains
non-evidence and cannot establish vacancy, eligibility, cost or other facts.

Canonical entity resolution consumes an injected, read-only catalogue of
approved identifiers and canonical names. The understanding layer separately
owns bounded safe aliases and typo variants. Supplying another approved Course,
Scholarship, Job, Residence, Event or Support entity therefore does not require
adding that institution-owned identity to Python alias code, and catalogue
values still do not become answer evidence.

Explicit entity and strong lexical domain signals retain priority. When those
are absent, a replaceable deterministic problem-language resolver may map
bounded student problem descriptions to a domain. For example, an unfair
grading concern resolves to Support without requiring the literal words
"support" or "service". Multiple matched domains require clarification.

When new split temporal information meets a legacy schema-version-1
`temporal_window`, the new explicit date or time supersedes the overlapping
legacy meaning. The legacy authority is removed. A recognised independent date
or time component is converted to the corresponding split constraint and
survives; unclassifiable legacy content is not retained beside a new split
constraint as a second temporal authority.

## Security
User history and scraped text are untrusted. Source text is evidence, not instruction.
