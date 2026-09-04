# Carmen's AskANU V3 Day-by-Day Tasks

**Primary lane:** RAG / backend

This is a role-filtered copy of the V3 schedule. The shared objective is included so you can see what the rest of the team needs from you.

**Daily rule:** finish the listed deliverable, run the listed verification, surface blockers immediately, and do not invent new scope when blocked.

## Day 1 — Saturday, 05 September 2026 — 5h/person
**Phase:** BOOTSTRAP + CONTRACT FREEZE
**Shared objective:** Make all three repos usable, aligned, and safe for AI-assisted development.

### Carmen - RAG repo
**Goal:** Create the RAG service skeleton against frozen contracts.
**Do:**
- Read V3 API/data/conversation/security docs; flag contradictions before coding.
- Create Python package/test skeleton and a minimal `/health` + `/api/v1/ask` stub that returns contract-shaped mock JSON.
- Define typed request/response models for the six frozen statuses.
- Add baseline contract tests for valid request, malformed request, and `needs_clarification`.
**Verify:** Run the RAG test suite and show contract-shaped JSON only; no Gemini/retrieval yet.
**Deliverable:** PR: RAG bootstrap + passing contract tests.
**Dependency / fallback:** Needs Qasim to freeze V3 contract files. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: All three repos run locally, contract docs match, and each owner has a mergeable Day 1 PR.

## Day 2 — Sunday, 06 September 2026 — 5h/person
**Phase:** COURSES DATA FOUNDATION
**Shared objective:** Prove the course/program source can become structured records that RAG and UI can consume.

### Carmen - RAG repo
**Goal:** Build the first exact course/program retrieval interface from fixtures.
**Do:**
- Implement shared data models needed for course/program records.
- Load a representative normalized fixture through repository/data-access code.
- Implement exact course-code lookup and exact program-code lookup before any vector search.
- Add tests for `COMP1110`, spacing/case variants, `BACCT`, and unknown identifiers.
**Verify:** Exact identifiers return the right entity/year and unknown identifiers return no evidence.
**Deliverable:** PR: exact course/program repository path with tests.
**Dependency / fallback:** Needs Will normalized fixture shape + DATA_SCHEMA v1. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: One real ANU course/program page can be normalized into a shared record shape and rendered as a mocked grounded answer.

## Day 3 — Monday, 07 September 2026 — 5h/person
**Phase:** FIRST LOCAL VERTICAL SLICE
**Shared objective:** Make a real ANU course question travel from collected data to the browser with a real source link.

### Carmen - RAG repo
**Goal:** Serve a real single-turn course answer from local structured evidence.
**Do:**
- Create DB/repository adapter for normalized course records.
- Implement request classification for simple standalone course queries.
- Use exact course lookup first and return evidence-backed answer structure without semantic fallback yet.
- Expose source object from the stored canonical URL and add local integration tests.
**Verify:** `What are the prerequisites for COMP1110?` returns only facts present in stored evidence with valid source URL.
**Deliverable:** PR: local `/api/v1/ask` course path + tests.
**Dependency / fallback:** Needs Will record loaded into local DB. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: A student can ask one real course question locally and get a grounded answer with an official ANU source link.

## Day 4 — Tuesday, 08 September 2026 — 5h/person
**Phase:** GROUNDED GEMINI + ABSTENTION
**Shared objective:** Add model synthesis without allowing the model to outrun evidence.

### Carmen - RAG repo
**Goal:** Add grounded Gemini synthesis and strict response validation.
**Do:**
- Build prompt/context assembler using only retrieved approved evidence.
- Require structured model output or validate/repair to the API schema.
- Attach source URLs programmatically from evidence, never from model text.
- Implement `insufficient_evidence` and off-topic paths; add prompt-injection/system-prompt tests.
**Verify:** Supported question cites evidence; unsupported question abstains; model cannot invent a URL.
**Deliverable:** PR: grounded synthesis + validation + safety tests.
**Dependency / fallback:** Needs working Day 3 evidence path. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU can use Gemini for a real course answer while preserving evidence, source provenance and abstention.

## Day 5 — Wednesday, 09 September 2026 — 5h/person
**Phase:** COURSE BREADTH + HYBRID RETRIEVAL
**Shared objective:** Turn the single course demo into a reusable course/program retrieval pattern.

### Carmen - RAG repo
**Goal:** Implement course query planning: exact first, metadata next, semantic only when needed.
**Do:**
- Normalize course codes/names and preserve explicit year/session.
- Add metadata-filtered retrieval for year/session and program/course entity type.
- Add vector retrieval only for semantic descriptions where exact lookup is insufficient.
- Test exact code, course name, explicit year, unknown code and set/list-shaped query behaviour.
**Verify:** Exact course-code query does not depend on top-k similarity; explicit year cannot silently return another year.
**Deliverable:** PR: hybrid course planner + tests.
**Dependency / fallback:** Needs broader Will dataset. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Courses are no longer a one-record demo: the team has a tested reusable discovery, storage, retrieval and UI pattern.

## Day 6 — Thursday, 10 September 2026 — 5h/person
**Phase:** EARLY GCP FOUNDATION
**Shared objective:** Get the real system onto GCP early enough that cloud problems cannot surprise the team later.

### Carmen - RAG repo
**Goal:** Make the RAG service deployable without changing feature logic.
**Do:**
- Add container/service startup configuration and `/health`.
- Move secrets/config to environment/Secret Manager interfaces; no committed credentials.
- Ensure production error responses are controlled JSON.
- Document Cloud SQL connection expectations and migration command.
**Verify:** Container runs locally and health endpoint exposes no secrets.
**Deliverable:** PR: deployable RAG service.
**Dependency / fallback:** Uses Qasim GCP service names/config. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: At least a health-level App -> RAG deployment exists in the real GCP environment.

## Day 7 — Friday, 11 September 2026 — 5h/person
**Phase:** DEPLOYED REAL COURSE SLICE
**Shared objective:** Connect cloud services, Cloud SQL and one real course query end-to-end.

### Carmen - RAG repo
**Goal:** Connect deployed RAG to Cloud SQL/pgvector and migrate schema.
**Do:**
- Create versioned DB migration for common/course records and vector extension if used.
- Use service identity/secret-based DB connection.
- Load one real normalized course record and run exact retrieval in cloud.
- Deploy `/ask` course path and capture request ID/latency for smoke test.
**Verify:** Deployed RAG returns the real course answer from Cloud SQL and valid source URL.
**Deliverable:** PR + migration + deployed smoke evidence.
**Dependency / fallback:** Needs Qasim Cloud SQL and Will seed record. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: A real student-facing deployed URL completes the first source-to-answer vertical slice.

## Day 8 — Saturday, 12 September 2026 — 5h/person
**Phase:** SCHEDULED FRESHNESS PROOF
**Shared objective:** Prove AskANU can update safely after source content changes.

### Carmen - RAG repo
**Goal:** Handle changed records and indexing state safely.
**Do:**
- Implement `pending/indexed/failed/stale` handling around embedding updates.
- Ensure DB-update + embedding-failure cannot appear as fully indexed/current.
- Add retrieval rule for stale/failed records where appropriate.
- Test changed vs unchanged content path.
**Verify:** Changed content reindexes; simulated embedding failure is visible and safe.
**Deliverable:** PR: indexing-state/freshness handling.
**Dependency / fallback:** Needs Will content_hash + ingestion state. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU has a proven scheduled, change-aware update path rather than a one-time index.

## Day 9 — Sunday, 13 September 2026 — 5h/person
**Phase:** SCHOLARSHIPS DOMAIN
**Shared objective:** Add structured scholarship ingestion, filtering and the 9-card Featured resource page.

### Carmen - RAG repo
**Goal:** Build scholarship retrieval and clarification rules.
**Do:**
- Add structured filters for open status, student type, study stage/level and area of study.
- Implement session-only clarification when a broad question lacks necessary eligibility context.
- Keep eligibility language evidence-based; do not declare a student definitely eligible unless source supports it.
- Add deterministic endpoint/query for open Featured resource-page records.
**Verify:** Broad scholarship query can clarify; specific query filters correctly; closed records are not presented open.
**Deliverable:** PR: scholarship retrieval/filtering + tests.
**Dependency / fallback:** Needs Will structured scholarship records. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Students can browse current Featured scholarships and ask filtered scholarship questions without persistent profiling.

## Day 10 — Monday, 14 September 2026 — 5h/person
**Phase:** JOBS DOMAIN
**Shared objective:** Add current ANU jobs with deterministic closing-date logic and chat retrieval.

### Carmen - RAG repo
**Goal:** Implement deterministic current-jobs retrieval and job Q&A routing.
**Do:**
- Create open/current filtering based on job status/closing date.
- Sort dated open roles by nearest closing date; undated open roles after them.
- Expose `/api/v1/jobs/current?limit=5`.
- Add tests for expired role, no closing date, fixed-term and known role lookup.
**Verify:** Expired role cannot appear in Current Jobs; ordering is deterministic.
**Deliverable:** PR: jobs endpoint/retrieval + tests.
**Dependency / fallback:** Needs Will jobs records. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU can deterministically surface current jobs and answer job questions using fresh official data.

## Day 11 — Tuesday, 15 September 2026 — 5h/person
**Phase:** ACCOMMODATION + SUPPORT
**Shared objective:** Add two lower-volatility domains with strict claims boundaries.

### Carmen - RAG repo
**Goal:** Add accommodation/support retrieval routes with safe claims.
**Do:**
- Implement entity/semantic retrieval for residences and support services.
- For accommodation, prohibit inference of live vacancy/guaranteed price.
- For support, route to approved ANU/ANUSA services and avoid clinical diagnosis or invented hours.
- Add source-authority metadata and tests for common questions.
**Verify:** Answers distinguish advertised info from live availability and always route support questions to sources.
**Deliverable:** PR: accommodation/support retrieval + safety tests.
**Dependency / fallback:** Needs Will domain records. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Accommodation and Support have real resource pages and grounded chat coverage without overclaiming.

## Day 12 — Wednesday, 16 September 2026 — 5h/person
**Phase:** EVENTS RELEASE SOURCE
**Shared objective:** Ship Events using an approved source while keeping Rubric optional and permission-gated.

### Carmen - RAG repo
**Goal:** Implement deterministic upcoming-event/time semantics.
**Do:**
- Create `/api/v1/events/upcoming?limit=5`.
- Normalize `today`, `tomorrow`, `this Friday`, `next week` in `Australia/Canberra`.
- Exclude past events and sort ascending by start time.
- Keep Rubric-specific fields optional and behind an approved-source flag.
**Verify:** Past event never appears upcoming; boundary tests pass in Canberra timezone.
**Deliverable:** PR: events endpoint/time logic + tests.
**Dependency / fallback:** Needs Will approved ANU Events data. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Upcoming Events works from an approved source; Rubric cannot block the stakeholder demo or release.

## Day 13 — Thursday, 17 September 2026 — 5h/person
**Phase:** CONVERSATION + MOBILE + DEMO STABILISATION
**Shared objective:** Make the six-domain baseline feel coherent as one assistant and freeze tomorrow’s demo scope.

### Carmen - RAG repo
**Goal:** Add current-session follow-up and clarification flows.
**Do:**
- Implement adjacent/non-adjacent entity resolution using bounded recent history.
- Implement pending clarification with `first`, `second`, `both`, direct option and correction.
- Clear pending clarification on clear topic switch and Clear Chat.
- Run conversation golden tests without treating history as factual evidence.
**Verify:** All core clarification examples pass and every factual follow-up retrieves fresh evidence.
**Deliverable:** PR: conversation resolver + tests.
**Dependency / fallback:** Uses frozen conversation contract. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: One deployed, responsive six-domain AskANU baseline is stable enough to rehearse for stakeholders.

## Day 14 — Friday, 18 September 2026 — 5h/person
**Phase:** STAKEHOLDER PRESENTATION
**Shared objective:** Present a stable, real AskANU slice and convert feedback into actionable post-demo work.

### Carmen - RAG repo
**Goal:** Protect RAG stability and provide technical backup during demo.
**Do:**
- Run pre-demo health + representative six-domain questions.
- Fix only P0 answer/retrieval defect discovered before presentation.
- Monitor request errors/latency during rehearsal/presentation.
- After demo, classify RAG feedback into correctness, retrieval, conversation or optional enhancement.
**Verify:** Demo questions return controlled responses and no new experimental change is introduced during presentation window.
**Deliverable:** RAG demo health note + feedback issues.
**Dependency / fallback:** Qasim controls release candidate. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: A stable AskANU is demonstrated to ANU GDG and the remaining schedule is updated from real feedback.

## Day 15 — Saturday, 19 September 2026 — 1h/person
**Phase:** POST-DEMO TRIAGE
**Shared objective:** Convert stakeholder feedback into a realistic remaining plan without immediately expanding scope.

### Carmen - RAG repo
**Goal:** Review RAG feedback and identify one highest-value correction.
**Do:**
- Reproduce the top RAG/correctness complaint if any.
- If none, review lowest-performing golden test and nominate one fix.
**Verify:** Issue has reproducible case + acceptance test.
**Deliverable:** One prioritised RAG issue with test case.
**Dependency / fallback:** Uses stakeholder log. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Every stakeholder comment is triaged; tomorrow starts from actual status, not the old assumption.

## Day 16 — Sunday, 20 September 2026 — 1h/person
**Phase:** TOP DEFECT FIX
**Shared objective:** Use the one-hour window for one tested slice per person, not a new feature.

### Carmen - RAG repo
**Goal:** Fix the highest-priority RAG defect from Sep 19.
**Do:**
- Implement the smallest correction.
- Add regression test and run nearest suite.
**Verify:** Original reproduction now passes without breaking contract.
**Deliverable:** Small RAG PR.
**Dependency / fallback:** If blocked, write failing test + diagnosis. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: The most important post-demo defects have either a tested fix or a reproducible blocker.

## Day 17 — Monday, 21 September 2026 — 1h/person
**Phase:** SOURCE COMPLETENESS AUDIT
**Shared objective:** Find missing evidence before hardening the model around incomplete data.

### Carmen - RAG repo
**Goal:** Run retrieval gap audit against six-domain golden questions.
**Do:**
- Record no-evidence/weak-evidence cases by source/domain.
- Do not tune prompts to hide missing data.
**Verify:** Every gap is classified retrieval vs source coverage.
**Deliverable:** RAG gap list.
**Dependency / fallback:** Needs current source snapshot. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: The team knows exactly which remaining failures are evidence gaps versus retrieval/UI defects.

## Day 18 — Tuesday, 22 September 2026 — 1h/person
**Phase:** MOBILE + ACCESSIBILITY
**Shared objective:** Make the confirmed responsive UI usable, not merely visually similar.

### Carmen - RAG repo
**Goal:** Verify API error/clarification objects remain compact for mobile clients.
**Do:**
- Check no oversized/internal payload is required by UI.
- Fix one contract-compatible serialization issue if found.
**Verify:** Mobile-relevant API fixtures remain contract-valid.
**Deliverable:** RAG mobile-contract check.
**Dependency / fallback:** No API redesign. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU works through the core chat/resource flow on common mobile widths with keyboard-accessible controls.

## Day 19 — Wednesday, 23 September 2026 — 1h/person
**Phase:** SECURITY + PRIVACY
**Shared objective:** Close concrete security/privacy gaps before feature freeze.

### Carmen - RAG repo
**Goal:** Run prompt-injection/output-validation regression.
**Do:**
- Test direct system-prompt extraction and malicious retrieved instructions.
- Fix one release-blocking validation/grounding defect if found.
**Verify:** No tested injection causes source/model boundary escape.
**Deliverable:** Security test report/PR.
**Dependency / fallback:** Uses SECURITY_BASELINE. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Release security/privacy controls are tested and remaining governance questions are explicit.

## Day 20 — Thursday, 24 September 2026 — 1h/person
**Phase:** INGESTION FAILURE + RECOVERY
**Shared objective:** Prove source failures cannot silently corrupt the live index.

### Carmen - RAG repo
**Goal:** Test stale/failed index handling under ingestion failure.
**Do:**
- Simulate record update with embedding failure.
- Ensure retrieval does not treat failed index as silently fresh.
**Verify:** Index status behaves as contract requires.
**Deliverable:** RAG failure test/PR.
**Dependency / fallback:** Needs failure fixture/state. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: One failed source run can be detected, contained and recovered without losing last-known-good data.

## Day 21 — Friday, 25 September 2026 — 1h/person
**Phase:** CONVERSATION EDGE CASES
**Shared objective:** Finish the core session-context behaviours before freeze.

### Carmen - RAG repo
**Goal:** Close non-adjacent/topic-switch/clarification edge cases.
**Do:**
- Run golden conversation cases 43–49.
- Fix one bounded resolver/state defect; no multi-agent expansion.
**Verify:** Core conversation golden set passes.
**Deliverable:** Conversation PR/PASS.
**Dependency / fallback:** Uses frozen contract. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Current-session follow-ups and clarification are reliable enough for release; optional batching cannot jeopardise them.

## Day 22 — Saturday, 26 September 2026 — 1h/person
**Phase:** SIX-DOMAIN REGRESSION
**Shared objective:** Run the whole product as a product, not as six separate demos.

### Carmen - RAG repo
**Goal:** Run one supported + one failure query per domain and inspect provenance.
**Do:**
- Focus on retrieval route/status/source correctness.
- Log any release-blocking regression.
**Verify:** No domain silently falls back to unsupported answer.
**Deliverable:** RAG regression note.
**Dependency / fallback:** Current staging data. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: The team has a single pre-freeze defect list based on a real six-domain regression run.

## Day 23 — Sunday, 27 September 2026 — 4h/person
**Phase:** 4-HOUR CATCH-UP + INTEGRATION
**Shared objective:** Use the only expanded late-phase day to close critical carry-over before feature freeze.

### Carmen - RAG repo
**Goal:** Close highest-priority RAG P0/P1 items and rerun release-critical tests.
**Do:**
- Spend first 2h on top correctness/retrieval blocker.
- Spend next 1h on conversation/temporal regression.
- Final 1h: run focused RAG release suite and document any unresolved risk.
**Verify:** No unresolved RAG P0 remains without explicit release decision.
**Deliverable:** RAG catch-up PRs + test report.
**Dependency / fallback:** Do not start speculative features. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Critical carry-over is closed or explicitly accepted before tomorrow’s feature freeze.

## Day 24 — Monday, 28 September 2026 — 1h/person
**Phase:** FEATURE FREEZE
**Shared objective:** Stop feature growth and lock the release candidate behaviour.

### Carmen - RAG repo
**Goal:** Freeze RAG feature surface and tag remaining fixes as bug-only.
**Do:**
- Run contract/golden subset.
- Reject new architecture/model experiments unless required for P0 bug.
**Verify:** RAG release candidate behaviour documented.
**Deliverable:** RAG freeze note/tag candidate.
**Dependency / fallback:** Bug fixes only. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU enters bug-fix-only mode with a documented release candidate and known issues.

## Day 25 — Tuesday, 29 September 2026 — 1h/person
**Phase:** CLEAN CLONE + REPRODUCIBILITY
**Shared objective:** Prove the project works from repositories and docs, not only from current laptops.

### Carmen - RAG repo
**Goal:** Run RAG setup/tests from a clean clone or clean environment.
**Do:**
- Follow README/AI_SETUP without local hidden state.
- Fix one reproducibility/documentation defect if found.
**Verify:** RAG can start/test from clean clone.
**Deliverable:** Clean-clone evidence/PR.
**Dependency / fallback:** No feature changes. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: The three repos can be reproduced from clean clones using documented configuration.

## Day 26 — Wednesday, 30 September 2026 — 1h/person
**Phase:** SECURITY + DEPENDENCY RELEASE SCAN
**Shared objective:** Run final automated/manual security checks before rehearsal.

### Carmen - RAG repo
**Goal:** Run RAG dependency/security/test scan and inspect safe errors.
**Do:**
- Check dependency vulnerabilities and secret patterns.
- Run injection/output/provenance tests.
**Verify:** No unaccepted critical/high release blocker.
**Deliverable:** RAG security report.
**Dependency / fallback:** Bug fixes only. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Release candidate has a documented security/dependency/privacy status with no unknown critical blocker.

## Day 27 — Thursday, 01 October 2026 — 1h/person
**Phase:** DEPLOYMENT + RECOVERY REHEARSAL
**Shared objective:** Prove the team can deploy, smoke-test and recover before final day.

### Carmen - RAG repo
**Goal:** Verify RAG deploy/restart and health after clean rollout.
**Do:**
- Deploy known RC revision.
- Run representative query and provider/DB failure smoke.
**Verify:** RAG recovers to healthy state using runbook.
**Deliverable:** Deployment rehearsal evidence.
**Dependency / fallback:** No feature changes. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: The team can deploy the release candidate and recover core services using documented steps.

## Day 28 — Friday, 02 October 2026 — 1h/person
**Phase:** FINAL REGRESSION + DEMO PREP
**Shared objective:** Finish only release blockers and prepare a boring, repeatable final demo.

### Carmen - RAG repo
**Goal:** Run final RAG release-critical suite and fix only P0 if present.
**Do:**
- Run contract/temporal/provenance/conversation subset.
- Record final version SHA.
**Verify:** Release-critical RAG tests green or explicit accepted known issue.
**Deliverable:** Final RAG test record.
**Dependency / fallback:** No new features. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Release candidate, data and demo are finalised; only emergency fixes remain for Oct 3.

## Day 29 — Saturday, 03 October 2026 — 1h/person
**Phase:** FINAL RELEASE
**Shared objective:** Release AskANU, run smoke tests, and leave a reproducible handover.

### Carmen - RAG repo
**Goal:** Monitor final RAG release and answer correctness smoke.
**Do:**
- Confirm deployed SHA/config.
- Run one supported + one unsupported + one clarification case.
**Verify:** RAG release is healthy and provenance intact.
**Deliverable:** Final RAG release check.
**Dependency / fallback:** Emergency fixes only. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU is released with traceable versions, healthy sources, passing core flows and a clear known-issues/handover record.
