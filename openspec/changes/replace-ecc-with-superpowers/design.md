## Context

The active agent workflow uses Superpowers. The repository still contains and
documents a legacy daily skill surface, which is now obsolete.

## Goals / Non-Goals

Goals:

- Remove legacy skill files and active references.
- Document Superpowers as the active skill workflow.
- Keep `.codex/` project-local configuration.
- Preserve all trading safety, SDD, issue-history, and verification rules.

Non-goals:

- No changes to bot runtime behavior.
- No exchange adapter, account sync, API, persistence, strategy, compose, or CI
  changes.
- No remote GitHub issue writes.
- No rewrite of archived OpenSpec history as if it never happened.

## Decisions

- Delete the local legacy skill directory.
- Replace the legacy configuration spec with a Superpowers/Codex configuration
  spec instead of leaving stale guidance.
- Update archived OpenSpec references that pointed at the old configuration
  document name.
- Treat the migration as repository governance work, so it gets an OpenSpec
  change and local issue draft.

## Safety Boundary

This change only affects agent workflow documentation and local skill files. It
does not add live Bybit execution, write endpoints, credential exposure,
recorder defaults, or live-network test requirements.

## Rollback

Rollback is documentation-only: restore the deleted legacy skill directory and
old configuration spec from git, then update `AGENTS.md` and `doc/spec/00_INDEX.md`
back to the previous wording.

## Open Questions

None.
