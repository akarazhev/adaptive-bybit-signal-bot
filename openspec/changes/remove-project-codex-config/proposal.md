## Why

The repository still tracks `.codex/` project-local Codex configuration that
originated from the previous ECC setup. The active workflow now uses
`AGENTS.md`, OpenSpec, and Superpowers instructions, so retaining `.codex/`
creates an extra agent configuration surface with stale MCP and subagent
defaults.

Removing the directory reduces configuration drift while preserving the
repository's production safety, OpenSpec-first SDD, and GitHub Codex review
guidance.

## What Changes

- Remove tracked `.codex/config.toml` and `.codex/agents/*.toml` files.
- Update project documentation so it no longer lists `.codex/` as an installed
  or expected configuration directory.
- Keep `AGENTS.md` as the repository operating contract for Codex and
  Superpowers.
- Keep GitHub Codex review guidance under `.github/` unchanged.
- Update active OpenSpec planning notes that previously said `.codex/` should be
  preserved.

## Capabilities

### Modified Capabilities

- Production governance no longer includes a repository-local `.codex/`
  configuration directory as part of the active agent workflow surface.

## Impact

- Affected repository-governance surfaces: `.codex/`, `doc/spec/`, and
  OpenSpec planning artifacts.
- Affected runtime/deployment surfaces: none.
- Affected Python behavior, persistence, API, exchange adapters, account sync,
  order intents, paper trading, recorder/replay, and secrets: none.
- Safety boundary: unchanged; the bot remains read-only/order-intent only.
