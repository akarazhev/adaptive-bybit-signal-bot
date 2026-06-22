# Codex Pull Request Review

Review this pull request as a safety-critical Python trading-adjacent system.

Use repository guidance from `AGENTS.md`, `openspec/config.yaml`, and
`openspec/specs/*/spec.md`.

Focus only on serious issues:

- Any path that can place, cancel, amend, submit, transfer, withdraw, set
  leverage, or otherwise execute on Bybit.
- Any weakening of the read-only/order-intent safety boundary.
- Secret handling issues, especially `.env`, Bybit credentials, API keys, logs,
  and GitHub Actions secrets.
- New API endpoints that are not GET/read-only or lack explicit security review.
- Persistence changes that break SQLite standalone or PostgreSQL compose mode.
- Runtime, compose, or recorder changes that make high-volume recording default
  on, hide failure, or create unsafe restart/storage behavior.
- Missing tests or verification for behavior, safety, persistence, or
  deployment-sensitive changes.
- OpenSpec artifacts missing for behavior, API, persistence, runtime,
  deployment, or safety changes.

Do not flag style-only issues unless they hide a correctness, safety, or
operability problem. Do not recommend adding live exchange execution to this
repository.
