# Superpowers/Codex Configuration

This document records the project-specific Superpowers and Codex configuration
for `adaptive-bybit-signal-bot`.

## Stack Evidence

| Evidence | Meaning |
|---|---|
| `pyproject.toml` declares Python `>=3.14`, hatchling, pytest, ruff, mypy | Python service with typed quality gates |
| `pyproject.toml` dependencies include FastAPI, Typer, SQLAlchemy, pydantic-settings, httpx, websockets | CLI/API/data/exchange service |
| `README.md` and `doc/spec/09_CODEX_CLI_HANDOFF.md` state read-only/order-intent safety rules | Safety-critical trading-adjacent repo |
| `Containerfile`, `compose.yaml`, `compose.rest.yaml`, `compose.recorder.yaml` | Podman container and compose deployment |
| `src/adaptive_bybit_bot/{api,data,exchange,features,recording,sentiment,services,strategy}` | Ports/adapters service layout |
| `tests/` contains pytest coverage for exchange, strategy, persistence, API, services, backtesting, recording, replay, and sentiment | Unit/smoke coverage is a daily workflow |

## Active Agent Workflow

Superpowers skills are the active workflow surface. Agents should use the
relevant Superpowers skill before task actions when a skill applies.

The daily workflow expectations are:

- brainstorming and writing-plans for scoped design and planning;
- test-driven-development for behavior changes and bug fixes;
- systematic-debugging for bugs, failing tests, and unexpected behavior;
- verification-before-completion before claiming work is complete;
- requesting-code-review and receiving-code-review for substantial changes;
- using-git-worktrees when isolation is appropriate;
- finishing-a-development-branch when implementation is complete and verified.

Project-local legacy skill bundles are not part of this repository. Do not
restore one unless the user explicitly approves a new agent-surface decision.

## Installed Files

- `AGENTS.md` - project operating contract for Codex and Superpowers.
- `.codex/config.toml` - project-local Codex defaults, MCP servers, and agent roles.
- `.codex/agents/*.toml` - read-only explorer/reviewer/docs-researcher roles.
- `openspec/config.yaml` - project-specific OpenSpec context and artifact rules
  for production-ready planning.
- `openspec/specs/*/spec.md` - source specifications for the trading safety
  boundary and production governance.
- `.github/workflows/ci.yml` - GitHub Actions gate for OpenSpec validation,
  compileall, pytest, ruff, mypy, and container build.
- `.github/workflows/codeql.yml` - CodeQL analysis for Python.
- `.github/workflows/codex-review.yml` and `.github/codex/prompts/review.md` -
  manual Codex review workflow for trusted maintainers with `OPENAI_API_KEY`.
- `.github/dependabot.yml` - weekly dependency update checks for Python,
  GitHub Actions, and container dependencies.
- `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/*`,
  `.github/CODEOWNERS`, and `.github/SECURITY.md` - GitHub collaboration,
  ownership, and reporting surfaces.

## OpenSpec Production Configuration

OpenSpec is configured as the planning layer for production-facing changes. Its
context encodes the read-only/order-intent Bybit safety invariant, Python/FastAPI
stack, SQLite/PostgreSQL runtime modes, Podman deployment surface, and required
verification gates.

This repository treats OpenSpec as the mandatory Spec-Driven Development (SDD)
surface for production-facing work. Changes that affect behavior, persistence,
API, runtime, deployment, safety, or repository governance must update or create
OpenSpec proposal/design/task artifacts before implementation begins. Small
documentation, formatting, or test-maintenance edits can skip a new OpenSpec
change only when they do not alter product behavior, production operation,
safety guarantees, or governance rules.

For new behavior, persistence, API, runtime, deployment, or safety changes:

```bash
openspec validate --all --strict --no-interactive
```

Use `/opsx:propose` or the equivalent OpenSpec CLI workflow before implementation
so proposals, specs, designs, and tasks inherit the repository safety and
production-readiness rules.

## GitHub Issue History Layer

GitHub issues are the human-readable history layer for SDD-scoped feature and
production-facing work. Before implementation begins, create or link a GitHub
issue, or prepare an English issue draft when remote GitHub writes are not
approved or authenticated.

The issue or draft should capture:

- context and motivation;
- goal and non-goals;
- safety invariants;
- acceptance criteria;
- links to the OpenSpec change and pull request when they exist;
- milestone updates such as OpenSpec created, tests added, implementation
  complete, verification passed, and docs updated.

OpenSpec remains the technical contract. The issue explains why the change
exists and preserves the project-evolution trail for human maintainers.

Agents must not create or update remote GitHub issues without explicit user
approval for that external write action. When approval is absent, they should
draft the issue body locally or include it in the handoff.

## GitHub/Codex Production Configuration

The repository-local GitHub configuration is designed to be safe without remote
administrator state:

- CI runs offline-safe validation and does not use live Bybit or Alternative.me
  access.
- CodeQL runs with read-only contents and `security-events: write`.
- The Codex review workflow is manual (`workflow_dispatch`) so trusted
  maintainers decide when to spend API budget and expose the pull request to
  Codex. It requires `OPENAI_API_KEY` as a repository secret.
- Codex review also uses `AGENTS.md` Review Guidelines and
  `.github/codex/prompts/review.md` to focus on production safety issues.
- Remote repository controls such as branch protection, required status checks,
  GitHub secret creation, and Codex cloud automatic reviews still need an
  authenticated GitHub session or repository administrator action.

Recommended remote follow-up after `gh auth login`:

```bash
gh secret set OPENAI_API_KEY
```

Then configure branch protection in GitHub settings to require the CI jobs
`Python checks`, `Container build`, and CodeQL analysis before merging to
`main`. Enable Codex cloud code review and automatic reviews from Codex settings
when the repository is connected to Codex cloud.

## Verification Expectation

For ordinary code changes, run:

```bash
PYTHONPATH=src pytest
python -m compileall -q src tests
ruff check .
mypy src
```

For deployment changes, add:

```bash
podman build -t adaptive-bybit-signal-bot -f Containerfile .
podman compose config
```

Do not treat live Bybit or Alternative.me access as required verification unless
the task explicitly needs integration behavior.
