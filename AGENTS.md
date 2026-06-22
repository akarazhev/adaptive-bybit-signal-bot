# Adaptive Bybit Signal Bot - Codex/ECC Instructions

This repository is a Python 3.12 read-only/order-intent bot for Bybit Spot
BTC/ETH. Codex must preserve the production safety boundary: the project reads
public/read-only data, computes signals, and writes local order intents. It must
not place, cancel, amend, transfer, or withdraw on Bybit.

## Project Stack

- Python 3.12 package under `src/adaptive_bybit_bot`.
- Typer CLI entrypoint: `adaptive-bybit-bot`.
- FastAPI read-only HTTP API in `src/adaptive_bybit_bot/api`.
- SQLAlchemy persistence with SQLite standalone mode and PostgreSQL compose mode.
- Pydantic Settings from `.env`; never inspect, print, or commit local `.env`.
- Podman deployment via `Containerfile`, `compose.yaml`, `compose.rest.yaml`, and
  `compose.recorder.yaml`.
- Tests use pytest; quality tools are ruff and mypy.

## ECC Daily Skills

Project-local ECC skills are installed under `.agents/skills/`.

Use these as the default daily surface:

- `tdd-workflow` for behavior changes and bug fixes.
- `verification-loop` before handoff or commit.
- `python-patterns` and `python-testing` for Python implementation and tests.
- `fastapi-patterns` and `api-design` for the read-only API.
- `security-review` and `llm-trading-agent-security` for credentials, financial
  safety, and any trading-adjacent workflow.
- `database-migrations` for schema/data-store changes, even though the current
  project creates schema through SQLAlchemy metadata rather than Alembic.
- `docker-patterns` and `deployment-patterns` for Containerfile/compose work.
- `coding-standards` for cross-cutting maintainability.

Do not add off-stack ECC surfaces to the daily set unless repo evidence changes.

## OpenSpec Workflow

OpenSpec is initialized under `openspec/` and configured for this repository's
production safety model.

- Use `openspec/config.yaml` as the project-specific planning context for new
  proposals, specs, designs, and tasks.
- Use OpenSpec for behavior, persistence, API, runtime, deployment, or safety
  changes before implementation. Prefer `/opsx:propose` for a complete first
  pass or the equivalent `openspec` CLI workflow when operating from a shell.
- Keep source specs under `openspec/specs/` aligned with the repo's production
  safety and governance contracts.
- Run `openspec validate --all --strict --no-interactive` before handoff when
  OpenSpec artifacts change.

## Review Guidelines

Codex code review in GitHub should prioritize P0/P1 issues only.

- Flag any path that could place, cancel, amend, submit, transfer, withdraw, set
  leverage, or otherwise execute on Bybit.
- Flag any weakening of the read-only/order-intent boundary, credential
  handling, `.env` secrecy, or `BYBIT_ALLOW_READ_WRITE_KEY=false` default.
- Flag state-changing API endpoints unless they include explicit authorization,
  validation, rate limiting, and security review.
- Flag persistence changes that do not preserve both SQLite standalone and
  PostgreSQL compose behavior.
- Flag runtime/compose/recorder changes that make high-volume recording
  default-on or create unsafe restart, storage, or rollback behavior.
- Flag missing OpenSpec artifacts, tests, or verification for production-facing
  changes.
- Do not block on style-only issues unless they hide a correctness, safety, or
  operability problem.

## Non-Negotiable Safety Invariants

- Do not add direct exchange execution methods, including:
  `place_order`, `cancel_order`, `amend_order`, `create_order`, `submit_order`,
  `withdraw`, `transfer`, or `set_leverage`.
- Keep `BybitRestClient` public/read-only except for signed read-only account
  validation/sync paths already present.
- Do not change `BYBIT_ALLOW_READ_WRITE_KEY=false` defaults or documentation
  without an explicit security review and user approval.
- New HTTP endpoints are GET/read-only unless the user explicitly requests a
  write endpoint and a security review is completed.
- Keep market recorder functionality opt-in through the recorder compose overlay;
  do not make high-volume recording default-on.
- Do not read or expose `.env`. Use `.env.example` for documentation and tests
  should override settings explicitly.
- Do not add live-network requirements to unit tests. Use `httpx.MockTransport`,
  local fixtures, or explicit integration test gating.

## Development Workflow

1. Read `README.md`, `pyproject.toml`, `doc/spec/07_CURRENT_ARCHITECTURE.md`,
   `doc/spec/08_NEXT_ROADMAP_V0.7_PLUS.md`, and
   `doc/spec/09_CODEX_CLI_HANDOFF.md` before feature work.
2. Plan changes before editing when behavior spans strategy, persistence, API,
   compose services, or safety rules.
3. Use TDD for bug fixes and new behavior: failing test first, minimal
   implementation, then refactor.
4. Preserve existing module boundaries:
   - `exchange/` isolates Bybit REST/WS adapters.
   - `features/`, `strategy/`, and `sentiment/` stay calculation-oriented.
   - `data/repositories.py` owns persistence workflows.
   - `services/` owns runtime orchestration.
   - `api/` remains read-only presentation.
5. Keep changes small and focused. Avoid unrelated refactors or formatting churn.
6. Update `doc/spec/` when changing architecture, safety guarantees, runbooks,
   compose topology, or the roadmap.

## Verification Commands

Use the local virtualenv when available.

Core checks:

```bash
PYTHONPATH=src pytest
python -m compileall -q src tests
ruff check .
mypy src
```

Useful smoke checks:

```bash
PYTHONPATH=src python -m adaptive_bybit_bot.cli --help
PYTHONPATH=src python -m adaptive_bybit_bot.cli init-db
```

Container checks when deployment files change:

```bash
podman build -t adaptive-bybit-signal-bot -f Containerfile .
podman compose config
```

If a required tool is unavailable, report that explicitly in the handoff rather
than implying the check passed.

## Codex Operating Rules

- Treat networked tools as read-only unless the user approves a write action.
- Prefer Context7 or primary documentation for current library/API behavior.
- Before using live Bybit or Alternative.me endpoints, state the intent and keep
  the run optional; public-network tests are not required for ordinary changes.
- Review diffs before final handoff. Call out residual safety, test, or
  deployment risk clearly.
