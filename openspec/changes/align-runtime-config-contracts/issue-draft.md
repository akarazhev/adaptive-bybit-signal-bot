## Title

Align runtime configuration contracts for SQLite, container Python, compose health, and risk caps

## Context

Repository review found implementation/specification drift in production-facing
runtime defaults. Standalone Podman docs mount `/data`, but the default SQLite
URL resolves to a relative path. The project is moving fully to Python 3.14, so
package metadata, CI, container, instructions, and docs must agree on that
baseline. Compose parameterizes PostgreSQL credentials but hardcodes the
healthcheck user/database. The public `MAX_POSITION_QUOTE_USDT` setting is
passed into `RiskConfig` but does not affect buy-intent sizing.

## Goal

Make runtime defaults, deployment configuration, docs, and local risk behavior
match the repository's published contracts.

## Non-Goals

- Do not add live Bybit execution.
- Do not change database schema or add Alembic.
- Do not create or update a remote GitHub issue without explicit user approval.
- Do not implement the full future v0.9 risk engine.

## Safety Invariants

- Bybit integration remains public/read-only except existing signed read-only
  account validation/sync flows.
- The system only writes local signal/order-intent/paper/backtest/replay records.
- `BYBIT_ALLOW_READ_WRITE_KEY=false` remains the default.
- The HTTP API remains GET/read-only.
- Recorder remains opt-in.

## Acceptance Criteria

- Default SQLite URL targets `/data/bot.db` as an absolute SQLite path.
- Package metadata, CI, container, AGENTS instructions, OpenSpec context, and
  docs all use Python 3.14 as the project baseline.
- Compose PostgreSQL healthcheck uses configured `POSTGRES_USER` and
  `POSTGRES_DB`.
- `MAX_POSITION_QUOTE_USDT` caps local buy-intent quote sizing.
- README, `.env.example`, and architecture docs match the implementation.
- Tests and verification gates pass.

## Links

- OpenSpec change: `openspec/changes/align-runtime-config-contracts`
- Pull request: TBD
