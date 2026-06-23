# Runtime Deployment Consistency Specification

## Purpose
This specification keeps runtime defaults, deployment documentation, and local
risk-limit configuration aligned across standalone SQLite, container, and
PostgreSQL compose operation.

## Requirements
### Requirement: Runtime Defaults Match Deployment Documentation
The system SHALL keep default runtime settings aligned with documented local,
container, and compose operation.

#### Scenario: Standalone container SQLite uses the mounted data volume
- **GIVEN** the default SQLite database URL is used in a container
- **WHEN** SQLAlchemy parses the URL
- **THEN** the database path resolves to `/data/bot.db`
- **AND** the path is inside the documented `/data` volume.

#### Scenario: Python baseline is consistent across runtime surfaces
- **GIVEN** the project Python baseline is reviewed
- **WHEN** package metadata, CI, container, instructions, OpenSpec context, and docs are inspected
- **THEN** they use Python 3.14
- **AND** they do not document Python 3.12 as the current runtime baseline.

#### Scenario: Compose PostgreSQL healthcheck follows configured database identity
- **GIVEN** an operator overrides `POSTGRES_USER` or `POSTGRES_DB`
- **WHEN** the default compose stack starts
- **THEN** the PostgreSQL healthcheck uses the configured user and database
- **AND** it does not hardcode the default `bot/bybit_bot` identity.

### Requirement: Published Local Risk Limits Affect Buy Intent Sizing
Published local risk configuration SHALL constrain local order-intent sizing.

#### Scenario: Buy quote exceeds maximum position quote
- **GIVEN** `ORDER_QUOTE_USDT` after sentiment adjustment is greater than `MAX_POSITION_QUOTE_USDT`
- **WHEN** the strategy creates a local buy intent
- **THEN** the buy-intent quote exposure is capped to `MAX_POSITION_QUOTE_USDT`
- **AND** no Bybit order placement, cancellation, amendment, transfer, withdrawal, or leverage request is sent.
