## ADDED Requirements

### Requirement: Repository Agent Guidance Uses AGENTS Contract
Repository-local agent guidance SHALL be centralized in `AGENTS.md` and OpenSpec
rather than requiring a tracked `.codex/` configuration directory.

#### Scenario: Agent starts work in the repository
- **GIVEN** an agent or maintainer inspects repository-local guidance
- **WHEN** they review the active workflow surfaces
- **THEN** `AGENTS.md` provides the repository operating contract
- **AND** OpenSpec provides the SDD planning contract
- **AND** the repository does not require tracked `.codex/config.toml` or
  `.codex/agents/*.toml` files for normal operation.
