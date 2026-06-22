# Production Governance Specification

## Purpose
This specification defines how OpenSpec should guide production-ready changes in this repository. It turns the repo's safety, verification, deployment, and documentation expectations into a durable planning contract.

## Requirements

### Requirement: OpenSpec Artifacts Carry Production Context
OpenSpec planning artifacts SHALL include project-specific context for the Python stack, Bybit safety boundary, supported runtimes, verification gates, and deployment surfaces.

#### Scenario: A new proposal is created
- **GIVEN** a developer or agent starts an OpenSpec change
- **WHEN** proposal, spec, design, or task instructions are requested
- **THEN** the instructions include the repository's read-only/order-intent safety model
- **AND** the instructions include the required production verification and deployment considerations.

### Requirement: Verification Gates Are Explicit
Implementation tasks SHALL identify the verification commands required before handoff.

#### Scenario: Ordinary code behavior changes
- **GIVEN** a change modifies Python behavior
- **WHEN** tasks are written
- **THEN** they include `PYTHONPATH=src pytest`
- **AND** they include `python -m compileall -q src tests`
- **AND** they include `ruff check .`
- **AND** they include `mypy src`.

#### Scenario: Deployment files change
- **GIVEN** a change modifies `Containerfile` or compose files
- **WHEN** tasks are written
- **THEN** they include container and compose verification commands
- **AND** they describe health, restart, resource, storage, and rollback considerations.

### Requirement: Persistence Changes Include Compatibility Reasoning
Persistence changes SHALL explain compatibility across SQLite standalone mode and PostgreSQL compose mode.

#### Scenario: Repository or ORM schema changes
- **GIVEN** a change modifies data models, repositories, or schema initialization
- **WHEN** design and tasks are written
- **THEN** they explain SQLite and PostgreSQL behavior
- **AND** they include migration, backfill, rollback, and test coverage expectations.

### Requirement: Documentation Tracks Operational Changes
Changes that affect architecture, safety guarantees, runtime commands, compose topology, or roadmap behavior SHALL update the existing `doc/spec/` documentation.

#### Scenario: Runtime topology changes
- **GIVEN** a change adds, removes, or changes a long-running service
- **WHEN** the change is completed
- **THEN** the current architecture or handoff docs are updated
- **AND** the README run instructions remain accurate for local, container, and compose usage.
