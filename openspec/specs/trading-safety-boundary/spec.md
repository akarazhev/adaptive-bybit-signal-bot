# Trading Safety Boundary Specification

## Purpose
This specification defines the production safety boundary for the Bybit-facing bot. The system may observe markets, calculate signals, and write local records, but it must not execute trades or asset movements on Bybit.

## Requirements

### Requirement: Exchange Execution Is Out Of Scope
The system SHALL keep Bybit exchange integration read-only and MUST NOT expose in-repository methods or workflows that place, cancel, amend, submit, transfer, withdraw, or set leverage on Bybit.

#### Scenario: Exchange client remains read-only
- **GIVEN** a change touches `src/adaptive_bybit_bot/exchange`
- **WHEN** the change is reviewed
- **THEN** the exchange client does not include direct execution methods
- **AND** the allowed Bybit interactions remain public market reads or signed read-only account validation and sync.

#### Scenario: Strategy creates local intent only
- **GIVEN** the strategy decides that market conditions warrant action
- **WHEN** the strategy result is persisted
- **THEN** the system writes local signal and order-intent records
- **AND** no Bybit order placement, cancellation, amendment, transfer, withdrawal, or leverage request is sent.

### Requirement: Credentials Stay Environment-Scoped
The system SHALL load private exchange credentials from environment-backed settings and MUST NOT inspect, print, commit, or document real local secrets.

#### Scenario: Local environment file is private
- **GIVEN** a developer has a local `.env` file
- **WHEN** OpenSpec artifacts, docs, tests, logs, or CLI output are produced
- **THEN** they do not include real secrets or values copied from `.env`
- **AND** `.env.example` remains the documentation surface for expected configuration names.

#### Scenario: Read-write key override remains exceptional
- **GIVEN** a Bybit key is not read-only
- **WHEN** account sync or validation is requested
- **THEN** the system refuses by default
- **AND** `BYBIT_ALLOW_READ_WRITE_KEY=true` remains an explicit exceptional override that requires security review before any default or documentation change.

### Requirement: API Surface Is Read-Only By Default
The HTTP API SHALL remain a read-only presentation surface unless a future write endpoint is explicitly requested and approved through security review.

#### Scenario: New endpoint is proposed
- **GIVEN** a change adds an HTTP endpoint
- **WHEN** the endpoint behavior is specified
- **THEN** the endpoint is GET/read-only by default
- **AND** any state-changing endpoint includes explicit authorization, validation, rate-limit, and safety-review requirements before implementation.

### Requirement: Recorder Remains Opt-In
The high-volume market recorder SHALL remain opt-in through the recorder-specific compose overlay or explicit CLI command.

#### Scenario: Default compose stack starts
- **GIVEN** an operator starts the default compose stack
- **WHEN** services are created from `compose.yaml`
- **THEN** the market recorder is not enabled by default
- **AND** high-volume recording requires an explicit recorder overlay or command.
