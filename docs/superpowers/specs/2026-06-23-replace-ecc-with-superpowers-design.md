# Replace Legacy Agent Skills With Superpowers Design

## Context

The repository previously documented a project-local legacy agent skill bundle.
The active agent runtime now uses Superpowers skills, and the user requested a
complete removal of the legacy bundle from the project.

This is a governance and agent-configuration change only. It must not alter bot
runtime behavior, exchange access, strategy logic, persistence, compose topology,
or tests.

## Goals

- Remove project-local legacy skill files.
- Remove active legacy skill references from repository instructions and docs.
- Keep `.codex/` as the project-local Codex configuration directory.
- Document Superpowers as the active skill workflow surface.
- Preserve the repository's read-only/order-intent safety boundary.

## Non-Goals

- No changes to Python source code.
- No changes to runtime settings, compose services, CI behavior, or API routes.
- No remote GitHub issue creation.
- No rewrite of archived OpenSpec history, except leaving it as historical record.

## Design

`AGENTS.md` becomes the active instruction surface for Codex with Superpowers.
It keeps the same project stack, OpenSpec-first SDD rules, GitHub issue-history
rules, review guidelines, safety invariants, workflow, and verification commands.
Only the legacy daily-skills section is replaced by Superpowers usage guidance.

The old configuration document is replaced with a Superpowers/Codex
configuration document under a new filename. `doc/spec/00_INDEX.md` is updated
to reference the new document.

The legacy local skill directory is removed. The `.codex/` directory remains
because it is project-local Codex configuration.

## Safety Boundary

The change does not add exchange execution, credentials handling, HTTP write
endpoints, persistence workflows, compose services, recorder defaults, or network
test requirements. The read-only/order-intent boundary remains unchanged.

## Verification

- Search for active legacy skill references.
- Parse TOML configuration.
- Run `openspec validate --all --strict --no-interactive` when available.
- Review `git diff` before handoff.
