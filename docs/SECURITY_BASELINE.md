# SECURITY_BASELINE.md

V3 MVP baseline:
- least-privilege App/RAG/Scraper identities
- Secret Manager; no committed credentials
- no browser -> DB
- parameterised SQL
- request/response schema validation
- safe rendering; do not execute model/scraped HTML/JS
- approved source registry
- source URLs from stored records
- prompt-injection/system-prompt disclosure tests
- input/history/output/timeout limits
- rate/cost controls
- dependency and secret scanning
- controlled errors

Starting values:
- question max 2,000 Unicode code points and 8 KiB UTF-8
- history max 10 prior turns, 96 KiB compact serialized UTF-8 total,
  128 characters per `turn_id`, and 10,000 characters per `content`
- `conversation_state` max 128 KiB compact serialized UTF-8
- complete `/api/v1/ask` request body max 256 KiB raw bytes, aligned with
  the App proxy target
- output target ~800 tokens
- timeout target ~30 sec
- starting rate limit ~20 `/ask` requests / 10 min / anonymous session + coarse IP abuse protection

Default logs should avoid raw questions and full chat histories.
Before broader public launch, record ANU privacy/security/governance review requirements.
