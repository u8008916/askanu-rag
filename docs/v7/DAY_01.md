# AskANU V7 — Day 1: Freeze shared V7 contracts

**Date:** 2026-09-21  
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

Freeze conversational intelligence contracts and prove the state model is executable.

## Start / stop contract

**Start from:** latest reviewed main + all prior-day accepted contracts/evidence. On Day 8, use the Day 7 frozen RC manifest rather than arbitrary newer main.

**STOP and escalate** if the work requires silently changing shared API/schema/source authority, moving institutional reasoning to the wrong repo, or violating a frozen invariant.

## Work map

- 0–2h — Inventory V6 ask/history/routing/retrieval failure modes.
- 2–4h — Define ConversationState, typed per-domain entity recency, ConstraintSet scope, PendingClarification, and typed ResultSet lifecycle.
- 4–6h — Define DOMAIN / ENTITY / INTENT / CONSTRAINTS interpretation contract and ambiguity rules.
- 6–8h — Define RetrievalPlan, EvidenceBundle, and CONFIRMED / DERIVED / PARTIAL / UNKNOWN semantics.
- 8–10h — By ~hour 8, implement a tiny state spike: COMP1110 → Warrumbul → “back to the course”.
- 10–12h — Publish at least 12 golden state transitions and Day 2 implementation files/tests.

## Acceptance / do-not-cross lines

- No one-current-topic design.
- No persistent profile.
- No source/API authority change without review.
- Typed ResultSet and constraint scope are explicit.

## Evidence to hand off

PR/SHA; behavioural tests; state/evidence traces; full regression; known unsupported cases; no-prod-action/deploy confirmation.

The executable RAG-owned contract review candidate and conditional Day 2
interface handoff are recorded in
[`DAY_01_SHARED_CONTRACTS.md`](DAY_01_SHARED_CONTRACTS.md). Carmen's
implementation is ready for PM review; Qasim owns the final shared-contract
freeze, Day 1 GO/HOLD and Day 2 GO decisions. Day 2 remains on hold until that
review/freeze is complete.

## Copy-paste AI kickoff prompt

You are Carmen working on AskANU V7 in the RAG/backend lane. Start from latest reviewed main and the frozen V7 behavioural contract. Implement only Day 1's scope through shared primitives. Do not invent unsupported institutional facts, silent source/schema/API changes, domain-specific state engines, or magic-wording shortcuts. Show planned files, behavioural impact, tests, risks and dependencies before implementation. Finish with exact evidence that Qasim can review against today's gate.

---

## Cross-repo handoff rule

If today's work exposes a requirement owned by another repository, record the exact contract/evidence gap and hand it to Qasim. Do not silently implement the other repository's responsibility here.
