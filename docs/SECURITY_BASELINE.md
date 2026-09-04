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
- question max 2,000 chars
- history max 10 prior turns
- output target ~800 tokens
- timeout target ~30 sec
- starting rate limit ~20 `/ask` requests / 10 min / anonymous session + coarse IP abuse protection

Default logs should avoid raw questions and full chat histories.
Before broader public launch, record ANU privacy/security/governance review requirements.
