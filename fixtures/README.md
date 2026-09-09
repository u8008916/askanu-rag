# Courses/Programs schema-v1 fixture

`day2_course_program_records.json` is representative offline RAG test data that
follows the frozen Courses/Programs schema v1. It is not scraper implementation
code and does not claim that its content is current live ANU data. The schema
source of truth is `docs/DATA_SCHEMA.md`.

Provenance fields, canonical URLs, timestamps, statuses, and content hashes are
stored fixture values. The RAG boundary validates and preserves them; it does
not generate URLs or recalculate scraper-owned hashes.

## Day 5 bounded catalog fallback

`day5_course_program_records.json` is explicitly **synthetic, offline test data**
for Issue #10's approved fallback, not a scraper capture or current ANU catalog.
It contains COMP1110, COMP1100 (2026/2027), COMP2200, BIOL9001P and BACCT.
Titles/descriptions, optional metadata and illustrative provenance values support
tests of names, exact identifiers, entity types, sessions and distinct vector matches.
Do not present the synthetic descriptions or illustrative URLs as live source verification.

It uses the same complete 16-field schema-v1 JSON-array format and existing fixture
loader as Day 2, not a private scraper format. Its hashes describe its synthetic
content. RAG retrieval does not recompute or update them, embedding_version or
index_status. Runtime real-record smoke tests read the external scraper JSON directly;
no real artifact was copied here. The Day 2 fixture/default app snapshot is unchanged.
