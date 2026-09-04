# DECISION_LOG.md

Record only decisions that change V3 contracts, architecture, source policy, scope, security/privacy rules, or schedule.

| Date | Decision | Why | Affected repos/docs | Owner | Approved by |
|---|---|---|---|---|---|
| 2026-09-05 | Freeze HTTP 400 for malformed JSON/validation, 413 for oversized input, 429 for rate limiting, and controlled 5xx JSON for DB/model/internal dependency failures; retain `error` status and safe response envelope. | Unblock Day 1 contract validation without changing V3 statuses. | RAG `docs/API_CONTRACT.md`; App contract copy requires synchronisation. | Qasim (contracts) | User instruction in pre-bootstrap cleanup request |
| 2026-09-05 | Define non-null pending clarification using the existing clarification object; distinguish evidence `record_id` from registry `source_id`; define minimal Events/Jobs list responses with V3 ordering and stored-record URLs. | Remove integration ambiguity while preserving V3 decisions; defer domain field types/nullability to Day 2. | RAG `docs/API_CONTRACT.md`; App/Scraper affected contract copies require synchronisation. | Qasim (contracts) | User instruction in pre-bootstrap cleanup request |

If a decision changes a shared contract, update every affected repo in the same work cycle.
