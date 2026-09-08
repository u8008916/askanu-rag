# AskANU RAG

Grounded retrieval and answer service.

The service provides a safe `/health` endpoint and a deterministic Day 3 course
prerequisites path through `/api/v1/ask`, backed by the frozen V3 models and exact
repository lookup. Unsupported questions retain the explicit Day 1 mock response.

**Primary owner:** Carmen

**Contracts/integration/release:** Qasim

**AI:** Codex

Start with:
1. `AGENTS.md`
2. `docs/MY_DAY_BY_DAY_TASKS.md`
3. `docs/API_CONTRACT.md`
4. `docs/DATA_SCHEMA.md`
5. `docs/AI_SETUP.md`

The repo is synchronised to AskANU Project Execution Plan V3.

## Local setup

Python 3.11 or newer is required.

```text
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
```

Run the service:

```text
.venv\Scripts\python -m uvicorn askanu_rag.main:app --app-dir src
```

Run the contract tests:

```text
.venv\Scripts\python -m pytest
```

The temporary Day 1 mock returns `needs_clarification` when `question` is
exactly `mock:needs_clarification`. This is an isolated contract-test hook, not
production conversation or query-planning behaviour.

## Local normalized record handoff

The default app still loads the approved Day 2 JSON-array fixture. Its COMP1110
record has null prerequisites, so the prerequisite question returns
`insufficient_evidence` with the stored source URL.

For scraper-generated data, supply an explicit path to a single schema-v1 JSON
object file or to the scraper's `records/` directory. Each record file is read as
UTF-8 and validated with the existing RAG `CourseProgramRecord` model. These
loaders do not require the scraper package or a fixed sibling-repository path.

```python
from askanu_rag.main import create_app
from askanu_rag.retrieval import (
    CourseProgramRepository,
    load_course_program_record_file,
    load_course_program_records_directory,
)


def app_from_records_directory(records_directory):
    records = load_course_program_records_directory(records_directory)
    return create_app(repository=CourseProgramRepository(records))


def app_from_record_file(record_file):
    record = load_course_program_record_file(record_file)
    return create_app(repository=CourseProgramRepository([record]))
```

Pass the records directory itself, not the storage base containing `records/`
and `runs/`. Directory loading reads only direct `.json` files (case-insensitive
extension) in filename order and does not recurse into subfolders. Filenames
select/order files; identity and academic year come from validated JSON content.
All years are retained. An empty directory returns an empty tuple; duplicate
entity/code/year keys are still rejected by the existing repository.

Missing paths and non-directory inputs fail explicitly. Invalid JSON/schema
raises the existing validation error with the offending file path attached as
an exception note. Links and Windows reparse-point entries are rejected.
No invalid JSON record is silently skipped. Loading occurs before app injection;
construction errors propagate to the caller, while HTTP runtime failures retain
the existing controlled error envelope.

The repository holds the loaded snapshot; reload and reconstruct it to consume
a later handoff. Supply real records instead of appending them to equivalent
fallback records. Runtime artifacts are generated externally by the scraper.
A real COMP1110/2026 artifact has been verified locally through the single-file
loader, exact repository lookup and injected API path. It returned the stored
title `Structured Programming` and canonical URL
`https://programsandcourses.anu.edu.au/2026/course/comp1110` exactly. Its null
prerequisites correctly produced `insufficient_evidence`. The artifact remains
outside this repository; RAG reads the serialized boundary without collecting
pages, rewriting URLs, or recomputing hashes.
