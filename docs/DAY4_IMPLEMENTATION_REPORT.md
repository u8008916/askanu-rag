# Day 4 final verification report

Date: 2026-09-08. Owner: Carmen. Issue: #9.

**Real updated COMP1110 -> RAG -> Gemini -> HTTP verification passed.**
All 197 automated tests pass (one existing Windows-permission skip).
The only remaining acceptance item is reading Qasim's frozen gate document:
the specified remote branch could not be found after a fresh fetch and direct
remote-ref check. Recommendation: **NOT READY for final commit/push sign-off**
until that exact gate comparison is completed. No commits, pushes, PRs or merges.

## Requested 80-point final report

1. Branch: `carmen/day-4-grounded-gemini`, unchanged.
2. HEAD, freshly fetched `origin/main`, and merge base: `4af8ddacfdb68867cdd006def357080995c3a194` (merged Day 3 PR #8).
3. Git status: 6 modified tracked files, 6 untracked new files; nothing staged or committed. Existing Day 4 work preserved.
4. Modified across Day 4: `.env.example`, `README.md`, `pyproject.toml`, `src/askanu_rag/course_queries.py`, `src/askanu_rag/main.py`, `tests/test_ask_contract.py`. Added: `src/askanu_rag/config.py`, `src/askanu_rag/gemini.py`, `src/askanu_rag/synthesis.py`, `tests/test_gemini_provider.py`, `tests/test_grounded_synthesis.py`, this report. This final recheck changed only README/report facts; no implementation or test changes were necessary.
5. Qasim gate successfully read: **NO**. Successful `git fetch origin` was followed by an unsuccessful remote-branch read and direct fetch; exact errors below.
6. Requested ref/path: `origin/qasim/day4-grounding-security-gate:docs/DAY4_GROUNDING_SECURITY_GATE.md` in the RAG origin. No checkout of Qasim's branch or modification of gate criteria.
7. Additional gate criteria: unknown, not invented. Known user-supplied G1-G7, API consistency, source provenance, secret/config and logging checks verified. Exact gate-specific examples cannot be confirmed without the file.
8. Runtime artifact used: `D:\gdg_project\askanu-scraper\local-data\records\courses__course__COMP1110_2026.json`. Read directly through the existing loader; not copied into RAG or modified.
9. Record ID: `courses:course:COMP1110_2026`.
10. Entity ID: `COMP1110_2026`.
11. Title: `Structured Programming`.
12. Academic year: string `"2026"`, no inference.
13. Canonical URL: `https://programsandcourses.anu.edu.au/2026/course/comp1110`.
14. Stored content hash: `37356e7de031c3abc98fd3f4c1db2bde094f167c480320dfce162abf0e56d408`. Compared/preserved, not recalculated. Record status is `CHANGED`.
15. Prerequisites: `COMP1100 OR COMP1130 OR COMP1730`.
16. Incompatibilities: `COMP1140 or COMP6710 or COMP7710`.
17. Assumed knowledge: `MCOMP students from 2026 onwards must enrol in COMP7710 Programming Fundamentals.` Stored offerings list First and Second Semester, 2026 / In Person.
18. `load_course_program_record_file` -> `CourseProgramRecord`: PASS, full 16-field schema-v1 object validated.
19. Provenance round-trip: PASS, JSON serialization/revalidation preserved the model; returned source fields equal stored fields. No URL reconstruction or hash recalculation.
20. Narrow `CourseProgramRepository([record])`: explicit `find_course_by_code("COMP1110", "2026")` and sole-year lookup without year both returned the same validated record.
21. Actual configured Gemini model: `gemini-3.5-flash-lite`.
22. API key variable: `GEMINI_API_KEY`, loaded by existing Settings from environment/local ignored `.env`.
23. Key exists locally: YES, checked as a boolean only; not displayed, changed or embedded in tests.
24. Interface: `async SynthesisClient.synthesize(context: SynthesisContext) -> str`, returning untrusted JSON. Real adapter: `GeminiSynthesisClient`, official `google-genai` 1.75.0. Tests inject fake clients/SDK stubs/mock HTTP transport; no CI credential dependency.
25. Internal output: exactly `{"answer":"...","supported":true}`. Strict Pydantic validation, required fields, forbidden extras, strict types, answer length bounds, duplicate-key rejection and complete-answer allowlisting. True support flag alone is not proof.
26. Evidence sent on the real path: course code, string academic year, prerequisite string; also the standalone user question encoded separately as untrusted data, plus evidence-derived allowed phrasings. System grounding instructions are separate.
27. Excluded: full record content, title, canonical URL, IDs, hashes, timestamps, incompatibilities, assumed knowledge, offerings, unrelated metadata, history and repository internals. No search/tools or external retrieval by the model.
28. Gemini cannot control public status. Course service and HTTP handlers own it.
29. Gemini cannot control source URL. `_source_from_record` owns all source fields and uses `record.canonical_url` directly.
30. Real supported path: PASS using localhost HTTP -> request validation -> classifier -> exact real-record retrieval -> assembler -> actual Gemini -> output/grounding validation -> programmatic source attachment. No fake provider or manually constructed final answer.
31. Exact real answer: `The prerequisites for COMP1110 (2026) are: COMP1100 OR COMP1130 OR COMP1730`.
32. HTTP status: `200`.
33. Response status: `ok`.
34. Source record ID: `courses:course:COMP1110_2026`; source ID: `courses_programs_and_courses`; domain: `courses`.
35. Source title: `Structured Programming`.
36. Source URL: `https://programsandcourses.anu.edu.au/2026/course/comp1110`.
37. URL equals stored canonical URL: PASS; all five source fields compared to the loaded record, not a separately reconstructed expectation.
38. Fixture leakage: NONE. Runtime factory loaded the explicit external single-record path; output contained the real title and lowercase stored URL. Historical default fixture remains unchanged.
39. Semantic bound: PASS. Answer exactly matches the Day 3 deterministic baseline; OR relationship, course identifiers and year preserved. No added facts, enrollment advice or model URL.
40. G1: PASS with real updated artifact and real Gemini, plus offline supported-path tests.
41. G2: PASS offline with separate synthetic null/empty/blank evidence, without mutating the real record.
42. G3: PASS offline, unknown exact course abstains with no guessed entity.
43. G4: PASS offline, clearly unrelated questions return `off_topic` with no invented source.
44. G5: PASS for supplied categories/examples: user and retrieved-content injection, source replacement, system-prompt requests, public-structure changes and unsupported facts.
45. G6: PASS for RAG-owned validation of unsafe script/event-handler output and unsafe requested evidence. No claim to have run frontend rendering tests.
46. G7: PASS offline: timeout, provider exception, missing key, empty/malformed/blocked/truncated output, missing/wrong/extra fields and unsupported facts.
47. Insufficient evidence: Gemini is not called; frozen `insufficient_evidence` and existing stored source if known. Null never means “no prerequisites.”
48. Unknown entity: Gemini is not called; empty sources and `insufficient_evidence`.
49. Off-topic: Gemini is not called; empty sources and frozen `off_topic`. Unsupported on-topic questions abstain.
50. Prompt injection: instructions cannot change the evidence-derived allowed answer or programmatic sources; invalid model outputs fail closed.
51. System-prompt leakage: isolated request is handled without Gemini; supported question plus disclosure instruction cannot escape answer validation. Tests pass.
52. Malicious URL replacement: rejected/ineffective in tests. Model URL/source extras never become API sources.
53. Retrieved-content injection: unrelated malicious content is excluded from the prompt; malicious prerequisite text fails before synthesis. Tests use synthetic records only.
54. Unsafe HTML: RAG rejects unsafe model answers rather than escaping/returning them as successful answers. No new sanitizer or HTML execution. Ben's safe frontend rendering remains necessary for untrusted display content.
55. Timeout: bounded service deadline cancels provider; SDK timeout also bounded, one SDK attempt; safe HTTP 502/error, no raw diagnostics.
56. Provider exception: translated at Gemini boundary into safe `SynthesisError`, explicitly handled as HTTP 502 with frozen error envelope, no raw exception text.
57. Malformed output: controlled HTTP 502/error, not repaired/coerced silently into public success.
58. Unsupported factual output: complete-answer allowlist rejects added prerequisite facts, OR -> AND, changed year/entity, arbitrary URLs or extra fields. Validation was not loosened for the live smoke.
59. Logging/privacy: source and diff inspection plus log-capture tests pass. No normal raw prompt/question/history/model output/key logging added. Temporary service emitted only startup information; no sensitive logs captured. Keep verbose SDK/HTTP debug logging disabled with credentials.
60. Secret scan: keyword review and credential-pattern scan of changed/new files passed; no real key/Bearer/private-key matches reported. This is a targeted check, not a comprehensive external security audit.
61. No real key committed; no commits made. `.env` remains ignored and unchanged.
62. No full raw prompt/history logging added.
63. No model-generated URL can enter final sources through this implementation.
64. No vector, embeddings, hybrid, pgvector or semantic fallback added.
65. No scraper change, collector rerun, parser investigation or artifact copy made during this task.
66. No shared schema/API contract changed; six response fields, statuses, schema-v1 model, ID/year/hash/URL rules preserved. No new domains, UI, migration, Cloud SQL or deployment scope.
67. Full `python -m pytest`: **197 passed, 1 skipped, 4 warnings** after the live smoke. Existing skip: Windows symlink permission. No new tests required for this final recheck.
68. `python -m pip check`: PASS, `No broken requirements found.`
69. `python -m compileall -q src tests`: PASS.
70. `git diff --check`: PASS; existing Windows LF -> CRLF notices only.
71. Health smoke: `GET http://127.0.0.1:8014/health`, HTTP 200, `{"status":"ok"}`. Bound to localhost only.
72. Final real POST smoke: HTTP 200/ok; answer/source at items 31-36; `request_id=req_52b9abce9b634ee3b653633fdf11a891`, `clarification=null`, `items=[]`; all six fields validated through the frozen `AskResponse` union. Real provider was injected by the configured factory. One real request made; temporary server stopped and port closure verified.
73. Warnings: existing Starlette/httpx and AnyIO deprecations, SDK Python 3.14 typing deprecation, existing pytest cache permission warning. No unrelated dependency upgrades to suppress them.
74. Sole Qasim blocker: make the exact gate branch/file available or provide its correct repository/ref. Gate-specific wording remains unverified.
75. Carmen's implementation, real Gemini integration and known RAG-owned G1-G7 verification are complete; **full requested Day 4 sign-off remains incomplete solely because exact gate-document review is blocked**.
76. Branch is ready for code review, but not recommended for final commit/push sign-off until item 74 is resolved. Existing uncommitted work preserved.
77. Suggested commit: `feat: add evidence-bounded Gemini synthesis and safety gates`.
78. Suggested PR title: `Day 4 — Grounded Gemini synthesis, abstention and safety validation`.
79. Updated V3-template PR description below; not submitted.
80. **NOT READY** for final commit/push recommendation: only the exact Qasim gate-document comparison remains. No code/Gemini/artifact blocker remains.

## Exact gate lookup evidence

`git fetch origin` succeeded after permission escalation. The configured fetch
refspec covers all remote branches: `+refs/heads/*:refs/remotes/origin/*`.
Reading the requested ref returned:

```text
fatal: invalid object name 'origin/qasim/day4-grounding-security-gate'.
```

A remote head search for Day 4/grounding branches returned no matching heads.
Directly fetching the supplied branch returned:

```text
fatal: couldn't find remote ref qasim/day4-grounding-security-gate
```

No branch was checked out, no gate content was invented, and no criteria changed.
The earlier stale-artifact/real-Gemini blockers are now resolved.

## Real HTTP response

```json
{
  "answer": "The prerequisites for COMP1110 (2026) are: COMP1100 OR COMP1130 OR COMP1730",
  "items": [],
  "sources": [
    {
      "record_id": "courses:course:COMP1110_2026",
      "source_id": "courses_programs_and_courses",
      "title": "Structured Programming",
      "url": "https://programsandcourses.anu.edu.au/2026/course/comp1110",
      "domain": "courses"
    }
  ],
  "request_id": "req_52b9abce9b634ee3b653633fdf11a891",
  "status": "ok",
  "clarification": null
}
```

## V3 task

Day / task:
Day 4 — Add grounded Gemini synthesis, abstention and safety validation (#9)

The sections below form the final PR draft; no PR has been created.

## What changed?

- Evidence-only context assembler and small async Gemini interface/official provider integration.
- Strict internal JSON schema and complete-answer grounding validation: Gemini chooses wording without rewriting evidence.
- Programmatic RAG source attachment and service-owned public status.
- Deterministic insufficient-evidence, unknown-entity and off-topic handling before Gemini.
- Prompt/retrieved-content injection, unsafe HTML, malformed output, timeout/provider-failure protections.
- Centralized environment configuration and logging/secret safety.
- Existing deterministic retrieval preserved; no vector/hybrid retrieval or scraper changes.

## Acceptance criteria / verification

- [x] Updated real COMP1110 runtime artifact validates through the existing loader and exact repository.
- [x] Real Gemini supported smoke: HTTP 200 / ok with stored official source.
- [x] Known G1-G7 RAG-owned cases pass; G1 verified with actual Gemini.
- [x] Relevant tests: 197 passed, 1 existing Windows-permission skip.
- [x] `pip check`, `compileall`, `git diff --check` pass.
- [x] No unrelated scope added.
- [ ] Today's full gate-document verification complete: Qasim's specified remote branch is unavailable.

## Contracts / architecture

- [x] No shared contract changed.
- [ ] If changed, decision log and Qasim/team approval recorded (not applicable).

Frozen six-field response and schema-v1 remain intact. Day 3 exact retrieval
supplies facts; Gemini synthesizes only within evidence-derived approved phrasings.
RAG owns sources, canonical URL and status. No scraper implementation copied.

## Security / data

- [x] No secrets committed.
- [x] No unapproved source introduced.
- [x] No raw full production prompt/history logging introduced.

Model-generated URLs never enter sources. Injection cannot override the
evidence/source boundary. Malformed, unsafe or unsupported model output and
provider failures produce the existing safe error envelope.

## Evidence / screenshots

Question: **What are the prerequisites for COMP1110?**

Actual Gemini answer:
**The prerequisites for COMP1110 (2026) are: COMP1100 OR COMP1130 OR COMP1730**

HTTP 200 / `ok`; model `gemini-3.5-flash-lite`.
Source: `Structured Programming`,
`https://programsandcourses.anu.edu.au/2026/course/comp1110`.
Request ID: `req_52b9abce9b634ee3b653633fdf11a891`.

Validated source fields equal the updated runtime record, with no fixture leakage,
extra fact, OR/AND change or reconstructed URL. Full evidence is recorded above.

## Blockers / carry-over

Only remaining item: obtain and compare Qasim's frozen
`docs/DAY4_GROUNDING_SECURITY_GATE.md`.
The supplied `qasim/day4-grounding-security-gate` branch is not available from
this RAG origin after fresh fetch and direct remote-ref verification.
No remaining real-artifact or real-Gemini blocker.

Closes #9
