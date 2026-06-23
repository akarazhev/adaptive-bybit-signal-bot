## MODIFIED Requirements

### Requirement: OpenSpec Artifacts Carry Production Context
OpenSpec planning artifacts SHALL include project-specific context for the Python stack, Bybit safety boundary, supported runtimes, verification gates, deployment surfaces, and the active Superpowers agent workflow.

#### Scenario: A new proposal is created
- **GIVEN** a developer or agent starts an OpenSpec change
- **WHEN** proposal, spec, design, or task instructions are requested
- **THEN** the instructions include the repository's read-only/order-intent safety model
- **AND** the instructions include the required production verification and deployment considerations
- **AND** active agent-workflow guidance points to Superpowers.
