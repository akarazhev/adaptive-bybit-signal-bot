# ECC/Codex Configuration

This document records the project-specific ECC install decision for Codex.

## Stack Evidence

| Evidence | Meaning |
|---|---|
| `pyproject.toml` declares Python `>=3.12`, hatchling, pytest, ruff, mypy | Python service with typed quality gates |
| `pyproject.toml` dependencies include FastAPI, Typer, SQLAlchemy, pydantic-settings, httpx, websockets | CLI/API/data/exchange service |
| `README.md` and `doc/spec/09_CODEX_CLI_HANDOFF.md` state read-only/order-intent safety rules | Safety-critical trading-adjacent repo |
| `Containerfile`, `compose.yaml`, `compose.rest.yaml`, `compose.recorder.yaml` | Podman container and compose deployment |
| `src/adaptive_bybit_bot/{api,data,exchange,features,recording,sentiment,services,strategy}` | Ports/adapters service layout |
| `tests/` contains 24 pytest files | Unit/smoke coverage is a daily workflow |

## DAILY ECC Surface

These skills are installed under `.agents/skills/` because they match the daily
work for this repository.

| Component | Type | Bucket | Evidence | Reason |
|---|---|---|---|---|
| `skills/tdd-workflow` | skill | DAILY | pytest suite and roadmap-driven feature work | tests before behavior changes |
| `skills/verification-loop` | skill | DAILY | README/spec require pytest, compileall, ruff, mypy | repeatable handoff checks |
| `skills/python-patterns` | skill | DAILY | Python package under `src/` | primary language |
| `skills/python-testing` | skill | DAILY | 24 pytest files | primary test workflow |
| `skills/fastapi-patterns` | skill | DAILY | `src/adaptive_bybit_bot/api/app.py` | API is FastAPI |
| `skills/api-design` | skill | DAILY | read-only HTTP API in README/spec | endpoint design and response hygiene |
| `skills/security-review` | skill | DAILY | `.env.example`, Bybit credentials, financial safety | security-sensitive boundaries |
| `skills/llm-trading-agent-security` | skill | DAILY | trading-adjacent automation and explicit no-execution invariant | asset-loss threat model, adapted to read-only mode |
| `skills/database-migrations` | skill | DAILY | SQLAlchemy models and SQLite/PostgreSQL support | persistence changes need schema discipline |
| `skills/docker-patterns` | skill | DAILY | `Containerfile` and compose files | container/deployment work |
| `skills/deployment-patterns` | skill | DAILY | Podman compose production mode | release/runtime changes |
| `skills/coding-standards` | skill | DAILY | strict mypy/ruff and modular service architecture | cross-cutting maintainability |

## LIBRARY Surface

These remain searchable in the upstream ECC checkout or can be added later, but
they are not loaded daily because current repo evidence does not justify them.

| Component family | Bucket | Evidence | Reason |
|---|---|---|---|
| Frontend/browser/Playwright skills | LIBRARY | no frontend app or browser tests | not active yet |
| Django/Laravel/Spring/Next/React/Vue skills | LIBRARY | no matching framework files | off-stack |
| Kubernetes/cloud-provider skills | LIBRARY | Podman compose only | deployment surface is smaller |
| Social/content/investor/operator skills | LIBRARY | no repo workflow evidence | not engineering daily work |
| OpenCode/Claude hook runtime | LIBRARY | requested target is Codex | avoid incompatible hook surface |

## Installed Files

- `AGENTS.md` - project operating contract for Codex.
- `.codex/config.toml` - project-local Codex defaults, MCP servers, and agent roles.
- `.codex/agents/*.toml` - read-only explorer/reviewer/docs-researcher roles.
- `.agents/skills/*` - selected ECC daily skills.
- `openspec/config.yaml` - project-specific OpenSpec context and artifact rules
  for production-ready planning.
- `openspec/specs/*/spec.md` - source specifications for the trading safety
  boundary and production governance.

## OpenSpec Production Configuration

OpenSpec is configured as the planning layer for production-facing changes. Its
context encodes the read-only/order-intent Bybit safety invariant, Python/FastAPI
stack, SQLite/PostgreSQL runtime modes, Podman deployment surface, and required
verification gates.

The current OpenSpec CLI verification baseline is `1.4.1`. After upgrading the
OpenSpec CLI, rerun `openspec update --force` from this repository so the
generated Codex prompts under `CODEX_HOME`/`~/.codex/prompts` are refreshed.

For new behavior, persistence, API, runtime, deployment, or safety changes:

```bash
openspec validate --all --strict --no-interactive
```

Use `/opsx:propose` or the equivalent OpenSpec CLI workflow before implementation
so proposals, specs, designs, and tasks inherit the repository safety and
production-readiness rules.

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
