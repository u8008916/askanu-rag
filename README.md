# AskANU RAG

Grounded retrieval and answer service.

The Day 1 service skeleton provides a safe `/health` endpoint and a mock-only
`/api/v1/ask` endpoint backed by the frozen V3 request and response models. It
does not perform retrieval, database access, embedding, or model calls.

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
