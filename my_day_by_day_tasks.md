# AskANU V6 - Carmen day-by-day tasks

**Ownership:** RAG/backend
**Primary repo:** askanu-rag

## V6 execution rule

A day is not complete because code exists. Use the acceptance criteria/evidence from the V6 PDF. Domain Complete requires >=99% entity + required source-present information + capability coverage and 100% critical provenance/safety.

## Day 11 - Tue 15 Sep 2026 - 3h

**Focus:** RAG/backend - first-three-domain 99% retrieval audit + contract gap triage

**Primary outcome:** Use the short Tuesday block to identify the highest-leverage retrieval/capability gaps that would stop Courses, Scholarships or Jobs reaching the V6 99% gate.

**Work map:**
- **0-1h - Coverage audit:** Compare frozen capability catalogues with current deterministic retrieval paths/tests. Identify missing capability families caused by data vs retrieval.
- **1-2h - Contract decisions:** Inspect expanded-source field inventory, especially Jobs requirements/selection criteria. Propose only minimum shared contract changes needed for intended questions.
- **2-3h - Golden suite prep:** Add/draft highest-value missing tests for programs/majors/minors, scholarship breadth and multi-job queries so full-capacity owners can land fixes safely.

**Acceptance criteria:**
- Highest-value retrieval gaps are classified with owner/data dependency.
- Any shared contract addition is explicitly proposed and approved before implementation.
- New/updated golden tests cover the most important missing capability families.
- No regression to existing Courses/Scholarships/Jobs vertical-slice behavior.

**Evidence:**
- Small RAG PR/SHA or audit note.
- Gap matrix: capability -> current behavior -> blocker owner.
- Focused test commands/results.
- Explicit Jobs requirements contract recommendation.

**Do not / escalate:**
- Do not exceed 3h busy-day scope.
- Do not add a model-only workaround for absent evidence.
- Do not create a new endpoint/status without Qasim approval.

**Copy-paste AI kickoff:**

> You are Carmen in askanu-rag on V6 Day 11. Read AGENTS.md, AI_SETUP, current DATA/API contracts and the V6 99% spec before editing. Today is a 3-hour audit/retrieval block while Will and Qasim expand Courses, Scholarships and Jobs. Compare the defined capability catalogue with current deterministic retrieval and tests. Classify every gap as source/data, shared contract, or RAG behavior. Focus first on capability families that would block the 99% gate. Inspect any proposed Jobs requirements field against the approved public-detail evidence; do not invent a parallel schema. Make only small reviewed changes/tests that can be merged today. Preserve exact-first identifiers, source provenance, missing-evidence behavior and the frozen AskResponse statuses.

## Day 12 - Wed 16 Sep 2026 - 14h

**Focus:** RAG/backend - Accommodation + Support retrieval to 99% capability coverage

**Primary outcome:** Build grounded Accommodation comparison and Support routing over broad approved data, then prove the defined capability suites and session behavior.

**Work map:**
- **0-3h - Contract + fixtures:** Review Will source-field inventory, freeze retrieval inputs/clarification rules and build exact/compare/no-evidence fixtures for both domains.
- **3-7h - Accommodation retrieval:** Implement deterministic entity lookup, compare/cost/features/how-to-apply/eligibility flows over stored records. Explicitly handle unknown live vacancy.
- **7-11h - Support routing:** Implement source-grounded service routing, exact service/contact/location/published-hours/access flows and conservative urgent/high-stakes behavior.
- **11-14h - Capability + conversation proof:** Run broad suites across many entities plus cross-domain follow-up, ambiguity, pending clarification, fresh-facts-over-history and New Chat reset.

**Acceptance criteria:**
- Accommodation capability suite >=99% or quantified blocker.
- Support capability suite >=99% or quantified blocker.
- No unsupported live vacancy/hours/high-stakes assurance.
- Cross-domain clarification/follow-up/reset remains correct.
- Prior three-domain regressions remain green.

**Evidence:**
- RAG PR/SHA + full/focused test counts.
- Capability coverage numerator/denominator for both domains.
- Example conversations for compare/routing/negative/high-stakes cases.
- Deployment note + live request IDs after Qasim gate.

**Do not / escalate:**
- Do not create persistent user profiles.
- Do not infer live vacancy or missing hours.
- Do not let prior chat facts override fresh source evidence.
- Do not broaden the shared response/status contract silently.

**Copy-paste AI kickoff:**

> You are Carmen in askanu-rag on V6 Day 12. Read the approved Accommodation/Support source-field contracts and V6 capability catalogues before coding. Build retrieval against broad stored data, not hand-built fixtures alone. Accommodation must support exact lookup, comparisons, costs/features/application/eligibility and evidence-based suitability while treating live vacancy as unknown unless an approved live source exists. Support must route users to official services using only published purpose/audience/contact/location/hours/access evidence, with conservative behavior for urgent/high-stakes language. Preserve session-only clarification and fresh retrieval. Add deterministic golden suites across many entities and return partial/insufficient rather than filling gaps.

## Day 13 - Thu 17 Sep 2026 - 3h

**Focus:** RAG/backend - five-domain release regression + P0 backend freeze

**Primary outcome:** Use the short block to close the highest-value backend correctness defect and freeze a stable five-domain RAG for Friday.

**Work map:**
- **0-1h - Golden regression:** Run high-value deterministic/clarification/provenance subset across Courses, Scholarships, Jobs, Accommodation and Support.
- **1-2h - P0/P1 repair:** Fix only reproduced release-blocking backend defect; otherwise strengthen a missing acceptance test.
- **2-3h - Freeze + handoff:** Run deployment smoke, record exact RAG SHA/revision/env assumptions and hand Qasim known issues/rollback note.

**Acceptance criteria:**
- Five-domain focused regression passes or exact P0 owner exists.
- No new contract/status/source change.
- RAG deployment smoke and private-auth path green.
- Exact freeze SHA/revision and known issues recorded.

**Evidence:**
- RAG freeze SHA/revision.
- Focused test output.
- Any P0 fix PR + regression.
- Rollback/known-issue note.

**Do not / escalate:**
- Do not start Events/Rubric.
- Do not refactor stable retrieval.
- Do not change shared response contract.

**Copy-paste AI kickoff:**

> You are Carmen in askanu-rag on V6 Day 13. Today is demo stabilization. Run the highest-value five-domain golden/regression subset, including temporal Jobs, Course/program identifiers, scholarship clarification, Accommodation missing-vacancy and Support high-stakes routing. Fix only a reproduced P0/P1 that threatens Friday. Do not begin Events/Rubric or redesign retrieval abstractions. Verify current RAG deployment/private auth, record exact SHA/revision and provide Qasim a concise rollback/known-issue handoff.

## Day 14 - Fri 18 Sep 2026 - 14h

**Focus:** RAG/backend - presentation stability + backend P0 support + feedback capture

**Primary outcome:** Protect the pinned backend during the GDG ANU presentation, support factual architecture/retrieval questions and capture backend feedback without live refactoring.

**Work map:**
- **0-3h - Final backend smoke:** Run contract/golden subset, representative query per completed domain, clarification/reset/provenance/error sanitization and current RAG env check.
- **3-6h - Presentation readiness:** Review architecture/retrieval/source-grounding talking points; keep rollback/revision info ready; no optional changes.
- **6-10h - Demo support:** Support Qasim during presentation; diagnose only if live issue occurs; prefer fallback/rollback to live refactor. Capture comments accurately.
- **10-14h - Feedback triage:** Reproduce backend/correctness feedback against real source/data; classify defect vs requirement/preference/TBC; create acceptance tests/issues for Saturday/Sunday.

**Acceptance criteria:**
- Focused backend smoke green or safe fallback known.
- No unreviewed experimental backend change enters demo RC.
- Stakeholder backend feedback captured/classified with reproduction where possible.
- Exact deployed RAG revision remains known.

**Evidence:**
- Pre-demo test output + RAG revision.
- Any P0 fix PR/regression.
- Backend feedback log + acceptance-test candidates.
- Post-demo blocker/priority note.

**Do not / escalate:**
- Do not live-refactor during presentation.
- Do not accept model-only fixes for source gaps.
- Do not start Events/Rubric before feedback is classified.

**Copy-paste AI kickoff:**

> You are Carmen on V6 Day 14, GDG ANU presentation day. Protect the pinned RAG. Run a focused pre-demo smoke and make only P0 fixes with regression evidence. During the presentation, do not live-refactor; if a backend issue appears, diagnose and use the known rollback/fallback path. Be ready to explain deterministic-first retrieval, grounding, source provenance, session-only context, private RAG and missing-evidence behavior. Capture stakeholder comments close to verbatim. After the meeting, reproduce factual correctness claims against the actual source/data before opening an issue and write acceptance tests for confirmed defects.

## Day 15 - Sat 19 Sep 2026 - 14h

**Focus:** RAG/backend - Events retrieval to 99% capability target + accepted feedback fixes

**Primary outcome:** Complete the sixth domain over stored approved event data and implement only high-value accepted backend feedback that preserves frozen contracts.

**Work map:**
- **0-3h - Events contract/tests:** Review selected source schema, date/time/timezone semantics and capability suite; build today/this-week/date-range/category/no-match/provenance fixtures.
- **3-7h - Deterministic retrieval:** Implement exact/upcoming/time-window/category/location/format filters over stored records; preserve canonical source and Canberra temporal semantics.
- **7-10h - Capability + negative suite:** Run broad Events golden cases including ambiguity/missing timeframe, expired/cancelled and source provenance; fix only release-relevant gaps.
- **10-14h - Accepted feedback + regression:** Implement highest-value confirmed backend feedback that fits frozen architecture; run six-domain regression and live deployment smoke.

**Acceptance criteria:**
- Events capability suite >=99% or exact quantified blocker.
- No synchronous external Events/Rubric call in RAG request path.
- P0 temporal/provenance cases pass 100%.
- Accepted backend feedback is regression-tested.
- Prior five domains remain green.

**Evidence:**
- RAG PR/SHA + tests.
- Events capability coverage report.
- Deployed Events request IDs/source cards.
- Accepted feedback issue -> fix/test evidence.

**Do not / escalate:**
- Do not create a broad new retrieval abstraction.
- Do not call Rubric live at question time.
- Do not implement unclassified stakeholder suggestions.

**Copy-paste AI kickoff:**

> You are Carmen in askanu-rag on V6 Day 15. Complete Events against stored approved records only. Use the source/window/schema frozen by Qasim/Will. Implement deterministic Canberra-aware today/this-week/date-range/upcoming/category/location/format behavior, exact event lookup, registration/details where stored, clarification for missing timeframe and safe no-match/expired/cancelled handling. Never call Rubric or any external event endpoint synchronously from /api/v1/ask. If Rubric is not approved, official ANU Events remains the source. After Events reaches capability target, implement only confirmed Friday backend feedback that is small and compatible. Finish with six-domain regression and live source-grounded smoke.

## Day 16 - Sun 20 Sep 2026 - 15h

**Focus:** RAG/backend - final six-domain correctness, conversation and performance sweep

**Primary outcome:** Use the final heavy day to close any remaining RAG/capability/conversation gap, then leave backend work small enough for one-hour hardening.

**Work map:**
- **0-3h - Factual audit:** Run latest six-domain capability matrix; rank failed/weak cases by P0/P1 and distinguish source/data vs retrieval vs conversation.
- **3-7h - Close capability gaps:** Fix highest-value deterministic/retrieval gaps that keep any domain below 99%; add regression tests and preserve source/missing-evidence semantics.
- **7-11h - Conversation edge cases:** Non-adjacent follow-up, first/second/both/correction, topic switch, ambiguity, pending clarification, fresh facts vs stale history, Clear/New Chat.
- **11-15h - Reliability + performance freeze:** Provider/DB/index failure paths, latency/bounded candidates/context, privacy-safe logs, final full suite, docs/known issues and handoff.

**Acceptance criteria:**
- No domain remains below 99% due to a fixable RAG gap, or exact blocker is documented.
- Cross-domain conversation/reset edge cases pass.
- Failure/error/provenance/privacy tests pass.
- Measured latency/context/candidate behavior is acceptable or quantified.
- Backend remaining work fits one-hour slices.

**Evidence:**
- Final RAG SHA + full test counts.
- Six-domain capability/conversation report.
- Failure/performance evidence.
- Known issues + one-hour backlog.

**Do not / escalate:**
- Do not add a new agent/account/persistent-memory feature.
- Do not optimize blindly.
- Do not weaken missing-evidence/provenance rules.

**Copy-paste AI kickoff:**

> You are Carmen in askanu-rag on V6 Day 16, the final planned heavy day. Start from the six-domain coverage/capability report and fix only material correctness/retrieval/conversation gaps that keep a domain below target or threaten release. Run cross-domain session edge cases, ensure fresh retrieval overrides stale historical statements, and preserve clarification/reset semantics. Exercise provider/DB/index failures, safe errors, source provenance and bounded retrieval/context. Optimize only if measured latency/cost requires it. End with a full regression, exact remaining P0/P1/P2 and backend work sized for the one-hour-per-day phase. No new product feature.

## 21 Sep - 3 Oct: one-hour hardening phase

### Day 17 - Mon 21 Sep - SECURITY + PRIVACY AUDIT
- **~45 min:** Rerun injection/output/provenance/privacy-log subset; fix one reproduced backend risk only.
- **~15 min proof:** RAG security PASS/PR.

### Day 18 - Tue 22 Sep - ACCESSIBILITY + MOBILE PASS
- **~45 min:** Check compact clarification/error/source payloads and serialization; fix one real contract issue if reproduced.
- **~15 min proof:** RAG mobile-contract PASS/PR.

### Day 19 - Wed 23 Sep - FAILURE + RECOVERY PASS
- **~45 min:** Simulate provider/DB/index failure; stale/failed must not masquerade as current.
- **~15 min proof:** RAG failure PASS/PR.

### Day 20 - Thu 24 Sep - PERFORMANCE + COST PASS
- **~45 min:** Measure retrieval candidates/context/model latency on representative questions; optimize only a proven hotspot.
- **~15 min proof:** RAG latency/cost note or PR.

### Day 21 - Fri 25 Sep - SIX-DOMAIN REGRESSION
- **~45 min:** One supported + one negative/clarification case per domain; inspect status/provenance.
- **~15 min proof:** RAG six-domain regression note.

### Day 22 - Sat 26 Sep - DOCS + RUNBOOKS
- **~45 min:** Update RAG setup/contracts/retrieval/failure notes for current six-domain state.
- **~15 min proof:** RAG docs PR/PASS.

### Day 23 - Sun 27 Sep - FREEZE READINESS
- **~45 min:** Close or explicitly accept top RAG P0/P1; run focused release subset.
- **~15 min proof:** RAG freeze-readiness note.

### Day 24 - Mon 28 Sep - FEATURE FREEZE
- **~45 min:** Run contract/golden subset; reject new model/architecture experiments.
- **~15 min proof:** RAG freeze note/tag candidate.

### Day 25 - Tue 29 Sep - FROZEN REGRESSION
- **~45 min:** Run frozen contract/golden/temporal/conversation subset; fix only reproduced blocker.
- **~15 min proof:** RAG frozen-regression PASS/PR.

### Day 26 - Wed 30 Sep - RELEASE-CANDIDATE DRILL
- **~45 min:** Restart/deploy known RAG RC; representative queries + failure smoke.
- **~15 min proof:** RAG RC drill evidence.

### Day 27 - Thu 1 Oct - FINAL SECURITY + SOURCE AUDIT
- **~45 min:** Dependency/secret scan + injection/output/provenance subset.
- **~15 min proof:** RAG final security report.

### Day 28 - Fri 2 Oct - RELEASE EVE
- **~45 min:** Final contract/temporal/provenance/conversation subset; record SHA/revision.
- **~15 min proof:** Final RAG test record.

### Day 29 - Sat 3 Oct - FINAL RELEASE
- **~45 min:** Confirm deployed SHA/config; supported + unsupported + clarification smoke.
- **~15 min proof:** RAG final health.
