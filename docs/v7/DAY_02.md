# AskANU V7 — Day 2: Implement context + understanding

**Date:** 2026-09-22  
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

Implement bounded session state, entity resolution, intent, constraints, and clarification.

## Start / stop contract

**Start from:** latest reviewed main + all prior-day accepted contracts/evidence. On Day 8, use the Day 7 frozen RC manifest rather than arbitrary newer main.

**STOP and escalate** if the work requires silently changing shared API/schema/source authority, moving institutional reasoning to the wrong repo, or violating a frozen invariant.

## Work map

- 0–2h — Implement ConversationState with typed recent entities, scoped constraints, student facts, PendingClarification, and typed ResultSets.
- 2–4h — Resolver priority: exact identifiers/names/aliases → typed references → compatible state/recency → clarification.
- 4–6h — Parse intent and explicit constraints separately from domain/entity.
- 6–8h — Implement constraint override and domain/intent scoping so constraints do not leak.
- 8–10h — Preserve original intent through clarification; explicit new request supersedes pending clarification.
- 10–12h — Run typo/alias, interruption, correction, Clear Chat, and 3–10-turn state tests.

## Acceptance / do-not-cross lines

- Structured Programming → COMP1110 via safe alias.
- $400 → actually $500 override works.
- “second scholarship” can recover typed older set later.
- Clear Chat leaves no old state.
- References outside retained state clarify rather than resolve by guess.

## Evidence to hand off

PR/SHA; behavioural tests; state/evidence traces; full regression; known unsupported cases; no-prod-action/deploy confirmation.

## Frozen Day 2 clarification and implementation

Qasim's 2026-09-24 clarification freezes:

- independent `DATE_WINDOW` and `TIME_OF_DAY_WINDOW` constraints;
- additive internal `QueryInterpretation` provenance for explicit/inherited
  constraints and typed-state/ResultSet references; and
- intent families `LOOKUP`, `FACT_LOOKUP`, `DISCOVER`, `COMPARE`,
  `CLARIFICATION_RESPONSE`, with operations `REFINE_RESULTS`,
  `CONTINUE_RESULTS`, and `RETURN_TOPIC`.

Implementation lives in:

- `src/askanu_rag/interpretation.py` — deterministic domain/entity/intent/
  constraint interpretation, bounded safe aliases and user-stated context;
- `src/askanu_rag/conversation_orchestrator.py` — authoritative state writes,
  clarification lifecycle, corrections and typed ResultSet selections;
- `src/askanu_rag/retrieval_planning.py` — contract-only retrieval handoff; and
- `src/askanu_rag/evidence_selection.py` — approved-evidence bundle boundary.

The external `conversation_state` schema version, shape and retention bounds are
unchanged. Retrieval ranking, BM25/FTS, embeddings, reranking and framework
selection remain Day 3 work.

### Targeted review corrections

- Canonical identity resolution accepts an injected approved entity catalogue;
  bounded aliases and typo handling remain separate understanding-layer inputs.
- A replaceable deterministic problem-language resolver complements lexical
  domain signals. Ambiguous multi-domain matches clarify rather than guess.
- Day 2 acceptance includes both deterministic 10-turn and 20-turn
  context/state journeys.
- When explicit `DATE_WINDOW` or `TIME_OF_DAY_WINDOW` meets legacy
  `temporal_window`, overlapping legacy authority is removed while a recognised
  independent temporal component is converted and preserved.

These corrections do not add retrieval optimisation or change the V1 state
envelope, source authority, evidence rules, migrations or production state.

### Final shared transport contract

The App-to-RAG Ask boundary is frozen at 256 KiB for the complete raw request.
Within it, compact serialized history is limited to 96 KiB, compact serialized
`conversation_state` to 128 KiB, and the question to 2,000 Unicode code points
plus an 8 KiB UTF-8 defense-in-depth guard. One history turn allows a 128-
character `turn_id` and 10,000-character `content`; the existing ten-turn limit
and aggregate history budget remain authoritative.

Component measurement uses deterministic compact JSON (`ensure_ascii=False`,
finite JSON values only, `,`/`:` separators, sorted object keys) encoded as
UTF-8. Complete-body measurement uses the raw HTTP bytes before parsing. No
field is truncated. Oversize requests follow the controlled 413 path, and RAG
must not emit authoritative state above 128 KiB.

The question byte guard is deliberately redundant under the current character
cap: 2,000 valid Unicode code points require at most 8,000 UTF-8 bytes, below
8,192. Keeping both validators protects the shared transport contract if the
character cap changes later. This correction adds no conversation semantic,
retrieval, migration, server-session or production behaviour.

## Copy-paste AI kickoff prompt

You are Carmen working on AskANU V7 in the RAG/backend lane. Start from latest reviewed main and the frozen V7 behavioural contract. Implement only Day 2's scope through shared primitives. Do not invent unsupported institutional facts, silent source/schema/API changes, domain-specific state engines, or magic-wording shortcuts. Show planned files, behavioural impact, tests, risks and dependencies before implementation. Finish with exact evidence that Qasim can review against today's gate.

---

## Cross-repo handoff rule

If today's work exposes a requirement owned by another repository, record the exact contract/evidence gap and hand it to Qasim. Do not silently implement the other repository's responsibility here.
