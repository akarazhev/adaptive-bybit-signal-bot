## 1. Planning

- [x] 1.1 Confirm user approval to remove `.codex/`.
- [x] 1.2 Prepare a local issue draft instead of creating a remote GitHub issue.
- [x] 1.3 Confirm the change does not touch runtime, exchange execution,
  persistence, API, compose, recorder/replay, or secrets.

## 2. Documentation And Configuration

- [x] 2.1 Remove tracked `.codex/config.toml`.
- [x] 2.2 Remove tracked `.codex/agents/*.toml`.
- [x] 2.3 Update `doc/spec/10_SUPERPOWERS_CODEX_CONFIGURATION.md` to document
  `AGENTS.md` as the active local agent contract and `.codex/` as removed.
- [x] 2.4 Update `doc/spec/00_INDEX.md` so the document description remains
  accurate.
- [x] 2.5 Update active OpenSpec planning references that still say `.codex/`
  remains preserved.
- [x] 2.6 Add a `production-governance` spec delta for centralized agent
  guidance.

## 3. Verification

- [x] 3.1 Search for active `.codex/` references.
- [x] 3.2 Run `openspec validate --all --strict --no-interactive`.
- [x] 3.3 Review git diff before handoff.
