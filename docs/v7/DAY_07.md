# AskANU V7 — Day 7: Cross-domain torture + integration

**Date:** 2026-09-27  
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

Run cross-domain backend torture and repair only general/release-critical defects.

## Start / stop contract

**Start from:** latest reviewed main + all prior-day accepted contracts/evidence. On Day 8, use the Day 7 frozen RC manifest rather than arbitrary newer main.

**STOP and escalate** if the work requires silently changing shared API/schema/source authority, moving institutional reasoning to the wrong repo, or violating a frozen invariant.

## Work map

- 0–2h — Execute 1/3/10/20-turn suites with typed entity/result memory.
- 2–4h — Test interruption, return, pronouns, correction, scoped constraints, and pending clarification.
- 4–6h — Test contradiction, prompt injection/source override, and unsupported intent.
- 6–8h — Classify failures: interpretation/state vs retrieval vs evidence selection vs reasoning.
- 8–10h — Recheck Recall@K and latency against Day 3 baseline and frozen Day 3 release thresholds.
- 10–12h — Regression provenance/security/unknown semantics.

## Acceptance / do-not-cross lines

- No new feature architecture unless a P1 exposes it.
- No source authority regression.
- No state leak after Clear Chat.

## Evidence to hand off

PR/SHA; behavioural tests; state/evidence traces; full regression; known unsupported cases; no-prod-action/deploy confirmation.

## Copy-paste AI kickoff prompt

You are Carmen working on AskANU V7 in the RAG/backend lane. Start from latest reviewed main and the frozen V7 behavioural contract. Implement only Day 7's scope through shared primitives. Do not invent unsupported institutional facts, silent source/schema/API changes, domain-specific state engines, or magic-wording shortcuts. Show planned files, behavioural impact, tests, risks and dependencies before implementation. Finish with exact evidence that Qasim can review against today's gate.

---

## Cross-repo handoff rule

If today's work exposes a requirement owned by another repository, record the exact contract/evidence gap and hand it to Qasim. Do not silently implement the other repository's responsibility here.
