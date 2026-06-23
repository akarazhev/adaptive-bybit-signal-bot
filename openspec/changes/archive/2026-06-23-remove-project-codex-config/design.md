## Context

`.codex/` was added as project ECC Codex configuration and later retained when
the repository moved to Superpowers as the active workflow surface. The user has
approved removing that tracked directory.

## Goals / Non-Goals

Goals:

- Delete the tracked project-local `.codex/` configuration files.
- Remove active documentation that presents `.codex/` as installed or required.
- Preserve `AGENTS.md`, OpenSpec-first SDD, GitHub issue-history rules,
  verification guidance, and the read-only/order-intent Bybit safety boundary.

Non-goals:

- No bot runtime behavior changes.
- No exchange, account sync, API, persistence, strategy, compose, recorder,
  replay, CI, or GitHub workflow changes.
- No remote GitHub issue writes.
- No removal of `AGENTS.md`, `.github/codex/`, or Codex review guidance.

## Decisions

- Remove only the project-local `.codex/` directory. This avoids touching the
  GitHub Codex review workflow, which is a separate trusted-maintainer review
  surface.
- Keep repository agent instructions centralized in `AGENTS.md`.
- Update `doc/spec/10_SUPERPOWERS_CODEX_CONFIGURATION.md` instead of renaming it
  in this change, because it still documents Superpowers and GitHub/Codex review
  configuration.
- Create a local issue draft rather than writing to GitHub remotely.

## Safety Boundary

This change only removes agent configuration files and updates documentation. It
does not add live Bybit execution, write endpoints, credential exposure,
recorder default changes, persistence behavior, or live-network test
requirements.

## Rollback

Rollback is documentation/configuration-only: restore `.codex/` from git and
revert the documentation and OpenSpec wording that marks project-local Codex
configuration as removed.

## Open Questions

None.
