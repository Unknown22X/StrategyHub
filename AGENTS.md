# Repository Guidelines

## Project Structure & Module Organization

This repository currently contains the product specification at
`docs/product-requirements.md`. Treat it as the authoritative source for scope,
safety rules, and acceptance criteria.

As implementation begins, keep the engine, desktop UI, and shared domain code
separate. A practical layout is `src/rangebot/engine/`,
`src/rangebot/ui/`, and `src/rangebot/domain/`; put tests in `tests/` with a
matching package structure. Keep deployment assets such as WinSW XML and
PyInstaller specifications under `deploy/`. Do not put credentials, runtime
data, or generated builds in the repository.

## Build, Test, and Development Commands

The planned Python toolchain is `uv`, with dependencies declared in
`pyproject.toml` and locked in `uv.lock`. Once those files exist, use:

```powershell
uv sync                 # create/update the development environment
uv run pytest           # run the full test suite
uv run pytest tests/unit -q
uv run ruff check .     # lint, if Ruff is configured
uv run ruff format .    # format, if Ruff is configured
```

Do not add a command to this guide until its configuration is committed. Test
Paper Trading before Testnet; enable Live Trading only through the documented
manual procedure.

## Coding Style & Naming Conventions

Use UTF-8 and four-space indentation for Python. Follow PEP 8 naming:
`snake_case` for functions, variables, and modules; `PascalCase` for classes;
and `UPPER_SNAKE_CASE` for constants. Keep strategy, risk, execution, and
exchange-domain logic operating-system independent; Windows-service and Qt
details belong at the edges. Use `Decimal` for prices, sizes, fees, and all
financial calculations; never `float`.

Validate external inputs with Pydantic, keep SQLAlchemy/Alembic database
changes migration-backed, and write Arabic user-facing text deliberately with
RTL rendering in mind. Redact secrets in every log path.

## Testing Guidelines

Use Pytest for unit and integration tests and Hypothesis for financial
invariants. Name files `test_<feature>.py` and tests `test_<behavior>()`.
Cover state transitions, rounding, stale-data handling, idempotency, partial
fills, restart reconciliation, and protective-order behavior. Mock Gate.io
REST/WebSocket calls in automated tests; keep Testnet checks explicitly marked
and never depend on them for routine local test runs.

## Commit & Pull Request Guidelines

No Git history is available yet, so use short imperative commit subjects such
as `Add stale-market entry guard`. Keep each commit focused. Pull requests
should describe the safety impact, link the relevant requirement IDs (for
example, `SAFE-014`), list tests run, and include screenshots for Qt UI or RTL
text changes. Never commit `.env`, API keys, request signatures, database
passwords, logs, or build output.

## Git and Workspace Hygiene

Before editing any files, inspect the current Git status.

If modified or untracked files already exist:

- Do not reset, discard, overwrite, or delete them.
- Determine whether they are intentional source changes or generated local artifacts.
- Inform the user when existing work makes attribution unclear.
- Create or request a checkpoint commit before beginning a large implementation task.
- Preserve all existing work unless the user explicitly approves its removal.

Keep real source files, tests, migrations, documentation, and configuration under
version control.

Keep generated or machine-local content out of Git, including:

- Virtual environments
- Test caches and temporary test directories
- Runtime databases and account state
- Logs
- Build and release output
- Playwright-generated inspection files
- Local AI-agent state
- Credentials, secrets, API keys, signatures, and `.env` files

Update `.gitignore` whenever a tool introduces a new generated directory.

Implementation workflow:

1. Begin from a clean working tree whenever practical.
2. Create a dedicated branch for substantial work.
3. Keep each commit focused on one milestone or coherent issue.
4. Do not mix unrelated cleanup with feature changes.
5. Run relevant tests before committing.
6. Report the exact files changed and commands run.
7. End each completed milestone with a focused commit.
8. Leave the working tree clean at the end of the task.

Never run destructive commands against existing user work without explicit approval,
including:

- `git reset --hard`
- `git clean -fd`
- `git restore .`
- `git checkout -- .`

Before staging or committing, verify that no secrets, credentials, private databases,
logs, or generated build artifacts are included.

## Agent skills

### Issue tracker

Issues and specs are tracked as local Markdown files under
`.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Domain docs

This repository uses a single-context domain-doc layout. See
`docs/agents/domain.md`.
