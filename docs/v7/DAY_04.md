# AskANU V7 — Day 4: Prove Accommodation vertical

**Date:** 2026-09-24  
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

Complete Accommodation as the first full E2E V7 conversational vertical.

## Start / stop contract

**Start from:** latest reviewed main + all prior-day accepted contracts/evidence. On Day 8, use the Day 7 frozen RC manifest rather than arbitrary newer main.

**STOP and escalate** if the work requires silently changing shared API/schema/source authority, moving institutional reasoning to the wrong repo, or violating a frozen invariant.

## Work map

- 0–2h — Broad discovery → bounded results; apply source-backed self-catered/price/preferences; prove truthful EMPTY when fully evaluated.
- 2–4h — Compare first two with missingness preserved; “second one” selects stable entity; refine max price.
- 4–6h — Cost/catering/application follow-ups resolve current residence.
- 6–8h — Current availability returns useful UNKNOWN + official next action.
- 8–10h — Switch to course then “back to accommodation” recovers typed entity/result.
- 10–12h — Run full vertical across 5 natural-language variants for advertised intents.

## Acceptance / do-not-cross lines

- Accommodation is architecture proof, not a one-off hack.
- Vacancy never inferred.
- Application must not fall into Courses fallback.
- No accommodation-only memory engine.

## Evidence to hand off

PR/SHA; behavioural tests; state/evidence traces; full regression; known unsupported cases; no-prod-action/deploy confirmation.

## Copy-paste AI kickoff prompt

You are Carmen working on AskANU V7 in the RAG/backend lane. Start from latest reviewed main and the frozen V7 behavioural contract. Implement only Day 4's scope through shared primitives. Do not invent unsupported institutional facts, silent source/schema/API changes, domain-specific state engines, or magic-wording shortcuts. Show planned files, behavioural impact, tests, risks and dependencies before implementation. Finish with exact evidence that Qasim can review against today's gate.

---

## Cross-repo handoff rule

If today's work exposes a requirement owned by another repository, record the exact contract/evidence gap and hand it to Qasim. Do not silently implement the other repository's responsibility here.
