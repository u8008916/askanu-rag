# AGENTS.md — askanu-rag

Primary owner: **Carmen**. Contracts/integration/release: **Qasim**.

This repo owns `/api/v1/ask`, request validation, context resolution, query planning, deterministic SQL/date/status retrieval, exact/entity lookup, metadata-filtered vector retrieval, grounded Gemini synthesis, output validation, abstention, clarification and RAG evaluation.

Not every question is vector search:
- exact course/entity -> exact lookup first
- current jobs/upcoming events -> deterministic SQL/time
- explicit year/session -> metadata filter
- semantic explanation/eligibility -> metadata + semantic
- ambiguity -> clarify first

Facts come from fresh retrieval. History is context. URLs come from stored records, never the model.

Before coding read `docs/MY_DAY_BY_DAY_TASKS.md`, `docs/API_CONTRACT.md`, `docs/DATA_SCHEMA.md`, `docs/CONVERSATION_CONTRACT.md`, `docs/SECURITY_BASELINE.md`.

When blocked, follow today's fallback and add tests/diagnosis rather than inventing architecture.
