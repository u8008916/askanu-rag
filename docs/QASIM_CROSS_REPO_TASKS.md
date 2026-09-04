# Qasim's AskANU V3 Day-by-Day Tasks

**Primary lane:** PM / integration / GCP / testing / security / release

This is a role-filtered copy of the V3 schedule. The shared objective is included so you can see what the rest of the team needs from you.

**Daily rule:** finish the listed deliverable, run the listed verification, surface blockers immediately, and do not invent new scope when blocked.

## Day 1 — Saturday, 05 September 2026 — 5h/person
**Phase:** BOOTSTRAP + CONTRACT FREEZE
**Shared objective:** Make all three repos usable, aligned, and safe for AI-assisted development.

### Qasim - Cross-repo / GCP / release
**Goal:** Turn V3 into the operational source of truth and initialise project control.
**Do:**
- Create/update the three GitHub repos with V3 starter docs, AI_SETUP and role-specific AGENTS rules.
- Create first issues for Days 1-3 with owners and acceptance criteria.
- Set branch/PR rules after initial commit and ensure `.env`/secret files are ignored.
- Post the WhatsApp daily-update template; create a shared decision log for contract/source changes.
**Verify:** Clone each repo cleanly; confirm docs agree on status enum, repo boundaries, dates, sources and UI.
**Deliverable:** V3 docs merged + Day 1 issues + project tracker ready.
**Dependency / fallback:** Owns contract decisions; must unblock all three teammates. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: All three repos run locally, contract docs match, and each owner has a mergeable Day 1 PR.

## Day 2 — Sunday, 06 September 2026 — 5h/person
**Phase:** COURSES DATA FOUNDATION
**Shared objective:** Prove the course/program source can become structured records that RAG and UI can consume.

### Qasim - Cross-repo / GCP / release
**Goal:** Freeze DATA_SCHEMA v1 for the first vertical slice and prepare local DB work.
**Do:**
- Review Carmen/Will field mapping and resolve naming/year/session differences.
- Define local PostgreSQL + pgvector development setup/migration ownership.
- Create a contract fixture representing one course from scraper output through API response.
- Add integration issues for Day 3 and mark any non-blocking fields for later.
**Verify:** Carmen and Will can both consume the same fixture without adapters invented independently.
**Deliverable:** DATA_SCHEMA v1 + shared course fixture + Day 3 integration issue.
**Dependency / fallback:** Depends on Carmen/Will Day 2 findings. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: One real ANU course/program page can be normalized into a shared record shape and rendered as a mocked grounded answer.

## Day 3 — Monday, 07 September 2026 — 5h/person
**Phase:** FIRST LOCAL VERTICAL SLICE
**Shared objective:** Make a real ANU course question travel from collected data to the browser with a real source link.

### Qasim - Cross-repo / GCP / release
**Goal:** Run the first true cross-repo integration session.
**Do:**
- Start App, RAG, local DB and scraper flow from clean terminals.
- Verify request/response against contract; record any contract mismatch as a decision, not an ad-hoc patch.
- Add one cross-repo smoke-test checklist for the course path.
- Review Git diffs/PRs and merge only the minimal vertical-slice changes.
**Verify:** Clean local run: source -> normalized record -> RAG -> REST -> React -> source link.
**Deliverable:** Recorded vertical-slice smoke test + merged compatible PRs.
**Dependency / fallback:** Coordinates all three repos. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: A student can ask one real course question locally and get a grounded answer with an official ANU source link.

## Day 4 — Tuesday, 08 September 2026 — 5h/person
**Phase:** GROUNDED GEMINI + ABSTENTION
**Shared objective:** Add model synthesis without allowing the model to outrun evidence.

### Qasim - Cross-repo / GCP / release
**Goal:** Run first security/grounding review and fix contract drift.
**Do:**
- Execute golden supported/unsupported/off-topic/injection cases.
- Check normal logs contain request metadata but not raw prompts/full history.
- Review model limits/timeouts/config placeholders and secret handling.
- Update V3 decision log only if an actual team decision changed.
**Verify:** No unsupported factual claim in the Day 4 release-critical sample and no secret/raw-prompt logging.
**Deliverable:** Grounding/security review notes + issues for defects.
**Dependency / fallback:** Needs Carmen/Ben merged changes. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU can use Gemini for a real course answer while preserving evidence, source provenance and abstention.

## Day 5 — Wednesday, 09 September 2026 — 5h/person
**Phase:** COURSE BREADTH + HYBRID RETRIEVAL
**Shared objective:** Turn the single course demo into a reusable course/program retrieval pattern.

### Qasim - Cross-repo / GCP / release
**Goal:** Freeze course-domain baseline and expand golden tests.
**Do:**
- Run course golden tests across exact, name, year/session and unsupported cases.
- Review Will sanity counts and Carmen retrieval routes before bulk ingestion.
- Create performance/cost notes for representative course queries.
- Approve course pattern as template for later domains only if tests pass.
**Verify:** Course-domain gate records PASS/BLOCKED with failing cases linked to issues.
**Deliverable:** Course baseline gate + updated test report.
**Dependency / fallback:** Depends on all course-domain PRs. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Courses are no longer a one-record demo: the team has a tested reusable discovery, storage, retrieval and UI pattern.

## Day 6 — Thursday, 10 September 2026 — 5h/person
**Phase:** EARLY GCP FOUNDATION
**Shared objective:** Get the real system onto GCP early enough that cloud problems cannot surprise the team later.

### Qasim - Cross-repo / GCP / release
**Goal:** Create the GCP project skeleton and least-privilege service identities.
**Do:**
- Use initial Sydney region assumption (`australia-southeast1`) unless blocked by project availability.
- Create App, RAG and Scraper service accounts and Secret Manager placeholders.
- Create initial Cloud Run/Firebase resources and CI/deploy notes; do not grant broad Owner roles to runtime services.
- Deploy health-only App/RAG services and record URLs/config in DEPLOYMENT notes.
**Verify:** App and RAG health endpoints are reachable through intended path and runtime identities are distinct.
**Deliverable:** GCP foundation + deployment record + access matrix.
**Dependency / fallback:** Requires billing/project access; if blocked, complete IaC/config/docs and open blocker. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: At least a health-level App -> RAG deployment exists in the real GCP environment.

## Day 7 — Friday, 11 September 2026 — 5h/person
**Phase:** DEPLOYED REAL COURSE SLICE
**Shared objective:** Connect cloud services, Cloud SQL and one real course query end-to-end.

### Qasim - Cross-repo / GCP / release
**Goal:** Complete cloud IAM chain and run the first deployed vertical-slice acceptance test.
**Do:**
- Configure App -> RAG service-to-service authentication and least privilege.
- Verify browser cannot directly reach Cloud SQL.
- Run deployed clean-path and one safe failure test.
- Record cost/billing baseline and any deployment blocker before domain expansion.
**Verify:** Firebase -> App -> authenticated RAG -> Cloud SQL -> answer/source works.
**Deliverable:** Deployment gate marked GO / GO WITH CARRY-OVER / BLOCKED.
**Dependency / fallback:** Coordinates all cloud components. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: A real student-facing deployed URL completes the first source-to-answer vertical slice.

## Day 8 — Saturday, 12 September 2026 — 5h/person
**Phase:** SCHEDULED FRESHNESS PROOF
**Shared objective:** Prove AskANU can update safely after source content changes.

### Qasim - Cross-repo / GCP / release
**Goal:** Verify freshness proof, logs and cost before adding more sources.
**Do:**
- Inspect Scheduler -> Job -> DB run path and operational logs.
- Confirm logs contain counts/request IDs but no raw secrets/prompts.
- Document recovery steps for failed job.
- Update weekly gate: first vertical slice + scheduled update must be GO before domain expansion.
**Verify:** One source update path is repeatable and recoverable from a failed run.
**Deliverable:** Freshness gate + recovery note.
**Dependency / fallback:** Depends on Will/Carmen cloud changes. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU has a proven scheduled, change-aware update path rather than a one-time index.

## Day 9 — Sunday, 13 September 2026 — 5h/person
**Phase:** SCHOLARSHIPS DOMAIN
**Shared objective:** Add structured scholarship ingestion, filtering and the 9-card Featured resource page.

### Qasim - Cross-repo / GCP / release
**Goal:** Integrate scholarship privacy/ranking rules and run golden cases.
**Do:**
- Review that filtering uses current-session answers only; no persistent student profile.
- Test 9-card ranking, missing deadlines, open/closed status and source links.
- Run international-undergraduate + postgraduate + broad clarification cases.
- Merge only after UI/retrieval/data agree on field names.
**Verify:** Scholarship vertical slice passes ranking + clarification + provenance tests.
**Deliverable:** Scholarship domain gate + issues for gaps.
**Dependency / fallback:** Coordinates three repo implementations. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Students can browse current Featured scholarships and ask filtered scholarship questions without persistent profiling.

## Day 10 — Monday, 14 September 2026 — 5h/person
**Phase:** JOBS DOMAIN
**Shared objective:** Add current ANU jobs with deterministic closing-date logic and chat retrieval.

### Qasim - Cross-repo / GCP / release
**Goal:** Run jobs temporal/source regression and deployed smoke.
**Do:**
- Validate Canberra date handling near closing boundary.
- Check panel, resource page and chat source links.
- Run one scheduled jobs ingestion in staging and inspect counts.
- Capture defects as P0/P1/P2 before moving on.
**Verify:** Current Jobs behaves correctly on staging and no expired role is shown as current.
**Deliverable:** Jobs domain gate + staging evidence.
**Dependency / fallback:** Depends on all jobs changes. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU can deterministically surface current jobs and answer job questions using fresh official data.

## Day 11 — Tuesday, 15 September 2026 — 5h/person
**Phase:** ACCOMMODATION + SUPPORT
**Shared objective:** Add two lower-volatility domains with strict claims boundaries.

### Qasim - Cross-repo / GCP / release
**Goal:** Review sensitive-domain wording, authority and release tests.
**Do:**
- Check support source authority: official ANU primary where available, ANUSA supplementary/approved for student assistance.
- Run accommodation no-vacancy/no-guaranteed-rate tests.
- Run support mental-health/financial/academic assistance golden questions.
- Deploy bounded domain data to staging and verify source links.
**Verify:** All sensitive-domain golden cases have valid routing and no unsupported high-stakes claim.
**Deliverable:** Accommodation/Support domain gate.
**Dependency / fallback:** Coordinates authority/safety review. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Accommodation and Support have real resource pages and grounded chat coverage without overclaiming.

## Day 12 — Wednesday, 16 September 2026 — 5h/person
**Phase:** EVENTS RELEASE SOURCE
**Shared objective:** Ship Events using an approved source while keeping Rubric optional and permission-gated.

### Qasim - Cross-repo / GCP / release
**Goal:** Close Rubric investigation operationally and test fallback.
**Do:**
- Record Slack/GDG request for approved Rubric API/feed/integration status.
- Mark official ANU Events as release source regardless of Rubric response.
- Run temporal golden tests and source-link validation.
- If approval arrives, schedule bounded integration later; do not derail current critical path.
**Verify:** Events domain is release-ready without Rubric and Rubric is tracked as a non-blocking decision.
**Deliverable:** Events gate + Rubric decision issue.
**Dependency / fallback:** Owns permission/fallback decision. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Upcoming Events works from an approved source; Rubric cannot block the stakeholder demo or release.

## Day 13 — Thursday, 17 September 2026 — 5h/person
**Phase:** CONVERSATION + MOBILE + DEMO STABILISATION
**Shared objective:** Make the six-domain baseline feel coherent as one assistant and freeze tomorrow’s demo scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Run full cross-repo regression and freeze stakeholder-demo scope.
**Do:**
- Run golden smoke set across six domains + conversation + mobile.
- Run secret/dependency checks and inspect production logs.
- Create demo script, fallback screenshots/data and tomorrow’s deployment checklist.
- Mark non-demo work as post-presentation; stop pulling new features into the demo branch.
**Verify:** Demo branch has a written GO / GO WITH CARRY-OVER / BLOCKED decision and known issues list.
**Deliverable:** Stakeholder demo release candidate + rehearsal checklist.
**Dependency / fallback:** Coordinates all owners. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: One deployed, responsive six-domain AskANU baseline is stable enough to rehearse for stakeholders.

## Day 14 — Friday, 18 September 2026 — 5h/person
**Phase:** STAKEHOLDER PRESENTATION
**Shared objective:** Present a stable, real AskANU slice and convert feedback into actionable post-demo work.

### Qasim - Cross-repo / GCP / release
**Goal:** Own the stakeholder release, presentation and feedback triage.
**Do:**
- Run final end-to-end smoke and choose stable deployment revision.
- Lead rehearsal and presentation to ANU GDG stakeholders.
- Capture feedback verbatim enough to distinguish requirement change from preference.
- After meeting, create P0/P1/P2 issues and publish GO / carry-over status for Sep 19 onward.
**Verify:** Presentation completed; feedback is recorded, prioritised and mapped to owners.
**Deliverable:** Stakeholder feedback log + post-demo priority board.
**Dependency / fallback:** Final authority on demo scope today. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: A stable AskANU is demonstrated to ANU GDG and the remaining schedule is updated from real feedback.

## Day 15 — Saturday, 19 September 2026 — 1h/person
**Phase:** POST-DEMO TRIAGE
**Shared objective:** Convert stakeholder feedback into a realistic remaining plan without immediately expanding scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Re-baseline V3 after actual stakeholder result.
**Do:**
- Mark completed/carry-over work.
- Prioritise P0/P1/P2 and protect feature-freeze date.
- If necessary, flag that V4 should be generated from actual status.
**Verify:** Remaining board fits available hours and critical path.
**Deliverable:** Updated post-demo board + carry-over decision.
**Dependency / fallback:** Coordinates all feedback. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Every stakeholder comment is triaged; tomorrow starts from actual status, not the old assumption.

## Day 16 — Sunday, 20 September 2026 — 1h/person
**Phase:** TOP DEFECT FIX
**Shared objective:** Use the one-hour window for one tested slice per person, not a new feature.

### Qasim - Cross-repo / GCP / release
**Goal:** Integrate only completed fixes and run a 10-minute smoke.
**Do:**
- Review the three diffs for contract drift.
- Merge safe fixes and record carry-over.
**Verify:** Smoke passes or blocker remains clearly assigned.
**Deliverable:** Integration note + updated board.
**Dependency / fallback:** Do not create new scope. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: The most important post-demo defects have either a tested fix or a reproducible blocker.

## Day 17 — Monday, 21 September 2026 — 1h/person
**Phase:** SOURCE COMPLETENESS AUDIT
**Shared objective:** Find missing evidence before hardening the model around incomplete data.

### Qasim - Cross-repo / GCP / release
**Goal:** Prioritise coverage fixes before model/UI polish.
**Do:**
- Combine three audits.
- Create P0/P1 coverage issues and assign dates.
**Verify:** No known source gap is disguised as an LLM problem.
**Deliverable:** Coverage gate update.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: The team knows exactly which remaining failures are evidence gaps versus retrieval/UI defects.

## Day 18 — Tuesday, 22 September 2026 — 1h/person
**Phase:** MOBILE + ACCESSIBILITY
**Shared objective:** Make the confirmed responsive UI usable, not merely visually similar.

### Qasim - Cross-repo / GCP / release
**Goal:** Run one desktop + one mobile end-to-end smoke after merge.
**Do:**
- Review accessibility defects by severity.
- Record deferred cosmetic items separately.
**Verify:** Critical mobile flow passes.
**Deliverable:** Mobile gate update.
**Dependency / fallback:** Coordinates merge. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU works through the core chat/resource flow on common mobile widths with keyboard-accessible controls.

## Day 19 — Wednesday, 23 September 2026 — 1h/person
**Phase:** SECURITY + PRIVACY
**Shared objective:** Close concrete security/privacy gaps before feature freeze.

### Qasim - Cross-repo / GCP / release
**Goal:** Audit IAM/logging/secrets/privacy release gate.
**Do:**
- Check runtime service roles, Secret Manager use and repo secret scan.
- Confirm normal logs exclude raw prompts/history; record unresolved ANU privacy/governance question.
**Verify:** Security checklist has owner for every unresolved item.
**Deliverable:** Security/privacy gate report.
**Dependency / fallback:** Owns cross-repo policy. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Release security/privacy controls are tested and remaining governance questions are explicit.

## Day 20 — Thursday, 24 September 2026 — 1h/person
**Phase:** INGESTION FAILURE + RECOVERY
**Shared objective:** Prove source failures cannot silently corrupt the live index.

### Qasim - Cross-repo / GCP / release
**Goal:** Run recovery drill and document exact operator steps.
**Do:**
- Trigger failed job scenario in staging.
- Verify logs/alert path and successful rerun recovery.
**Verify:** A teammate can follow written recovery steps.
**Deliverable:** Recovery runbook update.
**Dependency / fallback:** Coordinates GCP job. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: One failed source run can be detected, contained and recovered without losing last-known-good data.

## Day 21 — Friday, 25 September 2026 — 1h/person
**Phase:** CONVERSATION EDGE CASES
**Shared objective:** Finish the core session-context behaviours before freeze.

### Qasim - Cross-repo / GCP / release
**Goal:** Run conversation regression and decide whether bounded multi-question remains optional.
**Do:**
- Review failures/capacity.
- Keep multi-question feature flag off if core flows are not fully stable.
**Verify:** Core session context has release decision.
**Deliverable:** Conversation gate.
**Dependency / fallback:** Owns scope choice. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Current-session follow-ups and clarification are reliable enough for release; optional batching cannot jeopardise them.

## Day 22 — Saturday, 26 September 2026 — 1h/person
**Phase:** SIX-DOMAIN REGRESSION
**Shared objective:** Run the whole product as a product, not as six separate demos.

### Qasim - Cross-repo / GCP / release
**Goal:** Create pre-freeze defect list ordered P0/P1/P2.
**Do:**
- Combine regression results.
- Only P0/P1 can enter the 4h catch-up/freeze window.
**Verify:** Defect list fits remaining capacity.
**Deliverable:** Pre-freeze board.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: The team has a single pre-freeze defect list based on a real six-domain regression run.

## Day 23 — Sunday, 27 September 2026 — 4h/person
**Phase:** 4-HOUR CATCH-UP + INTEGRATION
**Shared objective:** Use the only expanded late-phase day to close critical carry-over before feature freeze.

### Qasim - Cross-repo / GCP / release
**Goal:** Run integration war room and decide freeze readiness.
**Do:**
- Review/merge only P0/P1 fixes.
- Run end-to-end staging regression and cost/security smoke.
- If Rubric approval arrived, integrate only if bounded and does not threaten freeze; otherwise defer.
- Publish `READY FOR FREEZE` or explicit blocker list.
**Verify:** All critical-path blockers have owner/decision and staging is reproducible.
**Deliverable:** Freeze-readiness report.
**Dependency / fallback:** 4h cross-repo coordination. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Critical carry-over is closed or explicitly accepted before tomorrow’s feature freeze.

## Day 24 — Monday, 28 September 2026 — 1h/person
**Phase:** FEATURE FREEZE
**Shared objective:** Stop feature growth and lock the release candidate behaviour.

### Qasim - Cross-repo / GCP / release
**Goal:** Declare feature freeze and protect release branches/tags.
**Do:**
- Publish freeze rules and P0/P1-only merge criteria.
- Snapshot deployment/config/source versions and known issues.
**Verify:** Team agrees what can still change.
**Deliverable:** Feature-freeze declaration + RC version.
**Dependency / fallback:** Owns release governance. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU enters bug-fix-only mode with a documented release candidate and known issues.

## Day 25 — Tuesday, 29 September 2026 — 1h/person
**Phase:** CLEAN CLONE + REPRODUCIBILITY
**Shared objective:** Prove the project works from repositories and docs, not only from current laptops.

### Qasim - Cross-repo / GCP / release
**Goal:** Perform cross-repo clean-clone checklist and update setup docs.
**Do:**
- Collect failures from all owners.
- Fix only docs/config required for reproducibility.
**Verify:** A fresh teammate can follow setup docs.
**Deliverable:** Reproducibility gate report.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: The three repos can be reproduced from clean clones using documented configuration.

## Day 26 — Wednesday, 30 September 2026 — 1h/person
**Phase:** SECURITY + DEPENDENCY RELEASE SCAN
**Shared objective:** Run final automated/manual security checks before rehearsal.

### Qasim - Cross-repo / GCP / release
**Goal:** Consolidate security/privacy release decision.
**Do:**
- Review IAM/logging/secret scans and unresolved governance note.
- Create explicit accept/fix/defer record for each issue.
**Verify:** No hidden security blocker remains.
**Deliverable:** Security release gate.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Release candidate has a documented security/dependency/privacy status with no unknown critical blocker.

## Day 27 — Thursday, 01 October 2026 — 1h/person
**Phase:** DEPLOYMENT + RECOVERY REHEARSAL
**Shared objective:** Prove the team can deploy, smoke-test and recover before final day.

### Qasim - Cross-repo / GCP / release
**Goal:** Lead full deployment/recovery rehearsal and record timings.
**Do:**
- Follow DEPLOYMENT/runbook as written.
- Record any undocumented manual step and fix docs.
**Verify:** Another team member could repeat rollout.
**Deliverable:** Deployment rehearsal gate.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: The team can deploy the release candidate and recover core services using documented steps.

## Day 28 — Friday, 02 October 2026 — 1h/person
**Phase:** FINAL REGRESSION + DEMO PREP
**Shared objective:** Finish only release blockers and prepare a boring, repeatable final demo.

### Qasim - Cross-repo / GCP / release
**Goal:** Run full demo rehearsal and final release checklist.
**Do:**
- Time the demo and define fallback path.
- Confirm tags/known issues/release notes/owners for tomorrow.
**Verify:** Checklist is ready with no unowned blocker.
**Deliverable:** Final rehearsal + release checklist.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: Release candidate, data and demo are finalised; only emergency fixes remain for Oct 3.

## Day 29 — Saturday, 03 October 2026 — 1h/person
**Phase:** FINAL RELEASE
**Shared objective:** Release AskANU, run smoke tests, and leave a reproducible handover.

### Qasim - Cross-repo / GCP / release
**Goal:** Own release tag, smoke sign-off and project handover.
**Do:**
- Run final cross-repo smoke and mark release GO/NO-GO.
- Create final tags/releases/known-issues note and backup demo link/assets.
- Record actual status so the next V4/V5/V6 can be generated from reality, not this schedule.
**Verify:** Release status is explicit and all artifacts/repos are traceable.
**Deliverable:** AskANU final release/handover record.
**Dependency / fallback:** Final release authority. If blocked: work only on the listed fallback or tests; do not invent new scope.

**Team integration check:** END-OF-DAY INTEGRATION CHECK: AskANU is released with traceable versions, healthy sources, passing core flows and a clear known-issues/handover record.
