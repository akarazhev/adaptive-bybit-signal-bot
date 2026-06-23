# Current architecture — adaptive-bybit-signal-bot v0.6

## One-line summary

`adaptive-bybit-signal-bot` is a read-only/order-intent research and signal system for Bybit Spot BTC/ETH. It collects public/read-only market data, classifies market regimes, writes local order intents, supports paper/backtest/replay workflows, and can run as a multi-service Podman Compose stack.

## Core safety model

The project must preserve this invariant:

```text
No trading side effects on Bybit.
```

The codebase intentionally has no production path for:

```text
- place order;
- cancel order;
- amend order;
- transfer;
- withdrawal;
- leverage/margin operations;
- direct exchange execution.
```

The bot can only create local records:

```text
SignalRecord
OrderIntentRecord
OrderEventRecord
PaperFillRecord
PositionRecord
BacktestRunRecord
MarketReplayRunRecord
```

If private Bybit keys are used, they are for read-only validation/account sync only.

## Current package metadata

```text
Project: adaptive-bybit-signal-bot
Version: 0.6.0
Python: >= 3.14
CLI: adaptive-bybit-bot
Default DB: sqlite:////data/bot.db
Compose DB: postgresql+psycopg://bot:bot@postgres:5432/bybit_bot
```

Main dependencies:

```text
httpx
pydantic
pydantic-settings
SQLAlchemy
typer
rich
websockets
fastapi
uvicorn
psycopg[binary]
pytest/ruff/mypy for dev
```

## Directory map

```text
src/adaptive_bybit_bot/
  api/
    app.py                  read-only FastAPI application

  backtesting/
    csv_io.py               candle CSV read/write helpers
    engine.py               candle-level backtest engine
    historical.py           Bybit historical klines downloader helpers

  data/
    db.py                   SQLAlchemy engine/session/schema helpers
    models.py               ORM models
    repositories.py         repository pattern for all persistence

  domain/
    enums.py                Side/Regime/SignalAction/status enums
    models.py               dataclasses for market, feature, signal, sentiment models

  exchange/
    bybit_client.py         REST public/read-only Bybit adapter
    bybit_ws.py             public WS adapter
    signing.py              private read-only request signing

  features/
    indicators.py           EMA/ATR/RSI/VWAP helpers
    engine.py               FeatureEngine

  market_data/
    orderbook.py            LocalOrderBook + LocalOrderBookStore
    ws_cache.py             in-memory WS market cache

  recording/
    events.py               file-backed MarketEvent schema
    jsonl.py                JSONL/JSONL.GZ reader/writer
    recorder.py             public WS market recorder
    replay.py               replay engine over recorded events

  sentiment/
    alternative_me.py       Alternative.me FNG client
    policy.py               sentiment modifiers
    service.py              cache refresh/context helpers

  services/
    account_sync.py         read-only account/execution sync
    factory.py              app dependency factory
    maintenance.py          fng/instrument/paper loops
    market_loop.py          REST polling strategy loop
    paper_trading.py        paper-fill simulator
    runtime.py              wait-db, heartbeat, locks
    ws_shadow.py            public WS shadow strategy loop

  cli.py                    Typer CLI
  config.py                 pydantic settings
  logging_config.py         logging setup
```

## Main runtime flows

### 1. REST polling strategy loop

```text
run / run-once
  ↓
BybitRestClient public market snapshot
  ↓
InstrumentSpec from DB/fallback
  ↓
FearGreedContext optional
  ↓
FeatureEngine
  ↓
RegimeClassifier
  ↓
StrategyEngine
  ↓
BotRepository.save_signal_and_intent
```

Command:

```bash
adaptive-bybit-bot run --symbols BTCUSDT,ETHUSDT
adaptive-bybit-bot run-once --symbol BTCUSDT
```

### 2. WebSocket shadow strategy loop

```text
run-ws
  ↓
Bybit public WS
  ↓
LocalOrderBook + WS cache
  ↓
REST candles refresh
  ↓
MarketSnapshot
  ↓
FeatureEngine / RegimeClassifier / StrategyEngine
  ↓
DB signal/order intent ledger
```

Command:

```bash
adaptive-bybit-bot run-ws --symbols BTCUSDT,ETHUSDT
```

### 3. Instrument sync

```text
refresh-instruments / instrument-loop
  ↓
Bybit instruments-info
  ↓
InstrumentSpec
  ↓
instrument_specs table
```

Commands:

```bash
adaptive-bybit-bot refresh-instruments --symbols BTCUSDT,ETHUSDT
adaptive-bybit-bot instrument-loop --symbols BTCUSDT,ETHUSDT
```

### 4. Fear & Greed sync

```text
fetch-fng / fng-loop
  ↓
Alternative.me /fng/
  ↓
FearGreedValue list
  ↓
sentiment_fng table
```

Commands:

```bash
adaptive-bybit-bot fetch-fng --limit 30
adaptive-bybit-bot fng-loop
```

### 5. Paper-fill loop

```text
paper-loop / paper-fill-once / paper-step
  ↓
active order intents
  ↓
public trades/orderbook
  ↓
fill approximation
  ↓
paper_fills + positions + order_events
```

Commands:

```bash
adaptive-bybit-bot paper-loop --symbols BTCUSDT,ETHUSDT
adaptive-bybit-bot paper-fill-once --symbol BTCUSDT
adaptive-bybit-bot paper-step --symbol BTCUSDT
```

### 6. Candle-level backtest

```text
CSV/historical klines
  ↓
BacktestEngine
  ↓
synthetic spread/orderbook approximation
  ↓
FeatureEngine/RegimeClassifier/StrategyEngine
  ↓
simulated fills
  ↓
backtest_runs/backtest_fills
```

Commands:

```bash
adaptive-bybit-bot download-klines --symbol BTCUSDT --interval 1 --start 2026-06-01 --end 2026-06-02 --output data/BTCUSDT-1m.csv
adaptive-bybit-bot backtest-csv --symbol BTCUSDT --interval 1 --input data/BTCUSDT-1m.csv
adaptive-bybit-bot backtest-fetch --symbol BTCUSDT --interval 1 --start 2026-06-01 --end 2026-06-02
```

### 7. Market recording and replay

```text
record-market
  ↓
public WS raw events
  ↓
JSONL/JSONL.GZ file
  ↓
market_recording_sessions metadata

replay-market
  ↓
JSONL reader
  ↓
local orderbook + trade candles
  ↓
strategy replay
  ↓
market_replay_runs/market_replay_fills
```

Commands:

```bash
adaptive-bybit-bot record-market --symbols BTCUSDT,ETHUSDT --seconds 3600
adaptive-bybit-bot list-market-recordings
adaptive-bybit-bot replay-market --symbol BTCUSDT --recording-id <recording-id>
adaptive-bybit-bot list-market-replays
adaptive-bybit-bot list-market-replay-fills
```

## Database schema overview

Current ORM tables:

```text
market_features
market_regimes
backtest_runs
backtest_fills
market_recording_sessions
market_replay_runs
market_replay_fills
instrument_specs
sentiment_fng
service_heartbeats
strategy_locks
signals
order_intents
order_events
paper_fills
positions
account_snapshots
executions
```

### Strategy/ledger tables

```text
signals
  id, ts, symbol, action, side, price, qty, confidence,
  expected_edge_bps, regime, reason_json, metadata_json, strategy_version

order_intents
  id, signal_id, symbol, side, limit_price, qty, status,
  created_at, expires_at, replaced_by_id, filled_at, fill_price, fill_qty

order_events
  id, order_intent_id, signal_id, ts, event_type,
  old_price, new_price, reason_json

positions
  id, symbol, qty, avg_entry, status, opened_at,
  updated_at, closed_at, realized_pnl
```

### Market/research tables

```text
market_features
market_regimes
backtest_runs
backtest_fills
market_recording_sessions
market_replay_runs
market_replay_fills
```

### Runtime tables

```text
service_heartbeats
strategy_locks
```

### External context tables

```text
instrument_specs
sentiment_fng
account_snapshots
executions
```

## CLI command inventory v0.6

```text
init-db
wait-db
run-once
run
run-ws
refresh-instruments
instrument-loop
fetch-fng
fng-loop
list-fng
list-instruments
paper-fill-once
paper-loop
validate-key
sync-account
instrument-info
paper-step
ws-print
ws-snapshot
ws-book
record-market
list-market-recordings
replay-market
list-market-replays
list-market-replay-fills
download-klines
backtest-fetch
backtest-csv
list-backtests
list-backtest-fills
list-intents
list-signals
list-paper-fills
list-services
list-locks
list-positions
mark-filled
api
```

## API endpoints v0.6

```text
GET /health
GET /signals
GET /intents
GET /paper-fills
GET /instruments
GET /positions
GET /sentiment/fng
GET /backtests
GET /backtest-fills
GET /services
GET /locks
GET /market-recordings
GET /market-replays
GET /market-replay-fills
```

All API endpoints are read-only.

## Compose architecture

### Default `compose.yaml`

Services:

```text
postgres
migrate
api
fng-sync
instrument-sync
ws-shadow
paper-runner
```

Run:

```bash
podman compose up --build
```

### REST writer override

File:

```text
compose.rest.yaml
```

Run:

```bash
podman compose -f compose.yaml -f compose.rest.yaml up --build postgres migrate api bot-rest
```

Use this only when REST polling should be the writer instead of `ws-shadow`.

### Recorder overlay

File:

```text
compose.recorder.yaml
```

Run:

```bash
podman compose -f compose.yaml -f compose.recorder.yaml up --build postgres migrate api market-recorder
```

Recorder is not in default stack to avoid uncontrolled data growth.

## Important environment settings

```env
SYMBOLS=BTCUSDT,ETHUSDT
DATABASE_URL=sqlite:////data/bot.db
BYBIT_BASE_URL=https://api.bybit.com
BYBIT_PUBLIC_WS_SPOT_URL=wss://stream.bybit.com/v5/public/spot

STRATEGY_LOCK_ENABLED=true
STRATEGY_LOCK_TTL_SECONDS=60
STRATEGY_WRITER_SERVICE=any
SERVICE_HEARTBEAT_SECONDS=15
SERVICE_HEARTBEAT_STALE_SECONDS=120

ORDER_QUOTE_USDT=50
MAX_POSITION_QUOTE_USDT=250
SPOT_MAKER_FEE_BPS=10
SPOT_TAKER_FEE_BPS=10
MIN_NET_PROFIT_BPS=12
MIN_EXPECTED_EDGE_BPS=30
MAX_SPREAD_BPS=8

FNG_ENABLED=false
PAPER_TRADING_ENABLED=false

MARKET_RECORDING_DIR=/data/market-recordings
MARKET_RECORDING_ORDERBOOK_DEPTH=50
MARKET_RECORDING_COMPRESS=true
```

## Testing baseline

Current v0.6 checks reported:

```text
pytest -q
82 passed

python -m compileall -q src tests
OK

CLI help smoke checks
OK

unzip -t adaptive-bybit-signal-bot-v0.6.zip
OK
```

Recommended local development checks:

```bash
pip install -e '.[dev]'
pytest
python -m compileall -q src tests
python -m adaptive_bybit_bot.cli --help
ruff check .
mypy src
```

Note: `ruff` and `mypy` are configured in `pyproject.toml`, but previous generated verification did not run them where the tools were unavailable.

## Stable invariants for future work

Do not break:

```text
1. No exchange trading side effects.
2. Public/read-only data collection only.
3. SQLite standalone mode.
4. PostgreSQL compose mode.
5. One strategy writer per symbol in compose.
6. InstrumentSpec validation before writing active order intents.
7. FNG is overlay only, not signal source.
8. Recorder writes high-volume events to files, not DB.
9. Replay works offline from file.
10. API remains read-only.
```
