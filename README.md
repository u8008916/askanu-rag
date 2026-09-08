# AskANU RAG

Grounded retrieval and answer service.

The service provides `/health` and an exact-first course prerequisites path through
`/api/v1/ask`. Day 4 adds evidence-bounded Gemini phrasing without giving the model
control of facts or sources. Unsupported ANU questions abstain; unrelated questions
return `off_topic`. Neither path invents sources or calls Gemini.

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

Run the Day 4 service from the repository root:

```text
.venv\Scripts\python -m uvicorn askanu_rag.main:create_configured_app --factory --app-dir src --host 127.0.0.1 --port 8081
```

Run the contract tests:

```text
.venv\Scripts\python -m pytest
```

The temporary Day 1 mock returns `needs_clarification` when `question` is
exactly `mock:needs_clarification`. This is an isolated contract-test hook, not
production conversation or query-planning behaviour.

## Local normalized record handoff

Without a configured handoff path, the app still loads the approved Day 2 JSON-array fixture. Its COMP1110
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
A real updated COMP1110/2026 artifact has been verified locally through the single-file
loader, exact repository lookup, real Gemini and the configured HTTP API path.
It returned HTTP 200 / `ok` with the answer:
`The prerequisites for COMP1110 (2026) are: COMP1100 OR COMP1130 OR COMP1730`.
The stored title `Structured Programming` and canonical URL
`https://programsandcourses.anu.edu.au/2026/course/comp1110` were preserved exactly.
This updated runtime artifact replaces the earlier null-evidence smoke input;
the default Day 2 fallback fixture remains unchanged. The artifact remains
outside this repository; RAG reads the serialized boundary without collecting
pages, rewriting URLs, or recomputing hashes.

## Day 4 configuration and grounding

Place the local key in an ignored `.env` file in the repository root under
`GEMINI_API_KEY`. Never paste the value into source, tests, logs or a PR.
The configured factory reads only `.env` in the current working directory;
process environment variables take precedence. `python-dotenv` handles this file
without modifying the process environment. Tests do not read the local file.

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash-lite
COURSE_RECORDS_PATH=
MAX_OUTPUT_TOKENS=800
REQUEST_TIMEOUT_SECONDS=30
```

Set `COURSE_RECORDS_PATH` to an existing schema-v1 single-object JSON file or
`records/` directory, not the storage base. No path to a sibling repo is hard-coded.
Relative paths resolve from the working directory. Invalid handoff data fails at
startup; no fallback silently replaces an explicitly selected bad artifact.
Blank path retains the Day 2 fixture (including its historical null prerequisites).
To prove the real COMP1110 success case, select the **updated** scraper artifact
whose `metadata_json.prerequisites` is `COMP1100 OR COMP1130 OR COMP1730`.
Do not edit the old record, patch its metadata, or copy scraper code to make a demo pass.

`create_app(repository, synthesis_client)` supports injected async fake clients.
Omitting `synthesis_client` preserves deterministic Day 3 behavior; the legacy
`askanu_rag.main:app` entrypoint is explicitly deterministic. Use the configured
factory above for Gemini. Missing credentials do not trigger a knowledge fallback:
supported requests fail with controlled HTTP 502, while missing evidence abstains
before the provider is called.

The provider interface is `async synthesize(context) -> str` (untrusted JSON).
Only the standalone question and three evidence fields are sent: course code,
academic year and prerequisites. Full record content, title, URLs, IDs, history,
timestamps, hashes and unrelated metadata are excluded. Instructions are sent
separately from JSON-encoded untrusted question/evidence data. No tools/search are
enabled. SDK and service deadlines are capped at 30 seconds, output at 800 tokens,
and SDK attempts at one.

Internal output is exactly `{"answer": "...", "supported": true}`. Strict Pydantic
validation rejects extra/missing fields, coercions and empty output. Duplicate JSON
keys, truncated/blocked output, unsafe requested evidence and malformed JSON are
also rejected. `supported: true` is **not proof**: the answer must match one of
three complete strings assembled from the retrieved fields, preserving values and
OR/AND verbatim. Gemini chooses wording, not facts. This deliberately narrow
Day 4 design is not general free-form semantic validation.

Source objects and public status are built only by RAG. Model URLs, HTML, added
facts or changed identities cannot pass the answer allowlist. Unsafe requested
evidence fails closed; unrelated malicious `content` is not sent. Answers are
plain text, not trusted HTML; frontend safe rendering remains required. Failures
return HTTP 502 with the frozen `error` envelope and safe message, never provider
diagnostics. No raw request/history/prompt/model output or credential logging is
introduced. Keep SDK/HTTP debug logging disabled when using real credentials.

### Day 4 verification

```text
.venv\Scripts\python -m pytest
.venv\Scripts\python -m pip check
.venv\Scripts\python -m compileall -q src tests
git diff --check
```

Tests use synthetic records and injected fake/SDK-stub clients, with no network,
API key or quota dependency. They cover G1-G7 and Day 3 regressions. Synthetic
COMP1110 test evidence is not a captured live scraper artifact.

For a real local smoke, configure the updated handoff path and run the Day 4
factory. Request `GET /health`, then POST this JSON to `/api/v1/ask`:

```json
{
  "question": "What are the prerequisites for COMP1110?",
  "history": [],
  "conversation_state": {"pending_clarification": null}
}
```

Expect HTTP 200 / `ok`, the exact stored prerequisite alternatives, the stored
source title/URL and a `req_` identifier in the six-field envelope. A null artifact
must instead return `insufficient_evidence` without calling Gemini. Check the
artifact first; do not treat abstention as proof of a real provider call.
