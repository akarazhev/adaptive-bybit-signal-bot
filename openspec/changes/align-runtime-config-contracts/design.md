## Context

The repository is moving to Python 3.14 as its full runtime baseline. It also
documents a `/data` container volume for standalone SQLite, parameterized PostgreSQL compose credentials, and a
`MAX_POSITION_QUOTE_USDT` risk setting. The code should make those contracts
observable instead of depending on operator interpretation.

## Goals / Non-Goals

**Goals:**

- Preserve standalone SQLite persistence under the mounted `/data` volume.
- Keep package metadata, container, CI, instructions, and docs on a consistent
  Python 3.14 baseline.
- Keep compose healthchecks valid when operators override `POSTGRES_USER` or
  `POSTGRES_DB`.
- Ensure the documented maximum position quote setting constrains new local
  buy intents.
- Add regression tests for the drift points.

**Non-Goals:**

- Do not add Alembic or any database schema migration layer.
- Do not change PostgreSQL table definitions or stored data.
- Do not add live Bybit execution, order placement, cancellation, or transfer
  behavior.
- Do not add a full v0.9 risk engine.

## Decisions

- Use `sqlite:////data/bot.db` for container/default SQLite. SQLAlchemy parses
  `sqlite:///data/bot.db` as relative `data/bot.db`, while four slashes target
  absolute `/data/bot.db`.
- Use `python:3.14-slim` in the container and set CI/package metadata to Python
  3.14 so the runtime baseline is explicit and consistent.
- Use escaped shell variables in the compose healthcheck so Docker/Podman
  Compose passes `POSTGRES_USER` and `POSTGRES_DB` through to the container.
- Cap local buy-intent quote size to `max_position_quote_usdt` before quantity
  normalization. This preserves default behavior because the default order
  quote is lower than the default maximum position quote.

## Risks / Trade-offs

- Operators relying on the previous relative SQLite path may need to move a
  local `data/bot.db` file manually. Containerized standalone runs become safer
  because the documented `/data` volume now actually holds the DB.
- Capping buy-intent size changes behavior only for configurations where
  `ORDER_QUOTE_USDT` after sentiment adjustment exceeds
  `MAX_POSITION_QUOTE_USDT`.
- The compose healthcheck keeps default behavior unchanged but becomes more
  accurate for custom Postgres settings.

## Migration Plan

No schema migration or backfill is required. Rollback is a config/code/doc
revert. If a standalone operator previously created a DB at relative
`data/bot.db`, they can copy that file to `/data/bot.db` or set
`DATABASE_URL=sqlite:///data/bot.db` explicitly to retain old behavior.

## Open Questions

None.
