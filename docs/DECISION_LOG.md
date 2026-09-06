# DECISION_LOG.md

Record only decisions that change V3 contracts, architecture, source policy, scope, security/privacy rules, or schedule.

| Date | Decision | Why | Affected repos/docs | Owner | Approved by |
|---|---|---|---|---|---|
| 2026-09-05 | Freeze HTTP 400 for malformed JSON/validation, 413 for oversized input, 429 for rate limiting, and controlled 5xx JSON for DB/model/internal dependency failures; retain `error` status and safe response envelope. | Unblock Day 1 contract validation without changing V3 statuses. | RAG `docs/API_CONTRACT.md`; App contract copy requires synchronisation. | Qasim (contracts) | User instruction in pre-bootstrap cleanup request |
| 2026-09-05 | Define non-null pending clarification using the existing clarification object; distinguish evidence `record_id` from registry `source_id`; define minimal Events/Jobs list responses with V3 ordering and stored-record URLs. | Remove integration ambiguity while preserving V3 decisions; defer domain field types/nullability to Day 2. | RAG `docs/API_CONTRACT.md`; App/Scraper affected contract copies require synchronisation. | Qasim (contracts) | User instruction in pre-bootstrap cleanup request |
| 2026-09-06 | Freeze Courses/Programs schema v1: full 16-field normalized Scraper -> DB -> RAG record; year-scoped `entity_id`; namespaced stable `record_id`; explicit four-digit academic year; SHA-256 `content_hash` of canonical `content`; stored canonical URLs; strict no-invented-value/null policy; multi-year-safe RAG lookup; and first DB/migration ownership. | Unblock Will -> Carmen integration using one implementation-ready shared boundary based on the verified scraper output and Carmen's Day 2 exact-retrieval requirements. | RAG `docs/DATA_SCHEMA.md` and `docs/DECISION_LOG.md`; Scraper `docs/DATA_SCHEMA.md` and implementation require synchronisation before PR #5 merge. | Qasim (contracts/integration) | Qasim after Will/Carmen implementation review |


If a decision changes a shared contract, update every affected repo in the same work cycle.
