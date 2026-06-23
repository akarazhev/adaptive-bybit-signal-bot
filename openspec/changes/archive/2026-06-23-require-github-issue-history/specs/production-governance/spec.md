## ADDED Requirements

### Requirement: GitHub Issues Capture Project Evolution
SDD-scoped feature and production-facing work SHALL start from a GitHub issue or
an explicitly prepared issue draft before implementation. The issue or draft
MUST capture human-readable context, goal, non-goals, safety invariants,
acceptance criteria, and links to the related OpenSpec change and pull request
when those artifacts exist. Remote issue creation or updates MUST NOT be
performed by an agent without explicit user approval.

#### Scenario: SDD-scoped work begins
- **GIVEN** a change affects behavior, persistence, API, runtime, deployment, safety, or repository governance
- **WHEN** a developer or agent starts planning the work
- **THEN** a GitHub issue exists or an issue draft is prepared before implementation
- **AND** the issue or draft records context, goal, non-goals, safety invariants, acceptance criteria, and OpenSpec/PR links when available.

#### Scenario: GitHub write approval is unavailable
- **GIVEN** remote GitHub issue creation or update has not been explicitly approved
- **WHEN** an agent prepares SDD-scoped work
- **THEN** the agent drafts the issue content locally or in the handoff
- **AND** the agent does not create or update the remote GitHub issue.

#### Scenario: Pull request is prepared
- **GIVEN** implementation work is ready for review
- **WHEN** a pull request body is written
- **THEN** the pull request links the GitHub issue or issue draft context
- **AND** the pull request links the related OpenSpec change when one exists.
