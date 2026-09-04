# V3_LOCKED_DECISIONS.md

This repository is synchronised to **AskANU Project Execution Plan V3**.

## Schedule
- Start: Saturday 5 September 2026
- 5–18 September: 5 hours/person/day
- Stakeholder presentation: Friday 18 September 2026
- 19 September–3 October: normally 1 hour/person/day
- Sunday 27 September: 4 hours/person
- Target feature freeze: Monday 28 September
- Final release: Saturday 3 October
- Capacity: 88 hours/person; 352 team-hours

## Team ownership
- Ben — App/UI/React — `askanu-app` — Claude Code
- Carmen — RAG/backend — `askanu-rag` — Codex
- Will — scraper/data/freshness — `askanu-scraper` — Claude Code or Codex
- Qasim — PM/integration/GCP/testing/security/release — cross-repo — Codex

## Architecture
Three separate repos. Do not convert to a monorepo.

`Browser/React -> App service -> REST -> RAG service -> Cloud SQL/pgvector -> Gemini`

`Cloud Scheduler -> Scraper job -> safe DB/index updates`

## Product/UI
- One chatbot across Courses, Events, Accommodation, Scholarships, Jobs, Support.
- Desktop: chat primary/left; resources/navigation right.
- `Clear Chat`, not `New Chat`.
- No profile/login block.
- `Try asking` only in empty state; disappears after the first question.
- Resource pages are information hubs, not separate bots.
- Mobile is the same responsive React website with drawer navigation.
- Quick Links: AnuHub, MyTimetable, Canvas, ANU Careers.
- Short deterministic Upcoming Events and Current Jobs summaries.

## Sources
- Courses: Programs and Courses
- Scholarships: ANU Scholarships
- Jobs: ANU Jobs
- Accommodation: ANU Accommodation
- Support: ANUSA Student Assistance + approved ANU support pages
- Events: official ANU Events/calendar
- Rubric: disabled for production unless approved API/feed/integration access is obtained

## Scholarship display
Show up to 9 open Featured scholarships. If fewer than 9 are available, fill remaining slots with other open scholarships ordered by nearest known deadline. Do not call them “most popular” without a real popularity metric.

## Conversation
Current-session context only. History resolves meaning; fresh retrieval supplies facts. Support clarification such as first/second/both/correction. `Clear Chat` clears history/context/pending clarification.

## Change rule
If any later decision conflicts with this file, record it explicitly in the decision log and update all affected contracts. Do not let an AI coding tool silently redefine the project.
