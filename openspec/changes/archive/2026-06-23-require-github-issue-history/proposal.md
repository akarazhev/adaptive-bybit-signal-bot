## Why

OpenSpec captures the implementation contract, but GitHub issues provide a more
human-readable history of why a feature existed, how the decision evolved, and
what acceptance criteria were understood before implementation. Adding an issue
history layer makes future project evolution easier to audit without replacing
OpenSpec as the source of technical requirements.

## What Changes

- Require SDD-scoped feature and production-facing work to start from a GitHub
  issue or an explicitly prepared issue draft before implementation.
- Keep OpenSpec as the normative planning/specification layer; GitHub issues
  capture context, goals, non-goals, acceptance criteria, safety invariants, and
  links to the OpenSpec change and PR.
- Update repository instructions, OpenSpec governance, issue template, PR
  template, and Codex configuration docs in English.
- Preserve the external action boundary: agents may draft issue content freely,
  but they must not create or update GitHub issues without explicit user
  approval.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `production-governance`: require GitHub issue history for SDD-scoped work and
  define how issue drafts behave when remote GitHub writes are not approved.

## Impact

- Affected governance surfaces: `AGENTS.md`, `openspec/config.yaml`,
  `openspec/specs/production-governance/spec.md`, `.github/ISSUE_TEMPLATE`,
  `.github/pull_request_template.md`, and `doc/spec/10_ECC_CODEX_CONFIGURATION.md`.
- No runtime code, API, persistence, compose, exchange adapter, credential, or
  trading-safety behavior changes.
