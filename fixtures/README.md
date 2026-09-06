# Courses/Programs schema-v1 fixture

`day2_course_program_records.json` is representative offline RAG test data that
follows the frozen Courses/Programs schema v1. It is not scraper implementation
code and does not claim that its content is current live ANU data. The schema
source of truth is `docs/DATA_SCHEMA.md`.

Provenance fields, canonical URLs, timestamps, statuses, and content hashes are
stored fixture values. The RAG boundary validates and preserves them; it does
not generate URLs or recalculate scraper-owned hashes.
