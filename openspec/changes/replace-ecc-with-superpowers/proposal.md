## Why

The repository was previously configured around a project-local legacy skill
surface. The active workflow now uses Superpowers skills, and the user requested
complete removal of the legacy surface from the project.

Keeping stale legacy files and instructions creates conflicting agent guidance
and makes the project harder to operate consistently.

## What Changes

- Remove project-local legacy skill files.
- Replace active legacy references in repository instructions with Superpowers
  workflow guidance.
- Replace the legacy Codex configuration spec with a Superpowers/Codex
  configuration spec.
- Keep `.codex/` as the project-local Codex configuration directory.
- Preserve OpenSpec-first SDD, GitHub issue-history rules, verification gates,
  and the read-only/order-intent Bybit safety boundary.

## Capabilities

### Modified Capabilities

- Production governance now documents Superpowers as the active agent workflow
  surface.

## Impact

- Affected docs: `AGENTS.md`, `doc/spec/00_INDEX.md`, configuration spec docs.
- Affected repository files: local legacy skill directory deletion.
- No Python runtime, persistence, API, compose, strategy, exchange, or CI
  behavior changes.
- Safety boundary: unchanged; the bot remains read-only/order-intent only.
