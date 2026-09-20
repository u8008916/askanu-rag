# AskANU V7 — Day 5: Complete Courses + Scholarships

**Date:** 2026-09-25  
**Repository:** `askanu-rag`  
**Primary owner:** Carmen  

> **Completion rule:** Today is done only when the acceptance evidence exists — code alone is not completion.

## Repo boundary for today

- Own conversation state, entity resolution, intent/constraint interpretation, clarification, retrieval planning, evidence selection, reasoning, answer-state semantics, and backend APIs.
- Do not implement App presentation logic or scraper/source collection logic.
- Do not call Rubric live from the request path.
- Do not silently widen schemas/source authority; cross-repo contract changes require Qasim review.
- Day 8 deploys only the Day 7 frozen RC SHA/digest.

## Primary outcome

Complete Courses + Scholarships through the shared architecture.

## Start / stop contract

**Start from:** latest reviewed main + all prior-day accepted contracts/evidence. On Day 8, use the Day 7 frozen RC manifest rather than arbitrary newer main.

**STOP and escalate** if the work requires silently changing shared API/schema/source authority, moving institutional reasoning to the wrong repo, or violating a frozen invariant.

## Work map

- 0–2h — Courses: lookup/title/code alias, prerequisites, units, supported offering/course facts, and follow-up memory.
- 2–4h — Courses: define explicit boundary for study-plan/program-rule questions not supported by evidence.
- 4–6h — Courses: comparison where meaningful; preserve unknowns.
- 6–8h — Scholarships: discovery/matching/filtering/deadline/result references.
- 8–10h — Implement three eligibility states: enough evidence; missing student information; institutional/complex criteria cannot be determined.
- 10–12h — Run cross-domain course → scholarship → course return and 5-variant intent tests.

## Acceptance / do-not-cross lines

- No eligibility guarantee.
- No generic scholarship search pretending to be matching.
- No prerequisite-only definition of Courses.
- No invented program rules.

## Evidence to hand off

PR/SHA; behavioural tests; state/evidence traces; full regression; known unsupported cases; no-prod-action/deploy confirmation.

## Copy-paste AI kickoff prompt

You are Carmen working on AskANU V7 in the RAG/backend lane. Start from latest reviewed main and the frozen V7 behavioural contract. Implement only Day 5's scope through shared primitives. Do not invent unsupported institutional facts, silent source/schema/API changes, domain-specific state engines, or magic-wording shortcuts. Show planned files, behavioural impact, tests, risks and dependencies before implementation. Finish with exact evidence that Qasim can review against today's gate.

---

## Cross-repo handoff rule

If today's work exposes a requirement owned by another repository, record the exact contract/evidence gap and hand it to Qasim. Do not silently implement the other repository's responsibility here.
