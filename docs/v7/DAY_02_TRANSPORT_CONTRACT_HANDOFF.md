# V7 Day 2 App-to-RAG transport-contract handoff

Status: **READY FOR PM REVIEW**. This correction freezes only the shared Ask
transport-size boundary. It does not change accepted Day 2 conversation
semantics or start Day 3 retrieval work.

## Git scope

- Branch: `carmen/v7-day2-transport-contract`
- Base and starting `origin/main`: `5e80b47833f99877a8632ea54910a673a04e8d2d`
- PR: intentionally not opened pending Carmen review

## Frozen limits

| Component | Limit |
|---|---:|
| Serialized `conversation_state` UTF-8 | 131,072 bytes (128 KiB) |
| Serialized bounded history UTF-8 | 98,304 bytes (96 KiB) |
| Question | 2,000 Unicode code points and 8,192 UTF-8 bytes |
| Complete `/api/v1/ask` request body | 262,144 raw bytes (256 KiB) |
| `HistoryTurn.turn_id` | 128 characters |
| `HistoryTurn.content` | 10,000 characters |
| History turns | existing maximum of 10 |

Binary units use `1 KiB = 1,024 bytes`. History and state are measured as
deterministic compact JSON encoded in UTF-8: `ensure_ascii=False`, non-finite
numbers disallowed, `,`/`:` separators, and sorted object keys. The complete
request is measured as raw HTTP bytes before JSON parsing. The App proxy target
is the same 256 KiB complete-body limit.

The 8 KiB question guard is intentionally redundant under the current
2,000-code-point cap. Valid UTF-8 code points require at most four bytes, so a
question that satisfies the character cap is necessarily at most 8,000 bytes.
The separate production validator is defense-in-depth if the character cap is
changed later; no impossible API-level test is claimed.

## Enforcement

- `AskRequest` preserves the 2,000-character and ten-turn limits, adds direct
  question-byte checks, validates history/state serialized bytes before and
  after typed parsing, and bounds both HistoryTurn strings.
- The existing request middleware rejects an Ask body above 256 KiB with the
  controlled 413 envelope before FastAPI parses it.
- Component size errors use the same controlled 413 path. Other malformed or
  semantically invalid request shapes retain controlled 400 behavior.
- The authoritative response path checks state size after the transition and
  before attaching it to the response. Response models also validate the state
  limit. A theoretically oversized internal state fails deterministically; it
  is never emitted or truncated.
- Controlled error handling substitutes an empty schema-v1 state if an
  oversized internal state caused the failure, keeping the error response
  round-trippable.

No input, history item, state field or complete body is truncated.

## Verification

- Focused transport limits: 12 passed, 3 existing dependency warnings.
- Exact state boundary: 131,072 bytes accepted; 131,073 bytes rejected, with
  the API path returning controlled 413.
- Exact history boundary: 98,304 bytes accepted; 98,305 bytes rejected with
  controlled 413.
- Question: 2,000 two-byte characters accepted; 2,001 rejected with controlled
  413. The focused byte-validator test rejects 2,049 four-byte code points
  (8,196 UTF-8 bytes).
- Complete request: 262,144 raw bytes accepted; 262,145 raw bytes returns
  controlled 413.
- Returned authoritative state remains within 128 KiB and is accepted on the
  next stateless request.
- Focused Day 2: 27 passed, 3 existing dependency warnings.
- Frozen Day 1: 36 passed, 3 existing dependency warnings.
- Existing ask/history/routing and six-domain behaviour: 268 passed, 3 existing
  dependency warnings.
- Explicit 10-turn and 20-turn journeys: 2 passed, 3 existing dependency
  warnings.
- Full suite: 896 passed, 89 skipped, 3 existing dependency warnings. The
  skips are 88 PostgreSQL integration tests because
  `ASKANU_TEST_DATABASE_URL` is not configured and one existing Windows
  symlink-permission skip. This correction changes no database contract.
- `pip check`: PASS (`No broken requirements found`).
- `compileall` for `src`, `tests`, and `migrations`: PASS.
- Alembic: exactly one unchanged head, `20260921_0010`.
- `git diff --check`: PASS; Git may emit only existing LF/CRLF conversion
  notices, not whitespace errors.

## Scope and safety

- Client-carried/stateless architecture changed: **NO**
- Conversation semantics changed: **NO**
- New functionality outside transport validation: **NO**
- Day 3 retrieval work: **NO**
- BM25/FTS/embedding/framework change: **NO**
- Migration or database write: **NO**
- Deployment or indexing: **NO**
- Scraper/source change: **NO**
- Live Rubric call: **NO**

Day 2 transport contract: **READY FOR PM REVIEW**. Day 3 remains **HOLD**.
Carmen-owned blockers: none identified.
