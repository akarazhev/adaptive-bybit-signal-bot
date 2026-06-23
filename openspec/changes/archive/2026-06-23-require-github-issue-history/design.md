## Context

The repository already requires OpenSpec-first development for changes that
affect behavior, persistence, API, runtime, deployment, safety, or repository
governance. OpenSpec is strong for machine-readable requirements and validation,
but a human maintainer still benefits from a GitHub issue that explains the
original problem, decision context, alternatives, and milestone history.

## Goals / Non-Goals

**Goals:**

- Add a durable English-language issue history step for SDD-scoped work.
- Keep OpenSpec as the technical contract and verification surface.
- Make PRs link both the GitHub issue and the OpenSpec change.
- Preserve the repository's external action boundary for GitHub writes.

**Non-Goals:**

- Do not require issues for typo fixes, formatting-only edits, or maintenance
  work that is already allowed to skip a new OpenSpec change.
- Do not add GitHub automation, workflow triggers, new tokens, or remote
  repository settings.
- Do not change runtime behavior or any Bybit-facing safety boundary.

## Decisions

- Use GitHub issues as the human history layer and OpenSpec as the normative
  contract. Alternative considered: store all history only in OpenSpec. That
  would keep requirements centralized, but it would make product rationale and
  discussion less visible to human maintainers.
- Require an issue or issue draft before implementation for SDD-scoped work.
  Alternative considered: require a remote issue only after PR creation. That
  misses the early decision context this change is intended to preserve.
- Update the existing feature request template instead of adding a new template.
  Feature requests are already the right GitHub entry point for proposed product
  and production-facing work.
- Treat remote issue creation/update as an explicit external write action.
  Agents can prepare issue bodies locally, but they must not post or edit
  GitHub issues unless the user approves the exact action.

## Risks / Trade-offs

- Issue clutter -> Limit the requirement to SDD-scoped work and keep small
  non-production maintenance exempt.
- Duplicate information between issues and OpenSpec -> Use the issue for
  context, goals, non-goals, acceptance criteria, and evolution; use OpenSpec
  for requirements, design, tasks, and validation.
- Remote write ambiguity -> Keep GitHub writes behind explicit user approval and
  allow local drafts when approval or authentication is unavailable.

## Migration Plan

Update the governance files and templates in one documentation/configuration
change. Rollback is a documentation/template revert; no database, runtime,
credential, or deployment rollback is required.

## Open Questions

None.
