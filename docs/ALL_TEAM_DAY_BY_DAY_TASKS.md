# AskANU V3 — Day-by-Day Tasks

**Source of truth:** AskANU Project Execution Plan V3.

This file mirrors the 29 daily execution pages in V3 so each teammate can open the repo and immediately see today's work.

**Rule:** If a critical-path task carries over, it outranks the next scheduled feature. Do not silently invent new scope.

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

### Ben - App repo
**Goal:** Create the confirmed desktop/mobile UI shell before styling details.
**Do:**
- Create React app structure and shared theme/design-token file.
- Build desktop layout: chat primary/left; navigation/resources right.
- Build empty chat state with input + `Try asking`; implement `Clear Chat` state reset in mock form.
- Create responsive drawer breakpoint for mobile and placeholder Quick Links / Events / Jobs cards.
**Verify:** Check desktop and 360/390/430px widths; no horizontal scroll; suggestions visible only in empty state.
**Deliverable:** PR: App bootstrap with responsive shell and mock states.
**Dependency / fallback:** Consumes API/UX contract; does not need backend. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Create a safe scraper framework and source registry.
**Do:**
- Create Python source modules for courses, scholarships, jobs, accommodation, support, events.
- Add common fetch/parse/normalise interfaces and ingestion-run model placeholders.
- Add approved source registry from V3; mark Rubric as `PENDING_APPROVAL` and non-production.
- Save initial public HTML fixtures for one course/program and one scholarship page; no mass crawling.
**Verify:** Parser framework tests run; no collector can target a source missing from registry.
**Deliverable:** PR: Scraper bootstrap + source registry + representative fixtures.
**Dependency / fallback:** Uses V3 source list. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: All three repos run locally, contract docs match, and each owner has a mergeable Day 1 PR.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Build active-conversation rendering and source cards against mock contract responses.
**Do:**
- Remove `Try asking` automatically after the first user message.
- Render user turn, AskANU answer, timestamp/metadata only if useful, and source cards with external-link affordance.
- Build `ok`, `insufficient_evidence`, `off_topic`, loading and safe error visual states.
- Keep Quick Links / Upcoming Events / Current Jobs visible in right resource area.
**Verify:** Use mocked contract fixtures; source URLs are clickable; `Clear Chat` restores empty state.
**Deliverable:** PR: active chat + source cards + core response states.
**Dependency / fallback:** Uses API_CONTRACT; no real backend required. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Parse ANU Programs & Courses into the first real normalized records.
**Do:**
- Inspect Programs & Courses page structure for course and program entities.
- Implement parser for core identifiers, academic year, title, career/units/delivery and canonical URL.
- Extend course parsing for sessions/prerequisites/assumed knowledge where present.
- Create deterministic `content_hash` and stable IDs; add BACCT + one computing-course fixtures/tests.
**Verify:** Re-parsing the same fixture produces the same IDs/hash and no invented fields.
**Deliverable:** PR: first courses/programs parser + normalized fixtures.
**Dependency / fallback:** Source: programsandcourses.anu.edu.au only. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: One real ANU course/program page can be normalized into a shared record shape and rendered as a mocked grounded answer.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Connect the React chat to the real local App/RAG path.
**Do:**
- Create API client using `VITE_API_BASE_URL`/App integration boundary.
- Wire send/loading/response/error states to the real `/api/v1/ask` response.
- Keep mock fixtures available for UI tests, but do not hardcode answer content in production path.
- Verify source card opens the original ANU page.
**Verify:** Local browser asks COMP1110 and displays real backend response + source card.
**Deliverable:** PR: real local API integration.
**Dependency / fallback:** Needs Carmen endpoint reachable; should not wait for Gemini. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Perform a live single-record fetch and safe normalization.
**Do:**
- Fetch one approved course/program page through common fetcher.
- Parse and validate required identity/year/URL fields.
- Write normalized record + ingestion-run output to local development storage/DB handoff.
- Add fetch failure and changed-content tests.
**Verify:** Live fetch result matches fixture expectations; repeated run is idempotent.
**Deliverable:** PR: first live approved-source collector.
**Dependency / fallback:** Needs local DB handoff agreed with Qasim/Carmen. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: A student can ask one real course question locally and get a grounded answer with an official ANU source link.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Polish grounded-answer states without changing information hierarchy.
**Do:**
- Render grounded response with readable paragraphs/lists and source block.
- Make insufficient-evidence/off-topic states clear but compact.
- Ensure user content and answer text are rendered safely rather than as executable HTML.
- Confirm empty-state suggestions still disappear after first question.
**Verify:** Mock and real responses all render without layout shift or unsafe HTML execution.
**Deliverable:** PR: grounded answer presentation + safe rendering tests.
**Dependency / fallback:** Consumes validated API responses. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Expand course parsing to fields needed for natural questions.
**Do:**
- Capture prerequisites/corequisites/incompatibilities/assumed knowledge when present.
- Capture sessions/offerings and relevant enrolment/census dates when exposed.
- Preserve academic year and canonical URL for every record.
- Add malformed/missing-field fixtures and ensure missing fields stay null/empty, not invented.
**Verify:** Fixtures cover normal + missing-field pages and pass normalization tests.
**Deliverable:** PR: richer course schema parsing.
**Dependency / fallback:** Coordinate field names with DATA_SCHEMA. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: AskANU can use Gemini for a real course answer while preserving evidence, source provenance and abstention.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Build the Courses resource page and finalise empty-state interaction.
**Do:**
- Create Courses information page with official search/navigation links and useful current info placeholders.
- Add call-to-action that returns user to the single AskANU chat for a course question.
- Refine empty-state suggestion cards and make them keyboard/touch accessible.
- Keep theme tokens central so future visual changes do not rewrite components.
**Verify:** Courses page is a resource hub, not another chat; suggestion cards work by keyboard and touch.
**Deliverable:** PR: Courses page + final empty-state component.
**Dependency / fallback:** Uses approved Programs & Courses links. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Broaden Programs & Courses collection pattern.
**Do:**
- Handle catalogue/search result discovery for courses, programs, majors, minors and specialisations.
- Preserve academic year and entity type in IDs/metadata.
- Add sanity counts and duplicate detection before any bulk DB update.
- Run a bounded sample across multiple entity types; do not mass-ingest until sanity checks pass.
**Verify:** Sample contains multiple entity types with stable IDs and no duplicate canonical entities.
**Deliverable:** PR: catalogue discovery + bounded multi-entity tests.
**Dependency / fallback:** Must obey source load/rate policy. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: Courses are no longer a one-record demo: the team has a tested reusable discovery, storage, retrieval and UI pattern.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Make App production-buildable and prepare Firebase/App service routing.
**Do:**
- Create production build config and environment-based API base URL.
- Add thin App server/proxy only where needed by the architecture; keep browser free of DB/model secrets.
- Prepare Firebase Hosting config and responsive fallback routes.
- Verify local production build.
**Verify:** Production build succeeds and no secret is bundled into frontend assets.
**Deliverable:** PR: deployable App build + routing config.
**Dependency / fallback:** Needs Qasim deployment target. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Make scraper runnable as a job rather than a continuously running web server.
**Do:**
- Create one-shot job entrypoint with source selection/dry-run mode.
- Return non-zero exit on ingestion failure and structured run summary on success.
- Use environment config for DB/cloud values; no secret files.
- Run local job against bounded course sample.
**Verify:** Job exits cleanly on success and safely on simulated fetch failure.
**Deliverable:** PR: Cloud Run Job-ready scraper entrypoint.
**Dependency / fallback:** Needs deployment/env contract. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: At least a health-level App -> RAG deployment exists in the real GCP environment.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Point deployed frontend/App path at deployed RAG and validate origin/CORS behaviour.
**Do:**
- Deploy React build to Firebase Hosting.
- Route API through intended App service boundary.
- Test loading/error/source-card behaviour on deployed URL.
- Test at least one desktop and one mobile browser width.
**Verify:** Public demo URL can ask the real course question without direct browser access to RAG DB secrets.
**Deliverable:** Deployed App/Firebase URL + smoke screenshots.
**Dependency / fallback:** Needs Carmen deployed endpoint + Qasim routing. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Load first safe course ingestion run into shared cloud DB.
**Do:**
- Run bounded collector job against approved course source.
- Write ingestion_run counts and normalized record with canonical URL/hash.
- Verify rerun is idempotent and unchanged record is not unnecessarily re-embedded.
- Record any source-rate/parser issues before expanding scope.
**Verify:** Two runs show stable record ID/hash and safe ingestion counts.
**Deliverable:** Cloud ingestion evidence + test logs.
**Dependency / fallback:** Needs Qasim DB/job identity. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: A real student-facing deployed URL completes the first source-to-answer vertical slice.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Add lightweight freshness/error presentation only where useful.
**Do:**
- Ensure stale/unavailable summary endpoints can show a safe UI state without inventing data.
- Complete Courses resource page source links on deployed build.
- Keep UI uncluttered; do not expose vector scores/internal states to students.
- Run responsive smoke after deployment changes.
**Verify:** UI degrades safely when summary data is unavailable and does not expose internals.
**Deliverable:** PR: safe freshness/error UX.
**Dependency / fallback:** Consumes API status only. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Deploy the first daily scheduled collector with last-known-good protection.
**Do:**
- Create Cloud Run Job deployment for courses and Cloud Scheduler daily trigger.
- Implement compare-by-content_hash and `last_seen_at`.
- Add suspicious many-records-to-zero sanity guard and parser-failure rollback/keep-current behaviour.
- Trigger job manually once and collect ingestion-run evidence.
**Verify:** Scheduled job exists; unchanged rerun does not re-embed; simulated zero/failure does not wipe data.
**Deliverable:** Scheduled update proof + run logs.
**Dependency / fallback:** Needs Qasim Scheduler/job IAM. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: AskANU has a proven scheduled, change-aware update path rather than a one-time index.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Build Scholarships resource page exactly to V3 rules.
**Do:**
- Show up to 9 open Featured scholarships from backend data.
- If fewer than 9 Featured are open, fill by nearest known deadline.
- Each card links to official scholarship page; label status/application requirement clearly.
- Add `Ask about scholarships` action into the single chat; no separate scholarship bot/profile.
**Verify:** Resource page never labels items “most popular”; closed items do not appear as current.
**Deliverable:** PR: Scholarships page + tests.
**Dependency / fallback:** Needs deterministic scholarship data endpoint/mock. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Build ANU scholarship listing + detail collector.
**Do:**
- Discover scholarship listing/detail URLs from approved ANU finder.
- Collect featured flag, status, application requirement, study stage/type/level/area, value, selection basis, dates, eligibility and URL.
- Preserve missing deadline as unknown; never invent date.
- Add fixtures for open Featured, open non-Featured and closed scholarship.
**Verify:** Parser tests cover Featured/open/closed and produce stable canonical records.
**Deliverable:** PR: scholarship collector + fixtures/tests.
**Dependency / fallback:** Source: study.anu.edu.au scholarships only. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: Students can browse current Featured scholarships and ask filtered scholarship questions without persistent profiling.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Build Jobs resource page + Current Jobs panel.
**Do:**
- Render current roles with title, type/location/closing date where available.
- Default panel shows 5 and `View all` routes to resource page/official listings.
- Keep all job links canonical and external.
- Test empty/unavailable state without fake jobs.
**Verify:** UI order matches backend deterministic order and all links are official.
**Deliverable:** PR: Jobs page/panel + tests.
**Dependency / fallback:** Consumes jobs endpoint. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Build ANU jobs search/list/detail collector.
**Do:**
- Collect title, category, employment type, location, classification, closing date, summary and canonical URL.
- Normalize closing date in Canberra-aware representation.
- Mark current/closed based on explicit source data/date rules; do not invent status.
- Add fixtures/tests for open dated, open undated and expired/closed cases.
**Verify:** Collector produces records that deterministic endpoint can sort correctly.
**Deliverable:** PR: jobs collector + fixtures/tests.
**Dependency / fallback:** Source: jobs.anu.edu.au/jobs/search. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: AskANU can deterministically surface current jobs and answer job questions using fresh official data.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Build Accommodation and Support resource pages.
**Do:**
- Accommodation: residence/resources cards, application link, official source links.
- Support: clear categories and direct contact/action links from approved sources.
- Make mental-health/support actions easy to find on mobile without alarmist copy.
- Do not add profile/login or claim live availability.
**Verify:** Pages are resource hubs with valid official/ANUSA links and accessible mobile layout.
**Deliverable:** PR: Accommodation + Support pages.
**Dependency / fallback:** Needs approved source links/data. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Build ANU Accommodation + ANUSA Student Assistance collectors.
**Do:**
- Collect residence name, catering/resident type, advertised rate text, description, application status/year and canonical page.
- Do not scrape authenticated StarRez application content.
- Collect ANUSA assistance categories, service descriptions, contact/action URLs and only explicit hours.
- Add fixtures/tests for missing rate/hours and link validation.
**Verify:** Collectors preserve source wording for sensitive fields and never infer vacancy/hours.
**Deliverable:** PR: accommodation + support collectors.
**Dependency / fallback:** Sources: study.anu.edu.au accommodation + anusa.com.au student-assistance. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: Accommodation and Support have real resource pages and grounded chat coverage without overclaiming.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Build Events resource page + Upcoming Events panel.
**Do:**
- Show 5 upcoming events in panel, `View all` for resource page.
- Cards show title/date/time/organiser/location when present and link to canonical source.
- Do not imply Rubric coverage unless approved integration is active.
- Test empty/stale state and mobile stacking.
**Verify:** Panel/page work with official ANU source alone and remain valid if Rubric never arrives.
**Deliverable:** PR: Events page/panel + tests.
**Dependency / fallback:** Consumes approved events endpoint. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Implement official ANU Events collector and isolate Rubric work.
**Do:**
- Build approved ANU Events/calendar collector with event ID/title/start/end/venue/organiser/description/URL.
- Add temporal/status normalization and daily polling fixtures/tests.
- Create Rubric adapter interface/feature flag only; no calls to undocumented `getUnifiedSearch`.
- Document known Rubric schema discovery for future approved integration without storing tokens/cookies.
**Verify:** Events collector produces current/upcoming records; Rubric path is disabled by default.
**Deliverable:** PR: ANU Events collector + Rubric placeholder/documentation.
**Dependency / fallback:** Rubric use requires explicit approval. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: Upcoming Events works from an approved source; Rubric cannot block the stakeholder demo or release.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Finish mobile interaction and clarification UI.
**Do:**
- Render selectable clarification options and `both` where allowed.
- Complete mobile drawer with Clear Chat/resource navigation/Quick Links.
- Test 360/390/430px, keyboard focus, touch targets and chat input with mobile viewport.
- Run full UI regression across empty chat and active conversation.
**Verify:** No horizontal scroll; clarification and Clear Chat work on desktop/mobile.
**Deliverable:** PR: mobile + clarification final demo baseline.
**Dependency / fallback:** Needs Carmen clarification responses. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Run full daily poll and harden parser failures across all six domains.
**Do:**
- Execute bounded staging ingestion for Courses, Scholarships, Jobs, Accommodation, Support and Events.
- Verify run counts, canonical URLs, hashes and last-known-good behaviour.
- Fix only release-blocking parser/data issues today.
- Produce one source-health summary for demo morning refresh.
**Verify:** Every required domain has at least baseline approved records or a documented blocker/fallback.
**Deliverable:** Six-domain ingestion report + P0 data issues.
**Dependency / fallback:** All approved collectors must exist. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: One deployed, responsive six-domain AskANU baseline is stable enough to rehearse for stakeholders.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Prepare and present the confirmed UI on desktop and mobile.
**Do:**
- Run browser/mobile smoke and verify Clear Chat, sources, resource pages, Events/Jobs panels.
- Fix only P0 visual/interaction defect before presentation.
- Prepare one desktop and one mobile fallback screenshot.
- After demo, convert UI feedback into concrete issues rather than editing live ad hoc.
**Verify:** Demo UI matches confirmed interaction model and fallback screenshots are available.
**Deliverable:** UI demo checklist + feedback issues.
**Dependency / fallback:** Uses frozen demo build. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Refresh source data and verify provenance before demo.
**Do:**
- Run final approved-source daily ingestion with sanity checks.
- Validate representative source URLs for all six domains.
- Keep Rubric disabled unless explicit approval is already documented.
- After demo, classify data/source feedback and parser gaps.
**Verify:** Freshness/source-health report is green or documented; no suspicious ingestion overwrote current data.
**Deliverable:** Pre-demo source report + feedback issues.
**Dependency / fallback:** Needs staging/prod job access. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: A stable AskANU is demonstrated to ANU GDG and the remaining schedule is updated from real feedback.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Review UI feedback and identify one highest-value interaction fix.
**Do:**
- Map each UI comment to confirmed UX vs optional styling.
- If no blocker, choose the most important accessibility/responsive defect.
**Verify:** No preference is mislabelled as a mandatory requirement.
**Deliverable:** One prioritised App issue.
**Dependency / fallback:** Uses stakeholder log. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Review source/data feedback and identify one highest-risk coverage gap.
**Do:**
- Check source health/counts since demo.
- Choose one parser/field gap that affects real answers.
**Verify:** Gap has affected query/source example.
**Deliverable:** One prioritised scraper issue.
**Dependency / fallback:** Uses source-health report. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Re-baseline V3 after actual stakeholder result.
**Do:**
- Mark completed/carry-over work.
- Prioritise P0/P1/P2 and protect feature-freeze date.
- If necessary, flag that V4 should be generated from actual status.
**Verify:** Remaining board fits available hours and critical path.
**Deliverable:** Updated post-demo board + carry-over decision.
**Dependency / fallback:** Coordinates all feedback. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: Every stakeholder comment is triaged; tomorrow starts from actual status, not the old assumption.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Fix the highest-priority App defect from Sep 19.
**Do:**
- Implement one bounded UI/accessibility correction.
- Test affected desktop/mobile state.
**Verify:** Issue acceptance criteria pass.
**Deliverable:** Small App PR.
**Dependency / fallback:** If blocked, add component test/reproduction. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Fix the highest-priority parser/data defect from Sep 19.
**Do:**
- Adjust one parser/normalizer rule.
- Add/repair fixture test.
**Verify:** Fixture reproduces old failure and now passes.
**Deliverable:** Small scraper PR.
**Dependency / fallback:** If blocked, capture new fixture + diagnosis. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Integrate only completed fixes and run a 10-minute smoke.
**Do:**
- Review the three diffs for contract drift.
- Merge safe fixes and record carry-over.
**Verify:** Smoke passes or blocker remains clearly assigned.
**Deliverable:** Integration note + updated board.
**Dependency / fallback:** Do not create new scope. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: The most important post-demo defects have either a tested fix or a reproducible blocker.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Audit resource pages for missing/incorrect links or stale labels.
**Do:**
- Open representative links for all six pages.
- Record only factual/UX gaps, not cosmetic wishes.
**Verify:** All visible links checked or issue created.
**Deliverable:** UI source-link audit.
**Dependency / fallback:** Uses current API data. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Audit collector coverage/counts and canonical URLs.
**Do:**
- Compare expected entity types/fields to actual records.
- Flag parsers producing suspicious missing fields.
**Verify:** Coverage gaps have source example + parser owner.
**Deliverable:** Scraper coverage report.
**Dependency / fallback:** Uses ingestion_runs. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Prioritise coverage fixes before model/UI polish.
**Do:**
- Combine three audits.
- Create P0/P1 coverage issues and assign dates.
**Verify:** No known source gap is disguised as an LLM problem.
**Deliverable:** Coverage gate update.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: The team knows exactly which remaining failures are evidence gaps versus retrieval/UI defects.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Run focused accessibility/mobile pass.
**Do:**
- Keyboard through Clear Chat, nav drawer, suggestions, clarification and source links.
- Check focus visibility, touch targets, labels and 360–430px no-overflow.
**Verify:** No blocking keyboard/viewport issue in tested path.
**Deliverable:** Accessibility/mobile PR or PASS report.
**Dependency / fallback:** Primary owner today. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Validate titles/URLs/text encoding for mobile resource cards.
**Do:**
- Check long titles and special characters from each source.
- Fix normalization only if source text breaks display/links.
**Verify:** Representative records render without broken text/URL.
**Deliverable:** Data display-compatibility test.
**Dependency / fallback:** Uses fixtures. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Run one desktop + one mobile end-to-end smoke after merge.
**Do:**
- Review accessibility defects by severity.
- Record deferred cosmetic items separately.
**Verify:** Critical mobile flow passes.
**Deliverable:** Mobile gate update.
**Dependency / fallback:** Coordinates merge. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: AskANU works through the core chat/resource flow on common mobile widths with keyboard-accessible controls.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Verify safe rendering and external-link handling.
**Do:**
- Test user/model strings containing HTML/script-like content.
- Ensure links use safe target/rel behaviour and no raw HTML execution.
**Verify:** Malicious strings display as text, not code.
**Deliverable:** App security PR/PASS.
**Dependency / fallback:** Frontend only. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Verify scraped content is treated as data, not instruction.
**Do:**
- Add malicious-source fixture if missing.
- Ensure sanitizer/normalizer retains evidence text safely without executing anything.
**Verify:** Fixture cannot alter scraper control flow.
**Deliverable:** Scraper security test.
**Dependency / fallback:** No unapproved source. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Audit IAM/logging/secrets/privacy release gate.
**Do:**
- Check runtime service roles, Secret Manager use and repo secret scan.
- Confirm normal logs exclude raw prompts/history; record unresolved ANU privacy/governance question.
**Verify:** Security checklist has owner for every unresolved item.
**Deliverable:** Security/privacy gate report.
**Dependency / fallback:** Owns cross-repo policy. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: Release security/privacy controls are tested and remaining governance questions are explicit.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Make stale/unavailable data errors understandable without exposing internals.
**Do:**
- Test Events/Jobs unavailable response.
- Use concise fallback copy and preserve chat usability.
**Verify:** UI degrades gracefully with no fake data.
**Deliverable:** App failure-state PR/PASS.
**Dependency / fallback:** Consumes status only. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Run failure drills: timeout, parser failure, suspicious zero.
**Do:**
- Execute or simulate each failure.
- Verify last-known-good survives and run status is failed/visible.
**Verify:** No failure wipes current approved data.
**Deliverable:** Scraper recovery report/PR.
**Dependency / fallback:** Primary owner today. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Run recovery drill and document exact operator steps.
**Do:**
- Trigger failed job scenario in staging.
- Verify logs/alert path and successful rerun recovery.
**Verify:** A teammate can follow written recovery steps.
**Deliverable:** Recovery runbook update.
**Dependency / fallback:** Coordinates GCP job. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: One failed source run can be detected, contained and recovered without losing last-known-good data.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Test clarification interactions end-to-end.
**Do:**
- Test first/second/both/correction/Clear Chat.
- Verify options are accessible on mobile.
**Verify:** UI state always matches backend pending clarification.
**Deliverable:** App conversation test/PASS.
**Dependency / fallback:** Needs Carmen fixtures. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Provide multi-entity/course fixtures needed for ambiguity tests.
**Do:**
- Validate entity IDs/names remain distinct and stable.
- Fix data collision only if reproduced.
**Verify:** Ambiguity tests use realistic records.
**Deliverable:** Fixture/data PR or PASS.
**Dependency / fallback:** No new domain. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Run conversation regression and decide whether bounded multi-question remains optional.
**Do:**
- Review failures/capacity.
- Keep multi-question feature flag off if core flows are not fully stable.
**Verify:** Core session context has release decision.
**Deliverable:** Conversation gate.
**Dependency / fallback:** Owns scope choice. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: Current-session follow-ups and clarification are reliable enough for release; optional batching cannot jeopardise them.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Run complete navigation/resource/chat smoke on desktop and mobile.
**Do:**
- Open each resource page and representative source.
- Check Clear Chat and empty-state suggestions.
**Verify:** All core navigation works.
**Deliverable:** App regression note.
**Dependency / fallback:** Current deployed build. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Run all six collectors in bounded staging mode and inspect counts.
**Do:**
- Check canonical URLs/hashes/last_seen.
- Investigate only suspicious counts/failures.
**Verify:** All required sources have healthy/latest run or documented blocker.
**Deliverable:** Source-health report.
**Dependency / fallback:** Approved sources only. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Create pre-freeze defect list ordered P0/P1/P2.
**Do:**
- Combine regression results.
- Only P0/P1 can enter the 4h catch-up/freeze window.
**Verify:** Defect list fits remaining capacity.
**Deliverable:** Pre-freeze board.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: The team has a single pre-freeze defect list based on a real six-domain regression run.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Close highest-priority UI/mobile P0/P1 items and polish only after tests.
**Do:**
- First 2h: functional/accessibility blockers.
- Next 1h: resource/chat/mobile regression.
- Final 1h: small visual polish only if all blockers are closed.
**Verify:** No UI P0 remains and confirmed UX is intact.
**Deliverable:** App catch-up PRs + screenshots/test report.
**Dependency / fallback:** No layout redesign. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Close highest-priority source/parser P0/P1 items and refresh staging data.
**Do:**
- First 2h: source coverage/parser blocker.
- Next 1h: full ingestion + failure sanity checks.
- Final 1h: source URL validation/report.
**Verify:** Required-domain data is healthy and no suspicious run is unresolved.
**Deliverable:** Scraper catch-up PRs + source report.
**Dependency / fallback:** Rubric only if approved and clearly non-blocking. If blocked: work only on the listed fallback or tests; do not invent new scope.

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

**END-OF-DAY INTEGRATION CHECK: Critical carry-over is closed or explicitly accepted before tomorrow’s feature freeze.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Freeze UI information architecture and component behaviour.
**Do:**
- Run empty/active/mobile/resource smoke.
- Move cosmetic wishes to post-release backlog.
**Verify:** Confirmed UI unchanged and bug list explicit.
**Deliverable:** App freeze note.
**Dependency / fallback:** Bug fixes only. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Freeze production source registry/parser behaviour.
**Do:**
- Run source registry diff and latest ingestion health.
- No new source added without release-blocking reason.
**Verify:** Approved source set is explicit.
**Deliverable:** Scraper freeze note.
**Dependency / fallback:** Bug fixes only. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Declare feature freeze and protect release branches/tags.
**Do:**
- Publish freeze rules and P0/P1-only merge criteria.
- Snapshot deployment/config/source versions and known issues.
**Verify:** Team agrees what can still change.
**Deliverable:** Feature-freeze declaration + RC version.
**Dependency / fallback:** Owns release governance. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: AskANU enters bug-fix-only mode with a documented release candidate and known issues.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Run App install/build/test from clean clone.
**Do:**
- Follow documented environment setup.
- Verify production build and local API config.
**Verify:** App builds without undeclared local dependency.
**Deliverable:** Clean-clone evidence/PR.
**Dependency / fallback:** No feature changes. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Run scraper install + one dry-run collector from clean clone.
**Do:**
- Use approved fixture/live bounded source.
- Verify no local-only file/secret required.
**Verify:** Scraper dry-run works from clean clone.
**Deliverable:** Clean-clone evidence/PR.
**Dependency / fallback:** No feature changes. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Perform cross-repo clean-clone checklist and update setup docs.
**Do:**
- Collect failures from all owners.
- Fix only docs/config required for reproducibility.
**Verify:** A fresh teammate can follow setup docs.
**Deliverable:** Reproducibility gate report.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: The three repos can be reproduced from clean clones using documented configuration.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Run frontend dependency/safe-render/security-header checks.
**Do:**
- Check dependency audit and production bundle for secrets.
- Verify safe external links/rendering.
**Verify:** No secret in bundle and no critical dependency blocker.
**Deliverable:** App security report.
**Dependency / fallback:** Bug fixes only. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Run scraper dependency/secret/source-policy scan.
**Do:**
- Check no unapproved Rubric/internal endpoint code enabled.
- Verify credentials are environment/Secret Manager only.
**Verify:** Production source policy matches V3.
**Deliverable:** Scraper security report.
**Dependency / fallback:** Bug fixes only. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Consolidate security/privacy release decision.
**Do:**
- Review IAM/logging/secret scans and unresolved governance note.
- Create explicit accept/fix/defer record for each issue.
**Verify:** No hidden security blocker remains.
**Deliverable:** Security release gate.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: Release candidate has a documented security/dependency/privacy status with no unknown critical blocker.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Verify Firebase/App deploy and browser recovery path.
**Do:**
- Deploy known RC build.
- Run desktop/mobile smoke after fresh deployment.
**Verify:** Public URL returns correct build and core flow.
**Deliverable:** App deployment evidence.
**Dependency / fallback:** No feature changes. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Verify scheduled scraper job and manual recovery rerun.
**Do:**
- Check latest scheduled run.
- Trigger safe manual run and inspect counts/logs.
**Verify:** Job can be rerun without duplicates/corruption.
**Deliverable:** Scraper recovery evidence.
**Dependency / fallback:** Approved sources only. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Lead full deployment/recovery rehearsal and record timings.
**Do:**
- Follow DEPLOYMENT/runbook as written.
- Record any undocumented manual step and fix docs.
**Verify:** Another team member could repeat rollout.
**Deliverable:** Deployment rehearsal gate.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: The team can deploy the release candidate and recover core services using documented steps.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Run final UI regression and capture fallback screenshots.
**Do:**
- Test confirmed desktop/mobile states.
- Capture current screenshots and verify source/resource links.
**Verify:** Demo can proceed even if network has a temporary issue.
**Deliverable:** Final UI smoke + fallback assets.
**Dependency / fallback:** No new features. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Run final source refresh + URL validation.
**Do:**
- Ingest approved sources with sanity guards.
- Validate representative canonical URLs and freeze source-health report.
**Verify:** No suspicious ingestion/source-link issue.
**Deliverable:** Final source report.
**Dependency / fallback:** No new source. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Run full demo rehearsal and final release checklist.
**Do:**
- Time the demo and define fallback path.
- Confirm tags/known issues/release notes/owners for tomorrow.
**Verify:** Checklist is ready with no unowned blocker.
**Deliverable:** Final rehearsal + release checklist.
**Dependency / fallback:** Cross-repo. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: Release candidate, data and demo are finalised; only emergency fixes remain for Oct 3.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`

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

### Ben - App repo
**Goal:** Verify final public desktop/mobile experience.
**Do:**
- Check Clear Chat, empty suggestions, sources, navigation, Quick Links, Events and Jobs.
- Confirm public build matches RC.
**Verify:** Core user flow passes on desktop/mobile.
**Deliverable:** Final App release check.
**Dependency / fallback:** Emergency fixes only. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Will - Scraper repo
**Goal:** Verify final ingestion/source health.
**Do:**
- Check latest scheduled/manual run status.
- Confirm all six required domains have approved baseline data.
**Verify:** No critical source failure at release.
**Deliverable:** Final scraper/source check.
**Dependency / fallback:** Emergency fixes only. If blocked: work only on the listed fallback or tests; do not invent new scope.

### Qasim - Cross-repo / GCP / release
**Goal:** Own release tag, smoke sign-off and project handover.
**Do:**
- Run final cross-repo smoke and mark release GO/NO-GO.
- Create final tags/releases/known-issues note and backup demo link/assets.
- Record actual status so the next V4/V5/V6 can be generated from reality, not this schedule.
**Verify:** Release status is explicit and all artifacts/repos are traceable.
**Deliverable:** AskANU final release/handover record.
**Dependency / fallback:** Final release authority. If blocked: work only on the listed fallback or tests; do not invent new scope.

**END-OF-DAY INTEGRATION CHECK: AskANU is released with traceable versions, healthy sources, passing core flows and a clear known-issues/handover record.**

`[ ] NOT STARTED   [ ] IN PROGRESS   [ ] BLOCKED   [ ] DONE    |    Actual result: __________    Blocker: __________    Carry-over: __________    PR/commit: __________`
