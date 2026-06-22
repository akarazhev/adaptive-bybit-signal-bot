# Adaptive Bybit Signal Bot

Read-only / order-intent bot for Bybit Spot BTC/ETH. The project analyzes public market data, classifies the market regime, validates candidate limit prices against exchange instrument filters, and writes **local order intents** to a database.

It intentionally **does not place, cancel, amend, transfer, or withdraw** on Bybit. A human or a separate executor can read the database/logs and act externally.

> Engineering scaffold only, not financial advice. Run offline backtests and paper/live-shadow mode first, then tune parameters from your own statistics before using real capital.

## Implemented in v0.6

### Public market data

- Bybit V5 REST market data:
  - Spot klines
  - Spot orderbook snapshots
  - Spot recent trades
  - Spot `instruments-info` filters
  - Optional derivatives context for the same symbol: funding history and open interest when available
- Bybit V5 public Spot WebSocket support:
  - `tickers.{symbol}`
  - `publicTrade.{symbol}`
  - `orderbook.{depth}.{symbol}`
- Local public WebSocket orderbook accumulator:
  - applies snapshot/delta updates
  - deletes price levels when size is `0`
  - inserts/updates levels from deltas
  - resets on new snapshot or `u=1`
  - keeps sorted best bid/ask state per symbol
- Public WebSocket in-memory market cache:
  - recent trades per symbol
  - ticker state
  - local orderbook state
  - diagnostics via CLI

### Sentiment overlay

- Optional Alternative.me Crypto Fear & Greed Index integration:
  - `fetch-fng` caches current/history values from `/fng/`
  - `list-fng` shows cached values with attribution
  - `/sentiment/fng` exposes cached values via read-only API
  - signal metadata records the applied sentiment modifier
- The index is used only as a **risk/aggressiveness overlay**, not as a standalone buy/sell signal.
- BTC uses the full sentiment weight by default. ETH uses a reduced weight because the current Alternative.me index is primarily a Bitcoin/crypto-market sentiment measure.
- Required attribution is included in CLI/API output and metadata: `Fear & Greed Index data source: Alternative.me`.
- Backtests can use cached historical FNG values when `FNG_ENABLED=true` and values have been fetched before running the backtest.

### Strategy and ledger

- Instrument metadata ledger:
  - tick size
  - quantity step / base precision
  - min order quantity
  - min quote notional / `minOrderAmt`
  - max limit/market quantity
- Local limit-order validation:
  - buy prices are rounded down to tick size
  - sell prices are rounded up to tick size
  - quantities are rounded down to the exchange step
  - invalid local intents are rejected before being written
- Feature engine:
  - EMA 20/50/200
  - EMA slope
  - ATR%
  - RSI 14
  - VWAP deviation
  - spread bps
  - order-book imbalance
  - microprice
  - trade imbalance
  - funding z-score
  - open-interest change
- Rule-based regime classifier:
  - `range`
  - `uptrend`
  - `uptrend_pullback`
  - `downtrend`
  - `shock`
  - `no_trade`
- Strategy engine:
  - `BUY_INTENT`
  - `SELL_INTENT`
  - `CANCEL_INTENT`
  - `REPRICE_INTENT`
  - `HOLD`
- Database ledger:
  - service heartbeats
  - strategy locks
  - market features
  - regimes
  - instrument specs
  - signals
  - order intents
  - order events
  - paper fills
  - positions
  - account snapshots
  - executions
  - backtest runs
  - backtest fills

### Paper trading and backtesting

- Optional paper-fill simulator:
  - checks active local intents against later public trades/orderbook
  - can mark local intents as `PAPER_FILLED` or `PAPER_PARTIAL_FILLED`
  - updates local paper position state
- Offline candle-level backtesting:
  - download Bybit klines to CSV
  - run backtest from CSV
  - fetch klines and run backtest in one command
  - persist backtest summary/fills in DB
  - includes maker-fee accounting and synthetic spread
- File-backed public WebSocket market recorder:
  - records raw ticker/trade/orderbook messages into JSONL or JSONL.GZ
  - stores only recording metadata in DB to avoid high-volume tick writes
  - replay engine can run the strategy over recorded market streams

### Interfaces and deployment

- CLI commands for data collection, strategy cycles, paper fills, WebSocket diagnostics, backtests, and read-only account sync
- Small read-only HTTP API
- Podman-compatible `Containerfile`
- `compose.yaml` for PostgreSQL-first multi-service Podman Compose deployments
- Optional `compose.recorder.yaml` overlay for the high-volume market recorder
- Dedicated services for API, WebSocket shadow strategy, instrument sync, Fear & Greed sync, and paper fill simulation
- Soft DB strategy locks to avoid competing signal writers
- Service heartbeats exposed through CLI/API
- Unit tests

## Safety model

The Bybit REST adapter intentionally contains no methods for:

- placing orders
- amending orders
- cancelling orders
- transferring funds
- withdrawals

Even with a read-write key, the bot has no code path that sends trade instructions. For account sync, it additionally refuses to run if the key is not read-only, unless `BYBIT_ALLOW_READ_WRITE_KEY=true` is explicitly set.

Recommended key setup:

- read-only permissions only
- IP restriction if possible
- no withdrawal permission
- no order/trading permission

## Architecture

```text
Bybit public/read-only REST + public WS
          ↓
Exchange adapters
          ↓
MarketSnapshot + InstrumentSpec + WS cache + FNG sentiment cache + recording/replay
          ↓
FeatureEngine
          ↓
RegimeClassifier
          ↓
StrategyEngine + SentimentPolicy
          ↓
BotRepository
          ↓
SQLite/PostgreSQL + recording metadata + service heartbeats + strategy locks + logs + API/CLI
```

Patterns used:

- **Ports/adapters**: exchange integration is isolated in `exchange/`.
- **Repository pattern**: database writes/read queries are isolated in `data/repositories.py`.
- **Strategy pattern**: regime and strategy decision logic are isolated in `strategy/`.
- **Event ledger**: actions are stored as signal/event records rather than hidden side effects.
- **Dependency injection**: services receive `settings`, `repository`, and `client` explicitly.

## Run locally

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
adaptive-bybit-bot init-db
adaptive-bybit-bot refresh-instruments --symbols BTCUSDT,ETHUSDT
adaptive-bybit-bot run-once --symbol BTCUSDT
adaptive-bybit-bot list-signals
adaptive-bybit-bot list-intents
```

## Run with Podman

```bash
cp .env.example .env
podman build -t adaptive-bybit-signal-bot -f Containerfile .
```

Initialize DB and instrument filters:

```bash
podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot init-db
podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot refresh-instruments --symbols BTCUSDT,ETHUSDT
```

One REST polling cycle:

```bash
podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot run-once --symbol BTCUSDT
```

Continuous REST polling loop:

```bash
podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot run --symbols BTCUSDT,ETHUSDT
```

Public WebSocket shadow loop:

```bash
podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot run-ws --symbols BTCUSDT,ETHUSDT
```

HTTP API:

```bash
podman run --rm --env-file .env -v adaptive-bybit-data:/data -p 8080:8080 adaptive-bybit-signal-bot api --host 0.0.0.0 --port 8080
curl http://localhost:8080/health
curl http://localhost:8080/intents
curl http://localhost:8080/signals
curl http://localhost:8080/instruments
curl http://localhost:8080/positions
curl http://localhost:8080/paper-fills
curl http://localhost:8080/backtests
curl http://localhost:8080/market-recordings
curl http://localhost:8080/market-replays
curl http://localhost:8080/market-replay-fills
curl http://localhost:8080/sentiment/fng
curl http://localhost:8080/services
curl http://localhost:8080/locks
```

Or with compose:

```bash
podman compose up --build
```


## Multi-service Podman Compose

The default `compose.yaml` is PostgreSQL-first and starts several cooperating services:

```text
postgres          shared state store
migrate           one-shot schema initialization
api               read-only HTTP API
fng-sync          periodic Alternative.me Fear & Greed cache refresh
instrument-sync   periodic Bybit instrument filter refresh
ws-shadow         public WebSocket strategy writer
paper-runner      optional local paper-fill simulation
```

The high-volume recorder is intentionally kept out of the default stack. To enable it, add the overlay:

```bash
podman compose -f compose.yaml -f compose.recorder.yaml up --build postgres migrate api market-recorder
```

Recordings are written under `/data/market-recordings` inside the container and stored in the `market-recordings` volume. Stop the recorder when you have enough data.

Start the full stack:

```bash
cp .env.example .env
# Optional but recommended for compose:
# FNG_ENABLED=true
# PAPER_TRADING_ENABLED=true
podman compose up --build
```

`compose.yaml` overrides `DATABASE_URL` to:

```env
DATABASE_URL=postgresql+psycopg://${POSTGRES_USER:-bot}:${POSTGRES_PASSWORD:-bot}@postgres:5432/${POSTGRES_DB:-bybit_bot}
STRATEGY_WRITER_SERVICE=ws-shadow
```

That means the WebSocket shadow service is the only default strategy writer. The REST polling writer is kept out of the default stack to avoid duplicate intents. If you intentionally want polling to be the writer instead, use the override file:

```bash
podman compose -f compose.yaml -f compose.rest.yaml up --build postgres migrate api bot-rest
```

Useful diagnostics:

```bash
podman compose logs -f ws-shadow
podman compose logs -f paper-runner
podman compose exec api adaptive-bybit-bot list-services
podman compose exec api adaptive-bybit-bot list-locks
curl http://localhost:8080/services
curl http://localhost:8080/locks
```

The services also wait for the database in application code, so the stack does not rely exclusively on provider-specific advanced `depends_on` behavior.

## Useful CLI commands

```bash
adaptive-bybit-bot refresh-instruments --symbols BTCUSDT,ETHUSDT
adaptive-bybit-bot list-instruments
adaptive-bybit-bot fetch-fng --limit 30
adaptive-bybit-bot list-fng
adaptive-bybit-bot run-once --symbol BTCUSDT
adaptive-bybit-bot run --symbols BTCUSDT,ETHUSDT
adaptive-bybit-bot run-ws --symbols BTCUSDT,ETHUSDT
adaptive-bybit-bot list-signals
adaptive-bybit-bot list-intents
adaptive-bybit-bot list-positions
adaptive-bybit-bot list-paper-fills
adaptive-bybit-bot fng-loop --once
adaptive-bybit-bot instrument-loop --symbols BTCUSDT,ETHUSDT --once
adaptive-bybit-bot paper-loop --symbols BTCUSDT,ETHUSDT --once
adaptive-bybit-bot list-services
adaptive-bybit-bot list-locks
adaptive-bybit-bot record-market --symbols BTCUSDT,ETHUSDT --seconds 3600
adaptive-bybit-bot list-market-recordings
adaptive-bybit-bot replay-market --symbol BTCUSDT --recording-id <recording-id>
adaptive-bybit-bot list-market-replays
adaptive-bybit-bot list-market-replay-fills
```

WebSocket diagnostics:

```bash
adaptive-bybit-bot ws-print --symbols BTCUSDT --seconds 30 --orderbook-depth 1
adaptive-bybit-bot ws-snapshot --symbols BTCUSDT,ETHUSDT --seconds 10
adaptive-bybit-bot ws-book --symbols BTCUSDT --seconds 30 --depth 50
```

Backtesting and replay:

```bash
adaptive-bybit-bot download-klines \
  --symbol BTCUSDT \
  --interval 1 \
  --start 2026-06-01 \
  --end 2026-06-02 \
  --output data/BTCUSDT-1m.csv

adaptive-bybit-bot backtest-csv \
  --symbol BTCUSDT \
  --interval 1 \
  --input data/BTCUSDT-1m.csv

adaptive-bybit-bot backtest-fetch \
  --symbol BTCUSDT \
  --interval 1 \
  --start 2026-06-01 \
  --end 2026-06-02

adaptive-bybit-bot list-backtests
adaptive-bybit-bot list-backtest-fills --limit 100

# Replay a raw WS recording without contacting Bybit again
adaptive-bybit-bot replay-market \
  --symbol BTCUSDT \
  --input data/market-recordings/example.jsonl.gz

adaptive-bybit-bot list-market-replays
```

## Fear & Greed sentiment overlay

The sentiment module uses the Alternative.me Crypto Fear & Greed Index as a slow context input. It does **not** create buy/sell signals by itself. Instead it changes strategy aggressiveness:

- `Extreme Fear`: smaller size, deeper buy limit, slightly higher required edge.
- `Fear`: slightly smaller size and slightly deeper buy limit.
- `Greed`: smaller size, higher required edge, shorter TTL, more defensive sell target.
- `Extreme Greed`: much smaller size, meaningfully higher required edge, deeper buy limit, shorter TTL.

Enable it in `.env`:

```env
FNG_ENABLED=true
FNG_HISTORY_LIMIT=30
FNG_REFRESH_SECONDS=21600
FNG_STALE_AFTER_HOURS=36
```

Fetch/cache values:

```bash
adaptive-bybit-bot fetch-fng --limit 30
adaptive-bybit-bot list-fng
```

When enabled, `run`, `run-once`, `run-ws`, and `backtest-*` will use cached/refreshed sentiment context. For offline backtests, fetch FNG history first so the backtest can look up the value available at each candle timestamp.

Attribution: Fear & Greed Index data source: Alternative.me.

## Read-only account sync

Add read-only keys to `.env`:

```env
BYBIT_API_KEY=...
BYBIT_API_SECRET=...
```

Validate the key:

```bash
adaptive-bybit-bot validate-key
```

Sync read-only account state:

```bash
adaptive-bybit-bot sync-account --symbols BTCUSDT,ETHUSDT
```

## Manual fill confirmation

Because this bot does not place orders, it cannot know with certainty that your manual/external order was filled unless you either sync executions or confirm it. To manually confirm an intent:

```bash
adaptive-bybit-bot list-intents
adaptive-bybit-bot mark-filled --intent-id <id> --price 65000 --qty 0.001
```

After a confirmed buy fill, the bot opens/updates a local position and starts generating sell/reprice/cancel intents for that position.

## Paper-fill mode

Paper trading is off by default. To enable local simulated fills:

```env
PAPER_TRADING_ENABLED=true
PAPER_FILL_MODE=trade_through
PAPER_MIN_FILL_RATIO=1.0
PAPER_MAX_TRADE_AGE_SECONDS=300
```

Then run normal evaluation cycles:

```bash
adaptive-bybit-bot run --symbols BTCUSDT,ETHUSDT
```

Or apply one paper-fill simulation step using fresh market data:

```bash
adaptive-bybit-bot paper-fill-once --symbol BTCUSDT
adaptive-bybit-bot list-paper-fills
adaptive-bybit-bot list-positions
```

Fill modes:

- `trade_through`: intent fills only if later public trades cross the limit with enough size.
- `touch`: same as `trade_through`, but also allows a fill if the public book touches/crosses the limit.

This is still only an approximation. Real queue position, hidden/RPI liquidity, and full exchange partial-fill behavior are not modeled yet.

## Configuration

Important `.env` parameters:

```env
SYMBOLS=BTCUSDT,ETHUSDT
POLL_INTERVAL_SECONDS=10
KLINE_INTERVAL=1
KLINE_LIMIT=240
ORDERBOOK_LIMIT=50
RECENT_TRADES_LIMIT=60

WS_ORDERBOOK_DEPTH=50
WS_EVALUATION_INTERVAL_SECONDS=10
WS_CANDLE_REFRESH_SECONDS=30
WS_TRADE_LOOKBACK_SECONDS=120
WS_MAX_TRADES_PER_SYMBOL=2000

BACKTEST_STARTING_QUOTE=10000
BACKTEST_WARMUP_CANDLES=240
BACKTEST_SYNTHETIC_SPREAD_BPS=2

FNG_ENABLED=false
FNG_REFRESH_SECONDS=21600
FNG_STALE_AFTER_HOURS=36
FNG_HISTORY_LIMIT=30
FNG_BTC_WEIGHT=1.0
FNG_ETH_WEIGHT=0.6
FNG_EXTREME_FEAR_SIZE_MULTIPLIER=0.5
FNG_EXTREME_GREED_SIZE_MULTIPLIER=0.4
FNG_GREED_EXTRA_EDGE_BPS=8
FNG_EXTREME_GREED_EXTRA_EDGE_BPS=15

PAPER_TRADING_ENABLED=false
PAPER_FILL_MODE=trade_through
PAPER_MIN_FILL_RATIO=1.0
PAPER_MAX_TRADE_AGE_SECONDS=300
PAPER_LOOP_INTERVAL_SECONDS=10

SERVICE_HEARTBEAT_SECONDS=15
SERVICE_HEARTBEAT_STALE_SECONDS=120
STRATEGY_LOCK_ENABLED=true
STRATEGY_LOCK_TTL_SECONDS=60
STRATEGY_WRITER_SERVICE=any
INSTRUMENT_REFRESH_SECONDS=43200

ORDER_QUOTE_USDT=50
SPOT_MAKER_FEE_BPS=10
MIN_NET_PROFIT_BPS=12
SAFETY_BUFFER_BPS=5
MAX_SPREAD_BPS=8
MAX_ATR_PCT=1.4
SHOCK_ATR_PCT=1.2
MAX_UNREALIZED_LOSS_BPS=80
MAX_POSITION_AGE_SECONDS=7200
ORDER_TTL_SECONDS=120
REPRICE_THRESHOLD_BPS=4
MIN_EXPECTED_EDGE_BPS=30
```

Default DB:

```env
DATABASE_URL=sqlite:///data/bot.db
```

For local non-container usage you may prefer:

```env
DATABASE_URL=sqlite:///./bot.db
```

PostgreSQL can be used by setting a SQLAlchemy URL, for example:

```env
DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/<database>
```

## Testing

```bash
pip install -e '.[dev]'
pytest
python -m compileall -q src tests
python -m adaptive_bybit_bot.cli --help
```

## Important limitations

1. Compose mode uses soft DB leases, not a distributed consensus system. Keep one intended strategy writer per symbol/service.
2. The WebSocket shadow loop uses public streams only and still refreshes candles from REST.
3. Candle-level backtesting is an approximation. It does not model queue position, hidden/RPI liquidity, realistic partial fills, or exact intrabar sequencing.
4. Market replay uses real recorded public WS sequencing, but fills are still approximations: the bot does not know its true queue position or hidden/RPI liquidity.
5. Paper fills are conservative approximations and do not model all exchange microstructure details.
6. Fear & Greed is daily/slow sentiment and should not be interpreted as a real-time entry trigger.
7. Liquidation WebSocket data is not fully wired into the strategy. Funding and open interest are included as derivatives context only.
8. The strategy is deliberately conservative and rule-based. Treat it as a baseline to measure, not as a finished alpha model.

## Suggested next steps

- Add a more realistic fill model with queue position and partial fills.
- Add replay/strategy reports: fill rate, adverse selection, net PnL by regime, and sentiment impact.
- Add liquidation WebSocket adapter as context only.
- Add sentiment attribution to a future dashboard/Telegram renderer.
- Add Telegram notifications for new/cancel/reprice/fill events.
- Add dashboard with PnL, stuck positions, and signal quality metrics.
