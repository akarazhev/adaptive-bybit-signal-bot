# Production Governance Specification

## Purpose
This specification defines how OpenSpec should guide production-ready changes in this repository. It turns the repo's safety, verification, deployment, and documentation expectations into a durable planning contract.

## Requirements

### Requirement: Spec-Driven Development Gates Production-Facing Changes
Production-facing changes SHALL follow Spec-Driven Development through OpenSpec before implementation.

#### Scenario: SDD-scoped work begins
- **GIVEN** a change affects behavior, persistence, API, runtime, deployment, safety, or repository governance
- **WHEN** a developer or agent starts implementation work
- **THEN** OpenSpec proposal, design, or task artifacts are created or updated before source changes
- **AND** the artifacts identify safety boundary impact, required tests, verification commands, and documentation updates.

#### Scenario: Non-production maintenance skips a new OpenSpec change
- **GIVEN** a documentation, formatting, or test-maintenance change does not alter product behavior, production operation, safety guarantees, or governance rules
- **WHEN** the change is prepared
- **THEN** a new OpenSpec change is not required
- **AND** existing source specs remain accurate after the change.

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

### Requirement: GitHub Automation Gates Production Changes
The repository SHALL provide GitHub configuration that validates OpenSpec artifacts, Python quality gates, security analysis, and container build readiness before production-facing changes are merged.

#### Scenario: Pull request validation runs
- **GIVEN** a pull request targets `main`
- **WHEN** GitHub Actions runs the repository CI workflow
- **THEN** the workflow validates OpenSpec artifacts
- **AND** it runs compileall, pytest, ruff, mypy, and a container build without requiring live Bybit or Alternative.me credentials.

#### Scenario: Dependency updates are monitored
- **GIVEN** dependencies are declared in Python, GitHub Actions, or container configuration
- **WHEN** Dependabot checks the repository schedule
- **THEN** dependency update pull requests can be opened for review
- **AND** those pull requests use the same CI and safety review expectations as ordinary changes.

### Requirement: Codex Review Uses Repository Safety Guidance
Codex review in GitHub SHALL use repository guidance that focuses on serious safety, security, correctness, persistence, and deployment risks.

#### Scenario: Maintainer requests Codex review
- **GIVEN** a maintainer runs the Codex review workflow or requests `@codex review` through Codex cloud
- **WHEN** Codex reviews the pull request
- **THEN** it follows the Review Guidelines in `AGENTS.md`
- **AND** it prioritizes issues that could violate the read-only/order-intent boundary, expose secrets, break persistence modes, weaken API safety, or remove required verification.
