## 1. Planning

- [x] 1.1 Prepare a local GitHub issue draft for this SDD-scoped runtime/config fix.
- [x] 1.2 Add OpenSpec proposal, design, tasks, and spec delta before implementation.

## 2. Tests First

- [x] 2.1 Add failing tests for default SQLite absolute `/data` URL, `.env.example`, and Python 3.14 runtime baseline.
- [x] 2.2 Add failing tests for parameterized compose Postgres healthcheck.
- [x] 2.3 Add failing strategy test proving `MAX_POSITION_QUOTE_USDT` caps buy-intent quote size.

## 3. Implementation

- [x] 3.1 Update default SQLite URLs in settings, container env, `.env.example`, README, and architecture docs.
- [x] 3.2 Update package metadata, CI, instructions, docs, and `Containerfile` to Python 3.14.
- [x] 3.3 Update compose healthcheck to use configured Postgres user and database.
- [x] 3.4 Enforce maximum position quote in buy-intent sizing without changing default behavior.

## 4. Verification

- [x] 4.1 Run Python 3.14 container gate: install `.[dev]`, `PYTHONPATH=src pytest`, `python -m compileall -q src tests`, `ruff check .`, and `mypy src`.
- [x] 4.2 Run `.venv/bin/python -m compileall -q src tests`.
- [x] 4.3 Run `.venv/bin/ruff check .`.
- [x] 4.4 Run `.venv/bin/mypy src`.
- [x] 4.5 Run `openspec validate --all --strict --no-interactive`.
- [x] 4.6 Run `podman compose config` because compose files changed, if the tool is available.
- [x] 4.7 Review `git diff` before handoff.
