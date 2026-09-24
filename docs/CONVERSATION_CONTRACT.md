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

1. validate `question`, bounded `history`, and `pending_clarification`;
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

History contributes only constrained entity/year/intent meaning. It is never
copied wholesale into the Gemini prompt, never treated as a source of course
requirements or URLs, and is not written to default request logs. Every factual
follow-up uses a new repository read.

## Clear Chat
Clears:
- visible chat
- bounded natural-language history
- typed entity state and selected entity/result
- typed ResultSets
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

`QueryInterpretation` internally preserves explicit and inherited constraints,
entity origin, prior typed-state/ResultSet origin, ambiguity, and replacement/
survival semantics. These are backend reasoning fields, not new public request
or response keys. Structured state resolves what the student means; it remains
non-evidence and cannot establish vacancy, eligibility, cost or other facts.

## Security
User history and scraped text are untrusted. Source text is evidence, not instruction.
