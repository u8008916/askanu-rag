# AskANU V7 — Final Release Acceptance Matrix

A release is not V7 because it deployed. It is V7 when the deployed student experience satisfies these behaviours.

| Area | Release acceptance |
|---|---|
| Natural language | Publish explicit denominator: **V7=YES intents passed / total V7=YES intents**. Every V7=YES intent passes >=5 materially different formulations including imperfect language; no intent disappears from release evidence. |
| Context | Typed entities survive interruptions; compatible older result sets can be recovered within frozen deterministic retention; canonical 20-turn journey passes; generic ordinals use most recent compatible set; evicted/out-of-history references clarify rather than guess. |
| Constraints | Hard constraints preserved; explicit overrides win; domain/intent-scoped constraints do not leak. |
| Clarification | Only genuine ambiguity/missing information clarifies; original intent resumes; explicit new request can interrupt. |
| Retrieval | Exact/structured/discovery/semantic paths explicit; retrieval miss distinguishable from selection/reasoning miss. |
| Reasoning | CONFIRMED/DERIVED/PARTIAL/UNKNOWN evidence-grounded. ResultSet = RESULTS/EMPTY/INCOMPLETE. EMPTY/NO_MATCH requires successfully evaluated supported population; UNKNOWN never becomes no-match. |
| Comparison | Missingness visible; no false equivalence; backend order/identity preserved. |
| Six domains | Courses, Scholarships, Accommodation, Jobs, Events, Support pass advertised capability matrices. |
| Events | Upcoming UI official-only; chat official+Rubric; Canberra temporal semantics; no questionable modality/ticket inference. |
| Clear Chat | Visible and structured state reset together; stale references cannot resolve. |
| UI | Existing AskANU design preserved; reusable result/comparison/clarification/unknown states work desktop + mobile. |
| Performance | Lookup/follow-up/discovery latency meets numeric experience targets frozen Day 3 and remains within frozen maximum regression threshold. |
| Safety/provenance | Canonical sources, source authority, unknown safety, injection/source-override tests pass. |
| Public path | Final acceptance runs on deployed Firebase/App → backend → persisted approved data, not only local fixtures. |
| Release order | SHAs/digests frozen → backup/rollback → reviewed migrations → authorized bounded writes → DB verify → RAG deploy/smoke → App deploy → public six-domain smoke → north-star → negative/safety suite → Qasim GO/HOLD. |

## Final product test

Give AskANU to someone who did not build it. They should be able to ask ordinary ANU questions, change topics, refer back, refine constraints, compare results, receive grounded recommendations and useful unknowns, and clear the conversation without being taught special wording.

**GO only when engineering readiness and experience readiness are both release-acceptable.**
