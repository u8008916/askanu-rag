# AI_SETUP.md

## Workflow
Human chooses task + acceptance criteria -> AI reads repo rules/contracts -> AI proposes a small plan -> human checks -> AI implements -> tests -> human reviews diff -> PR -> review/merge.

## First prompt
> Read `AGENTS.md`, `docs/V3_LOCKED_DECISIONS.md`, `docs/MY_DAY_BY_DAY_TASKS.md`, and every contract relevant to today's task. Do not edit anything yet. Tell me today's exact task, dependencies, files you expect to touch, tests you will run, and anything blocking you.

## Implementation prompt
> Implement only today's approved V3 task. Keep the change small. Do not change repository boundaries, contracts, source policy, architecture, privacy/security rules or status semantics. Run the listed verification/tests and show me the diff before I commit.

## Rules
- work on a branch, not directly on `main`
- never paste or commit secrets/tokens/cookies/service-account JSON
- AI may implement approved work
- AI may not silently redefine architecture/contracts/source policy/release scope
- if blocked, use the fallback in today's task; do not invent new scope
