# AskANU V7 — Day 6: Complete Jobs + Events + Support; feature freeze

**Date:** 2026-09-26  
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

Complete Jobs + Events + Support on the shared planner and freeze features.

## Start / stop contract

**Start from:** latest reviewed main + all prior-day accepted contracts/evidence. On Day 8, use the Day 7 frozen RC manifest rather than arbitrary newer main.

**STOP and escalate** if the work requires silently changing shared API/schema/source authority, moving institutional reasoning to the wrong repo, or violating a frozen invariant.

## Work map

- 0–2h — Jobs: current discovery → technical filter → closing-this-week → first result → requirements.
- 2–4h — Events: today/tomorrow/this Friday/this weekend/next week with Canberra temporal semantics; official+Rubric chat.
- 4–6h — Support: natural problem descriptions route to service/topic, not only exact names.
- 6–8h — Preserve Events source authority and no live Rubric calls.
- 8–10h — Run result references, missing dates, unknowns, and 5-variant language tests.
- 10–12h — Freeze planned features at end of day.

## Acceptance / do-not-cross lines

- No V6 generic fallback for requirements/application/problem-language intents.
- No ticket/modality inference.
- No post-freeze feature expansion.

## Evidence to hand off

PR/SHA; behavioural tests; state/evidence traces; full regression; known unsupported cases; no-prod-action/deploy confirmation.

## Copy-paste AI kickoff prompt

You are Carmen working on AskANU V7 in the RAG/backend lane. Start from latest reviewed main and the frozen V7 behavioural contract. Implement only Day 6's scope through shared primitives. Do not invent unsupported institutional facts, silent source/schema/API changes, domain-specific state engines, or magic-wording shortcuts. Show planned files, behavioural impact, tests, risks and dependencies before implementation. Finish with exact evidence that Qasim can review against today's gate.

---

## Cross-repo handoff rule

If today's work exposes a requirement owned by another repository, record the exact contract/evidence gap and hand it to Qasim. Do not silently implement the other repository's responsibility here.
