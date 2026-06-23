## Title

Replace legacy project-local workflow with Superpowers

## Context

The repository was configured around a project-local legacy skill surface. The
active agent workflow now uses Superpowers skills, and stale legacy
files/instructions create conflicting guidance.

## Goal

Remove the legacy skill surface from active project configuration and
documentation, and document Superpowers as the active skill workflow while
preserving all production safety and governance rules.

## Non-Goals

- No bot runtime behavior changes.
- No exchange execution or account-write behavior.
- No API, persistence, compose, strategy, or CI changes.
- No remote GitHub issue update without explicit approval.

## Safety Invariants

- The bot remains read-only/order-intent only.
- `BYBIT_ALLOW_READ_WRITE_KEY=false` remains the default.
- `.env` remains private and must not be inspected or exposed.
- HTTP API endpoints remain GET/read-only by default.
- Recorder remains opt-in through its compose overlay.

## Acceptance Criteria

- Project-local legacy skill files are removed.
- Active docs no longer instruct agents to use the legacy skill surface.
- Superpowers is documented as the active skill workflow.
- Codex guidance remains centralized in `AGENTS.md`; the old `.codex/`
  project-local configuration surface can be removed separately.
- OpenSpec validates, or unavailable tooling is reported.

## Links

- OpenSpec change: `openspec/changes/replace-ecc-with-superpowers`
- PR: TBD
