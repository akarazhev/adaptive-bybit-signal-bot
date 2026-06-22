# Codex CLI handoff — как продолжать разработку

## Стартовый контекст для агента

Проект: `adaptive-bybit-signal-bot`.

Текущая версия: `0.6.0`.

Текущий главный архив: `adaptive-bybit-signal-bot-v0.6.zip`.

Назначение:

```text
Read-only/order-intent Bybit Spot bot for BTC/ETH.
It analyzes public/read-only data, classifies regimes, writes local order intents, supports paper/backtest/replay, and runs in Podman Compose.
```

Главный запрет:

```text
Do not add direct order placement/cancel/amend/withdraw/transfer functionality.
```

## Рекомендуемый prompt для Codex CLI

Можно дать агенту такой стартовый prompt:

```text
Ты работаешь над Python-проектом adaptive-bybit-signal-bot v0.6.
Прочитай README.md, pyproject.toml и doc/spec/*.md.
Сохрани safety-инвариант: бот не размещает/отменяет/изменяет ордера на Bybit, только пишет локальные order intents.
Следующая задача: реализовать v0.7 Strategy Metrics & Reporting согласно 08_NEXT_ROADMAP_V0.7_PLUS.md.
Сначала создай план, затем внеси изменения маленькими коммитоподобными шагами.
После изменений запусти pytest, compileall и CLI smoke tests.
Не ломай SQLite standalone и PostgreSQL compose режимы.
```

## Локальная распаковка и установка

```bash
unzip adaptive-bybit-signal-bot-v0.6.zip
cd adaptive-bybit-signal-bot
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Если dev extras недоступны, минимально:

```bash
pip install -e . pytest
```

## Базовые проверки перед изменениями

```bash
pytest
python -m compileall -q src tests
python -m adaptive_bybit_bot.cli --help
python -m adaptive_bybit_bot.cli init-db
```

Опционально:

```bash
ruff check .
mypy src
```

Примечание: `ruff` и `mypy` настроены в `pyproject.toml`, но в ранее использованной среде могли быть не установлены.

## Быстрый локальный smoke flow

```bash
cp .env.example .env
adaptive-bybit-bot init-db
adaptive-bybit-bot list-signals
adaptive-bybit-bot list-intents
adaptive-bybit-bot list-services
adaptive-bybit-bot list-locks
```

Без live Bybit можно запускать unit tests и offline tests.

С live public internet/API можно дополнительно:

```bash
adaptive-bybit-bot refresh-instruments --symbols BTCUSDT,ETHUSDT
adaptive-bybit-bot fetch-fng --limit 30
adaptive-bybit-bot run-once --symbol BTCUSDT
```

## Podman commands

Build:

```bash
podman build -t adaptive-bybit-signal-bot -f Containerfile .
```

Standalone SQLite:

```bash
podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot init-db
podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot run-once --symbol BTCUSDT
```

Compose stack:

```bash
podman compose up --build
```

Recorder overlay:

```bash
podman compose -f compose.yaml -f compose.recorder.yaml up --build postgres migrate api market-recorder
```

REST writer override:

```bash
podman compose -f compose.yaml -f compose.rest.yaml up --build postgres migrate api bot-rest
```

## Important files to inspect first

```text
README.md
pyproject.toml
.env.example
compose.yaml
compose.rest.yaml
compose.recorder.yaml
src/adaptive_bybit_bot/cli.py
src/adaptive_bybit_bot/config.py
src/adaptive_bybit_bot/domain/models.py
src/adaptive_bybit_bot/domain/enums.py
src/adaptive_bybit_bot/data/models.py
src/adaptive_bybit_bot/data/repositories.py
src/adaptive_bybit_bot/strategy/strategy.py
src/adaptive_bybit_bot/services/runtime.py
src/adaptive_bybit_bot/recording/replay.py
```

## Current tests

Test files:

```text
tests/test_indicators.py
tests/test_regime.py
tests/test_strategy.py
tests/test_strategy_more.py
tests/test_repository.py
tests/test_repository_more.py
tests/test_signing.py
tests/test_instruments.py
tests/test_paper_trading.py
tests/test_instrument_spec.py
tests/test_bybit_instruments.py
tests/test_local_orderbook.py
tests/test_backtesting.py
tests/test_cli_smoke.py
tests/test_db.py
tests/test_exchange_client.py
tests/test_feature_engine_more.py
tests/test_historical_klines.py
tests/test_sentiment.py
tests/test_service_runtime.py
tests/test_services.py
tests/test_maintenance.py
tests/test_api_config_cli.py
tests/test_recording_replay.py
```

v0.6 baseline:

```text
82 passed
```

## Coding conventions

Follow existing style:

```text
- Python 3.12;
- type hints everywhere feasible;
- dataclasses for domain models;
- Pydantic settings for config;
- SQLAlchemy ORM for persistence;
- Typer for CLI;
- FastAPI for read-only API;
- Rich for terminal tables;
- pure functions for calculations when possible;
- repository methods for DB operations;
- no live network calls in unit tests unless explicitly integration-marked.
```

## Safe development rules

### Never add these methods to BybitRestClient

```text
place_order
cancel_order
amend_order
create_order
submit_order
withdraw
transfer
set_leverage
```

If a future external executor is needed, implement it as a separate component/package and keep this bot read-only.

### Do not put secrets in repo

`.env.example` may contain empty placeholders only.

Do not commit:

```text
.env
real API keys
recording files with private data
SQLite db files
```

### Do not make recorder default-on

Recorder can create large files. Keep it in optional compose overlay.

### Keep API read-only

New endpoints should be GET/read-only unless there is a strong reason and explicit safety review.

## Recommended v0.7 implementation plan

### Step 1 — Create metrics package

```text
src/adaptive_bybit_bot/metrics/
  __init__.py
  models.py
  calculations.py
  service.py
  reports.py
```

### Step 2 — Add pure calculation tests

Create:

```text
tests/test_metrics_calculations.py
```

Cover:

```text
net PnL
fees
win rate
profit factor
max drawdown
fill rate
forward returns
bucket aggregation
```

### Step 3 — Add repository helpers

In `data/repositories.py`, add read methods as needed:

```text
list_signals_between(symbol, start, end)
list_order_intents_between(symbol, start, end)
list_backtest_fills(run_id)
get_backtest_run(run_id)
list_market_replay_fills(run_id)
get_market_replay_run(run_id)
```

Prefer adding read-only methods only.

### Step 4 — Add report service

Implement:

```text
MetricsService.evaluate_backtest(run_id)
MetricsService.evaluate_replay(run_id)
MetricsService.evaluate_signals(...)
```

Return typed report model.

### Step 5 — Add CLI

Add commands:

```bash
adaptive-bybit-bot evaluate-backtest --run-id <id>
adaptive-bybit-bot evaluate-replay --run-id <id>
adaptive-bybit-bot strategy-report --source replay --run-id <id> --format markdown
```

### Step 6 — Add API

Add read-only endpoints:

```text
GET /metrics/backtests/{run_id}
GET /metrics/replays/{run_id}
```

### Step 7 — Update docs/config/version

Update:

```text
README.md
pyproject.toml version to 0.7.0
.env.example only if new config needed
```

### Step 8 — Run checks

```bash
pytest
python -m compileall -q src tests
python -m adaptive_bybit_bot.cli --help
python -m adaptive_bybit_bot.cli evaluate-replay --help
python -m adaptive_bybit_bot.cli evaluate-backtest --help
```

## v0.7 report model proposal

```python
@dataclass(frozen=True)
class PnLMetrics:
    gross_pnl_quote: float
    fees_quote: float
    net_pnl_quote: float
    net_pnl_bps: float | None
    win_rate: float | None
    profit_factor: float | None
    average_win_quote: float | None
    average_loss_quote: float | None
    max_drawdown_quote: float | None

@dataclass(frozen=True)
class FillMetrics:
    fill_count: int
    buy_fill_count: int
    sell_fill_count: int
    total_qty_bought: float
    total_qty_sold: float
    total_fees_quote: float

@dataclass(frozen=True)
class StrategyEvaluationReport:
    source_type: str
    source_id: str
    symbol: str
    start_ts: datetime | None
    end_ts: datetime | None
    pnl: PnLMetrics
    fills: FillMetrics
    by_regime: dict[str, dict[str, Any]]
    by_sentiment: dict[str, dict[str, Any]]
    warnings: list[str]
```

## Common pitfalls

```text
1. Confusing signal price with fill price.
2. Counting BUY fills as realized PnL before SELL closes.
3. Ignoring fees.
4. Mixing paper/backtest/replay semantics without source_type.
5. Treating FNG as a signal instead of overlay metadata.
6. Letting REST writer and WS writer both create intents.
7. Making tests depend on live Bybit or Alternative.me.
8. Loading large JSONL recording fully into memory.
```

## Definition of Done for v0.7

```text
- New metrics package exists.
- evaluate-backtest and evaluate-replay commands work.
- Basic markdown strategy report can be generated.
- New API endpoints are read-only.
- Tests cover pure calculations and integration service.
- Existing tests pass.
- README updated.
- Version bumped to 0.7.0.
- Safety model unchanged.
```
