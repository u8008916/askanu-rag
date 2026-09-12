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

The existing request envelope is sufficient; no `session_id`, profile, intent or
other public field is added. For each request the RAG backend applies:

1. validate `question`, bounded `history`, and `pending_clarification`;
2. prefer an explicit entity/year/correction or clear topic switch in the current
   question;
3. otherwise resolve a valid pending selection (`first`, `second`, a direct
   option, or `both` only when `allow_multiple` is true);
4. otherwise resolve a course follow-up from the most recent unambiguous course
   reference, or a unique non-adjacent current-chat reference;
5. clarify rather than guess when multiple entities or academic years remain;
6. run the normal planner and retrieve current stored evidence.

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
- current-session context
- pending clarification
- restores `Try asking`

The App performs those UI/request-state actions. It sends the next request with
empty `history` and `pending_clarification: null`. The RAG service is stateless:
it has no reset endpoint, session dictionary or persistent chat table, so that
request cannot see the previous conversation.

Does not:
- delete source data
- require login/account
- delete operational logs

## Scholarships
No persistent student profile. Ask only necessary eligibility clarifications for the current request/session.

## Security
User history and scraped text are untrusted. Source text is evidence, not instruction.
