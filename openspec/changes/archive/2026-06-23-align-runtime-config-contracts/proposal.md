## Why

The current implementation has several runtime-contract drifts: the standalone
SQLite URL points at a relative path while container docs mount `/data`, the
container image uses a different Python version than the project baseline and
CI, the PostgreSQL healthcheck ignores configured compose credentials, and the
published maximum position quote setting is not enforced by buy-intent sizing.

These are production-facing inconsistencies because they affect persistence,
container reproducibility, compose health, and local order-intent risk bounds.

## What Changes

- Make the default SQLite URL target the `/data` volume with an absolute SQLite
  path.
- Move the project baseline, CI, and production container base image to Python
  3.14.
- Make the PostgreSQL healthcheck honor configured `POSTGRES_USER` and
  `POSTGRES_DB` values.
- Enforce `MAX_POSITION_QUOTE_USDT` when sizing local buy intents.
- Update README, `.env.example`, and architecture docs so operator-facing
  examples match implementation.

## Capabilities

### New Capabilities

- `runtime-deployment-consistency`: runtime defaults, compose healthchecks, and
  documented risk settings stay aligned with implementation.

### Modified Capabilities

- None.

## Impact

- Affected runtime/deployment surfaces: `pyproject.toml`, `Containerfile`,
  `.github/workflows/ci.yml`, `compose.yaml`, `.env.example`,
  `src/adaptive_bybit_bot/config.py`, and docs.
- Affected strategy surface: local buy-intent sizing caps order quote exposure
  to `MAX_POSITION_QUOTE_USDT`.
- Persistence compatibility: no schema change; SQLite standalone and
  PostgreSQL compose modes remain supported.
- Safety boundary: no Bybit execution path is added; the system still writes
  only local signal/order-intent records.
