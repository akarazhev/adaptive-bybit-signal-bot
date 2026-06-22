# Adaptive Bybit Signal Bot

Read-only/order-intent MVP for Bybit spot BTC/ETH.

The bot analyzes public market data, classifies the market regime, calculates simple technical and order-book features, and writes **order intents** to a database. It does **not** place, cancel, or amend orders on Bybit. A human or a separate executor can read the database/logs and act externally.

> This is engineering scaffolding, not financial advice. Run paper/live-shadow mode first and tune parameters from your own statistics before using real capital.

## What is implemented

- Public Bybit V5 REST market data:
  - spot klines
  - spot orderbook snapshots
  - spot recent trades
  - derivatives context for the same symbol: funding history and open interest when available
- Optional read-only private sync:
  - API key metadata validation
  - wallet balance snapshot
  - open orders snapshot
  - execution history storage
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
  - market features
  - regimes
  - signals
  - order intents
  - order events
  - positions
  - account snapshots
  - executions
- CLI and small read-only HTTP API
- Tests
- Podman-compatible `Containerfile`

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
Bybit public/read-only REST
          ↓
BybitRestClient adapter
          ↓
MarketSnapshot
          ↓
FeatureEngine
          ↓
RegimeClassifier
          ↓
StrategyEngine
          ↓
BotRepository
          ↓
SQLite/PostgreSQL + logs + API/CLI
```

Patterns used:

- **Ports/adapters**: exchange integration is isolated in `exchange/`.
- **Repository pattern**: DB writes/read queries are isolated in `data/repositories.py`.
- **Strategy pattern**: market-regime and strategy decision logic are isolated in `strategy/`.
- **Event ledger**: actions are stored as immutable-ish signal/event records rather than hidden side effects.
- **Dependency injection**: services receive `settings`, `repository`, and `client` explicitly.

## Run locally

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
adaptive-bybit-bot init-db
adaptive-bybit-bot run-once --symbol BTCUSDT
adaptive-bybit-bot list-signals
adaptive-bybit-bot list-intents
```

## Run with Podman

```bash
cp .env.example .env
podman build -t adaptive-bybit-signal-bot -f Containerfile .
podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot run-once --symbol BTCUSDT
```

Continuous loop:

```bash
podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot run --symbols BTCUSDT,ETHUSDT
```

HTTP API:

```bash
podman run --rm --env-file .env -v adaptive-bybit-data:/data -p 8080:8080 adaptive-bybit-signal-bot api --host 0.0.0.0 --port 8080
curl http://localhost:8080/health
curl http://localhost:8080/intents
curl http://localhost:8080/signals
```

Or with compose:

```bash
podman compose up --build bot
podman compose up --build api
```

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

## Configuration

Important `.env` parameters:

```env
SYMBOLS=BTCUSDT,ETHUSDT
POLL_INTERVAL_SECONDS=10
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
DATABASE_URL=postgresql+psycopg://bot:bot@postgres:5432/bot
```

## Testing

```bash
pip install -e '.[dev]'
pytest
```

## Important limitations of this MVP

1. It uses REST polling, not a full WebSocket event engine. Polling is simpler and safer for the first version.
2. It does not yet persist instrument tick/lot filters from `instruments-info`; price tick defaults to `0.01`, quantity step to `0.000001`.
3. It does not include historical backtesting yet.
4. Liquidation data is not fully wired. Funding and open interest are included as derivatives context; liquidation WebSocket support should be added after the order-intent ledger is stable.
5. The strategy is deliberately conservative and rule-based. Treat it as a baseline to measure, not as a finished alpha model.

## Suggested next steps

- Add `instruments-info` sync for exact tick size, lot size and min notional.
- Add paper-fill simulator for limit-order fill probability.
- Add historical backtesting from Bybit historical data.
- Add WebSocket collectors for lower-latency orderbook/trade streams.
- Add liquidation WebSocket adapter as context only.
- Add Telegram notifications for new/cancel/reprice/fill events.
- Add dashboard with PnL, stuck positions, and signal quality metrics.
