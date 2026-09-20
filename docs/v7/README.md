# AskANU V7 — askanu-rag Execution Plan

**Execution window:** 21–28 September 2026  
**Primary lane:** RAG / backend / conversational intelligence  
**Source of truth:** frozen AskANU V7 master execution plan.

## How to use this folder

Open the current day's file before starting work. The day is complete only when the required acceptance evidence exists; code alone is not completion.

Each day file contains only the work this repository/owner needs, plus cross-repo dependencies and gates necessary to avoid implementing another repository's responsibilities.

## Frozen repo boundaries

- Own conversation state, entity resolution, intent/constraint interpretation, clarification, retrieval planning, evidence selection, reasoning, answer-state semantics, and backend APIs.
- Do not implement App presentation logic or scraper/source collection logic.
- Do not call Rubric live from the request path.
- Do not silently widen schemas/source authority; cross-repo contract changes require Qasim review.
- Day 8 deploys only the Day 7 frozen RC SHA/digest.

## Shared V7 invariants

- AskANU should feel like talking to an ANU-aware assistant, not searching an ANU database.
- Never make the student learn how to prompt AskANU.
- Understand → Remember → Retrieve → Reason → Communicate.
- Session state is structured and bounded; conversation history alone is not state.
- DOMAIN, ENTITY, INTENT, and CONSTRAINTS are separate.
- Answer epistemic state is CONFIRMED / DERIVED / PARTIAL / UNKNOWN.
- ResultSet state is RESULTS / EMPTY / INCOMPLETE; UNKNOWN must never be converted into NO_MATCH.
- Hard constraints are never silently ignored.
- Missing evidence remains unknown rather than false.
- Every V7=YES intent must pass at least five materially different formulations.
- Feature expansion stops at the end of Day 6. Day 7 is torture/integration; Day 8 is release.
- Engineering readiness and experience readiness are reported separately.

## Files

- `DAY_01.md` … `DAY_08.md` — repo-specific daily execution briefs.
- `FINAL_RELEASE_ACCEPTANCE.md` — shared release gate relevant to all repos.
