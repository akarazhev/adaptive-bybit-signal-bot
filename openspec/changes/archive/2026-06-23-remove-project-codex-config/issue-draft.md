## Title

Remove project-local `.codex` configuration

## Context

The repository previously tracked `.codex/` files that came from the ECC Codex
configuration. The active workflow is now centered on `AGENTS.md`, OpenSpec, and
Superpowers. Keeping `.codex/` adds a stale project-local agent configuration
surface even though the runtime and safety contracts are documented elsewhere.

## Goal

Remove tracked `.codex/` project-local configuration and update repository
documentation so future agents use `AGENTS.md`, OpenSpec, and Superpowers as the
active guidance surface.

## Non-Goals

- Do not remove `AGENTS.md`.
- Do not remove `.github/codex/` or the manual GitHub Codex review workflow.
- Do not change Python runtime behavior, exchange adapters, persistence, API,
  compose files, strategy logic, recorder/replay behavior, or CI.
- Do not create or update a remote GitHub issue without explicit approval.

## Safety Invariants

- Bybit integration remains public/read-only except existing signed read-only
  account validation/sync flows.
- The system only writes local signal/order-intent/paper/backtest/replay
  records.
- `BYBIT_ALLOW_READ_WRITE_KEY=false` remains the default.
- The HTTP API remains GET/read-only.
- Recorder remains opt-in.
- `.env` remains uninspected and unexposed.

## Acceptance Criteria

- `.codex/config.toml` and `.codex/agents/*.toml` are removed from the tracked
  tree.
- Active docs no longer list `.codex/` as an installed or expected local config
  directory.
- `AGENTS.md` remains the repository operating contract.
- OpenSpec validates successfully.

## Links

- OpenSpec change: `openspec/changes/remove-project-codex-config`
- Pull request: TBD
