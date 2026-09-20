# AskANU V7 — Day 8: Production release + post-deploy acceptance

**Date:** 2026-09-28  
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

Deploy reviewed RAG/backend changes and prove production conversational behaviour.

## Start / stop contract

**Start from:** latest reviewed main + all prior-day accepted contracts/evidence. On Day 8, use the Day 7 frozen RC manifest rather than arbitrary newer main.

**STOP and escalate** if the work requires silently changing shared API/schema/source authority, moving institutional reasoning to the wrong repo, or violating a frozen invariant.

## Work map

- 0–2h — Verify migration/deploy delta and rollback path before mutation.
- 2–4h — Deploy only reviewed merged SHA/digest from the Day 7 frozen RC.
- 4–6h — Run post-deploy API/state/retrieval/provenance smoke.
- 6–8h — Run representative north-star conversation on deployed backend.
- 8–10h — Verify no live Rubric request dependency.
- 10–12h — Record production evidence and rollback identifiers.

## Acceptance / do-not-cross lines

- No unreviewed migration.
- No silent source/status contract change.
- Rollback ready before deploy.

## Evidence to hand off

PR/SHA; behavioural tests; state/evidence traces; full regression; known unsupported cases; exact deploy/rollback evidence.

## Copy-paste AI kickoff prompt

You are Carmen working on AskANU V7 in the RAG/backend lane. Start from latest reviewed main and the frozen V7 behavioural contract. Implement only Day 8's scope through shared primitives. Do not invent unsupported institutional facts, silent source/schema/API changes, domain-specific state engines, or magic-wording shortcuts. Show planned files, behavioural impact, tests, risks and dependencies before implementation. Finish with exact evidence that Qasim can review against today's gate.

---

## Cross-repo handoff rule

If today's work exposes a requirement owned by another repository, record the exact contract/evidence gap and hand it to Qasim. Do not silently implement the other repository's responsibility here.
