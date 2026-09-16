# V6 Day 12 Accommodation and Support RAG handoff

**Status:** local implementation complete; production and shared-environment
gates remain closed.

## Review coordinates

- RAG branch: `carmen/day12-accommodation-support-rag`
- RAG base: `fba4fe6b61b287309479a70fd50b86e1d680c5cd`
- scraper evidence ref (read-only):
  `refs/remotes/origin/will/v6-day12-accommodation-support`
- scraper evidence SHA: `fb91311a988dafe3b6af81e1df60d34a2ec042f2`
- migration head: `20260916_0008`

The scraper worktree was not changed. No commit or push was made in either
repository.

## Contract result

The old RAG contract and Will's PR #26 proposal had a material shared-contract
mismatch. Qasim's frozen direction is now implemented exactly:

- Accommodation uses `residence`,
  `accommodation:residence:<entity_id>`, and the exact ANU residence URL.
- Support uses `support_service`,
  `support:support_service:<entity_id>`, and the exact trailing-slash ANUSA
  category URL.
- `source_authority` is absent from both metadata objects.
- Accommodation and Support use their approved nested room/contact/topic/referral
  shapes with strict extra-field rejection.
- Accommodation application URLs are approved HTTPS StarRez URLs; Support topic
  URLs remain inside ANUSA Student Assistance and referral URLs are external.
- Vacancy is source-backed only. Null remains unknown and never inherits meaning
  from an application link.

The detailed historical diff and final decisions are in
`V6_DAY12_ACCOMMODATION_SUPPORT_CONTRACT_REVIEW.md`.

## Implemented RAG scope

1. Strict Pydantic records and exact identity/canonical-URL validation.
2. Append-only migration `20260916_0008` with a read-only, fail-closed existing
   row preflight. It performs no data rewrite or automatic lossy conversion.
3. Exact residence/service lookup, ambiguity clarification, comparisons, nested
   room facts, advertised rates, application/contact/eligibility, topic and
   referral routing, and explicit missing-evidence behavior.
4. High-stakes fail-closed answers for vacancy, diagnosis, emergency coverage,
   response time, 24/7 and professional availability.
5. Current-session follow-up resolution using the user's prior entity reference
   plus a fresh repository read. Explicit topic switches win; Clear/New Chat has
   no persisted entity state.
6. Updated schema, decision, deployment and hybrid-retrieval documentation.

Events, Rubric, production migration, Cloud SQL, deployment, scraper changes and
live StarRez fetching are outside this branch.

## Measured evidence

| Suite | Result |
|---|---:|
| Accommodation capability matrix | 33/33 |
| Support capability matrix | 26/26 |
| Accommodation P0 safety/provenance | 7/7 |
| Support P0 safety/provenance | 7/7 |
| Conversation regressions | 10/10 |
| Focused Day 12 contract/migration/repository/capability/safety/conversation tests | 134 passed |
| Complete repository suite | 722 passed, 68 skipped |

The 68 full-suite skips are environment-gated tests, including seven new Day 12
PostgreSQL integration cases. No disposable local PostgreSQL URL was configured,
so those seven integration cases were collected and skipped rather than claimed
as executed. Their coverage includes `0007 -> 0008`, frozen-record acceptance,
obsolete-shape rejection, identity rejection and provisional-row guard behavior.

Additional successful checks:

- dependency consistency: no broken requirements;
- bytecode compilation for `src`, `tests` and `migrations`;
- Alembic graph: one head, `20260916_0008`;
- complete offline PostgreSQL SQL generation through `0008`; and
- clean whitespace/error check with `git diff --check`.

The three test warnings are existing dependency deprecations from
Starlette/httpx, AnyIO and google-genai.

## Remaining release gates

Qasim/Carmen still need a disposable PostgreSQL 18 execution of the new
integration cases and review of the uncommitted diff. Any Cloud SQL action also
depends on the compatible scraper image, runtime grants, database configuration,
staged reader/writer proof and the agreed deployment order. These gates were not
performed or relaxed here.
