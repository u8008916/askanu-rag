# AskANU V7 — Day 3: Build retrieval + reasoning

Measured implementation evidence:
`DAY_03_RETRIEVAL_REASONING_HANDOFF.md`.

**Date:** 2026-09-23  
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

Build the shared retrieval planner, typed result memory, and grounded reasoning layer.

## Start / stop contract

**Start from:** latest reviewed main + all prior-day accepted contracts/evidence. On Day 8, use the Day 7 frozen RC manifest rather than arbitrary newer main.

**STOP and escalate** if the work requires silently changing shared API/schema/source authority, moving institutional reasoning to the wrong repo, or violating a frozen invariant.

## Work map

- 0–2h — Map resolved intent/constraints to exact, structured, discovery, and semantic candidate strategies.
- 2–4h — Store ordered canonical identities + query/constraints in typed ResultSet with RESULTS / EMPTY / INCOMPLETE status.
- 4–6h — Separate broad candidate recall from evidence selection and final reasoning.
- 6–8h — Implement CONFIRMED/DERIVED/PARTIAL/UNKNOWN answer orchestration plus EMPTY/NO_MATCH vs UNKNOWN result semantics.
- 8–10h — Benchmark K=5/10/20 for Recall@K, noise, and final correctness; distinguish retrieval miss from selection/reasoning miss.
- 10–12h — Baseline p50/p95 end-to-end latency for lookup, discovery, and follow-up; propose numeric experience targets and maximum regression threshold for Qasim to freeze.

## Acceptance / do-not-cross lines

- Exact IDs do not depend on vector similarity.
- Hard filters never silently relax.
- EMPTY only after supported population was successfully evaluated; incomplete evidence is never no-match.
- No embeddings/framework migration without benchmark need.
- Internal scores never become product truth.
- Performance evidence ends with proposed numeric release gates.

## Evidence to hand off

PR/SHA; behavioural tests; state/evidence traces; full regression; known unsupported cases; no-prod-action/deploy confirmation.

## Copy-paste AI kickoff prompt

You are Carmen working on AskANU V7 in the RAG/backend lane. Start from latest reviewed main and the frozen V7 behavioural contract. Implement only Day 3's scope through shared primitives. Do not invent unsupported institutional facts, silent source/schema/API changes, domain-specific state engines, or magic-wording shortcuts. Show planned files, behavioural impact, tests, risks and dependencies before implementation. Finish with exact evidence that Qasim can review against today's gate.

---

## Cross-repo handoff rule

If today's work exposes a requirement owned by another repository, record the exact contract/evidence gap and hand it to Qasim. Do not silently implement the other repository's responsibility here.
