# Roadmap v0.7+ — что делать дальше

## Общий принцип дальнейшей разработки

После v0.6 проект уже умеет:

```text
collect → signal → intent → paper/backtest/replay
```

Дальше не стоит добавлять новые индикаторы ради индикаторов. Следующий приоритет — **измеримость и доказуемость стратегии**.

То есть нужно ответить на вопросы:

```text
- стратегия зарабатывает после комиссий или нет?
- где она ошибается?
- какие режимы рынка лучше/хуже?
- какие intents зависают?
- Fear & Greed помогает или ухудшает?
- какой fill model даёт реалистичную оценку?
```

## Рекомендуемый следующий релиз: v0.7 Strategy Metrics & Reporting

### Цель

Добавить слой аналитики, который агрегирует данные из:

```text
signals
order_intents
order_events
paper_fills
positions
backtest_runs/backtest_fills
market_replay_runs/market_replay_fills
market_features
market_regimes
sentiment_fng
```

и строит отчёты:

```text
net PnL
fill rate
cancel/reprice rate
adverse selection
signal forward returns
PnL by regime
PnL by FNG bucket
strategy quality by symbol/timeframe
```

### Новые модули

Рекомендуемая структура:

```text
src/adaptive_bybit_bot/metrics/
  __init__.py
  models.py
  calculations.py
  service.py
  reports.py
```

Назначение:

```text
models.py        dataclasses/Pydantic schemas для отчётов
calculations.py  pure calculation functions
service.py       DB orchestration через repository
reports.py       render/export JSON/Markdown/CSV
```

### Новые таблицы, если нужен persisted report cache

Вариант 1 — без новых таблиц:

```text
Считать отчёты на лету по existing data.
```

Вариант 2 — добавить cache:

```text
strategy_report_runs
  id
  ts
  report_type
  source_type       paper/backtest/replay/live_shadow
  symbol
  start_ts
  end_ts
  config_json
  summary_json
  artifact_path
```

Для v0.7 можно начать без таблицы и добавить cache позже.

### Метрики v0.7

#### 1. Signal counts

```text
total signals
BUY_INTENT count
SELL_INTENT count
CANCEL_INTENT count
REPRICE_INTENT count
HOLD count
signals by regime
signals by symbol
signals by day/hour
```

#### 2. Intent lifecycle metrics

```text
active intents
filled intents
expired intents
cancel requested intents
replaced intents
average intent TTL
average time to fill
average time to cancel/reprice
stuck intents > threshold
```

#### 3. Fill metrics

```text
fill rate = fills / eligible intents
buy fill rate
sell fill rate
average fill price vs signal price
fee total
fee bps realized
```

#### 4. PnL metrics

```text
gross PnL
fees
net PnL
net PnL bps
win rate
average win
average loss
profit factor
max drawdown
expectancy per trade
```

#### 5. Adverse selection metrics

Для BUY signal/fill:

```text
forward return after 1m
forward return after 5m
forward return after 15m
forward return after 60m
minimum adverse excursion
maximum favorable excursion
```

Для SELL signal/fill:

```text
post-sell return avoided/captured
missed upside after sell
```

Важно различать:

```text
signal timestamp
intent created timestamp
fill timestamp
position close timestamp
```

#### 6. Regime analytics

```text
PnL by regime
fill rate by regime
adverse selection by regime
average time in position by regime
cancel/reprice rate by regime
```

Цель:

```text
Понять, действительно ли range/uptrend_pullback работают лучше, а shock/downtrend нужно блокировать.
```

#### 7. FNG analytics

Buckets:

```text
Extreme Fear
Fear
Neutral
Greed
Extreme Greed
stale/disabled
```

Метрики:

```text
PnL by FNG bucket
fill rate by bucket
adverse selection by bucket
position duration by bucket
effect of size_multiplier/edge_extra_bps
```

Цель:

```text
Понять, улучшает ли FNG overlay стратегию или просто снижает активность.
```

### CLI команды v0.7

Предложение:

```bash
adaptive-bybit-bot evaluate-signals --symbol BTCUSDT --hours 24
adaptive-bybit-bot evaluate-paper --symbol BTCUSDT --from ... --to ...
adaptive-bybit-bot evaluate-backtest --run-id <id>
adaptive-bybit-bot evaluate-replay --run-id <id>
adaptive-bybit-bot strategy-report --source replay --run-id <id> --format markdown
adaptive-bybit-bot export-report --source replay --run-id <id> --output report.md
```

Минимальный набор для первого PR:

```bash
adaptive-bybit-bot evaluate-replay --run-id <id>
adaptive-bybit-bot evaluate-backtest --run-id <id>
adaptive-bybit-bot strategy-report --source replay --run-id <id>
```

### API endpoints v0.7

```text
GET /metrics/summary
GET /metrics/signals
GET /metrics/backtests/{run_id}
GET /metrics/replays/{run_id}
GET /reports/strategy
```

Можно начать с:

```text
GET /metrics/replays/{run_id}
GET /metrics/backtests/{run_id}
```

### Acceptance criteria v0.7

```text
1. evaluate-replay считает net PnL, fees, fill count, win rate.
2. evaluate-backtest считает те же базовые метрики.
3. strategy-report выводит human-readable Markdown.
4. Отчёт показывает PnL by regime, если regime metadata доступна.
5. Отчёт показывает FNG bucket stats, если sentiment metadata доступна.
6. Unit tests покрывают calculations.py без БД.
7. Integration tests покрывают repository/service на in-memory SQLite.
8. Старые 40 тестов остаются зелёными.
```

## v0.8 — Better fill model

### Цель

Улучшить paper/replay fill approximation.

Текущая проблема:

```text
trade_through говорит, что цена прошла через уровень, но не знает:
- сколько объёма было перед нами;
- были ли partial fills;
- какой была очередь;
- какой latency/cancel delay.
```

### Proposed fill model уровни

#### Level 1: current `trade_through`

```text
Trade crosses limit → fill.
```

#### Level 2: volume-threshold model

```text
Only fill after cumulative aggressive trade volume through level >= qty * multiplier.
```

Настройки:

```env
FILL_VOLUME_MULTIPLIER=1.0
FILL_REQUIRE_CROSS_BPS=0
```

#### Level 3: queue-estimate model

При создании BUY limit:

```text
estimate queue ahead at same price from local orderbook qty
fill only after cumulative sell-aggressive volume >= queue_ahead * queue_factor + own_qty
```

Настройки:

```env
FILL_QUEUE_AHEAD_FACTOR=0.5
FILL_MAX_QUEUE_AHEAD_QUOTE=...
```

#### Level 4: latency/cancel delay model

```text
intent created at t
actual order assumed active at t + submit_latency_ms
cancel intent effective at t + cancel_latency_ms
reprice intent effective at t + amend_latency_ms
```

Настройки:

```env
SIM_SUBMIT_LATENCY_MS=250
SIM_CANCEL_LATENCY_MS=250
SIM_REPRICE_LATENCY_MS=300
```

### Acceptance criteria v0.8

```text
1. Fill model pluggable: trade_through / volume_threshold / queue_estimate.
2. Replay can run same recording with different fill models.
3. Report compares model outcomes.
4. Partial fills are represented in replay/paper fills or explicitly disabled.
5. Tests cover edge cases: touch without cross, cross with insufficient volume, queue ahead.
```

## v0.9 — Risk Engine

### Цель

Сделать risk management отдельным слоем, а не набором условий внутри StrategyEngine.

Новая структура:

```text
src/adaptive_bybit_bot/risk/
  __init__.py
  config.py
  engine.py
  limits.py
  state.py
```

Risk rules:

```text
max daily loss
max open exposure
max position age
max stale intent age
cooldown after loss
cooldown after volatility shock
cooldown after N bad signals
symbol-level risk budget
global risk budget
max active intents per symbol
max consecutive losses
```

Пример config:

```env
RISK_MAX_DAILY_LOSS_USDT=10
RISK_MAX_SYMBOL_EXPOSURE_USDT=250
RISK_MAX_GLOBAL_EXPOSURE_USDT=500
RISK_COOLDOWN_AFTER_LOSS_SECONDS=1800
RISK_COOLDOWN_AFTER_SHOCK_SECONDS=900
RISK_MAX_ACTIVE_BUY_INTENTS_PER_SYMBOL=1
RISK_MAX_ACTIVE_SELL_INTENTS_PER_SYMBOL=1
```

Risk engine должен уметь возвращать:

```text
ALLOW
BLOCK
REDUCE_SIZE
FORCE_EXIT
CANCEL_STALE_INTENTS
```

Acceptance criteria:

```text
1. RiskEngine вызывается до записи order intent.
2. Risk decisions сохраняются в signal metadata/reason.
3. Tests покрывают limit breaches.
4. Existing strategy behavior совпадает при default relaxed risk config.
```

## v1.0 — Production observability/dashboard/alerts

### Цель

Сделать систему удобной для долгого shadow/paper запуска на VPS.

Компоненты:

```text
Telegram alerts
Prometheus metrics
Grafana dashboard
structured JSON logs
backup/restore scripts
retention policy для recordings
read-only reconciliation dashboard
```

### Telegram alerts

События:

```text
new BUY_INTENT
new SELL_INTENT
CANCEL_INTENT
REPRICE_INTENT
paper fill
manual fill
stuck position
service stale
lock conflict
FNG changed bucket
risk block
```

### Prometheus metrics

```text
service heartbeat freshness
WS event rate
recording bytes written
strategy decisions per minute
active intents
paper positions
API latency
DB latency
replay duration
```

### Dashboard

Панели:

```text
current regimes
active intents
positions
paper PnL
recent signals
FNG state
service health
locks
market data freshness
recording sessions
replay/backtest metrics
```

## v1.1+ — ML только после метрик

Не добавлять ML-предсказание цены до появления качественных reports.

Правильные ML-задачи позже:

```text
fill probability estimation
adverse selection classifier
bad market/no-trade classifier
position exit quality estimator
parameter selection by regime
```

Нежелательная постановка:

```text
predict BTC price direction
```

Лучшие target variables:

```text
probability of fill within TTL
expected forward return after fill
probability of adverse move after limit fill
expected time to profitable exit
expected net edge after fees
```

## Глобальные DoD для будущих версий

Каждый следующий релиз должен:

```text
1. Не добавлять trading side effects.
2. Сохранять SQLite standalone mode.
3. Сохранять PostgreSQL compose mode.
4. Иметь unit tests для pure logic.
5. Иметь integration test на SQLite для repository/service.
6. Обновлять README.md и .env.example.
7. Обновлять version в pyproject.toml.
8. Добавлять CLI help tests для новых команд.
9. Не ломать existing tests.
10. Явно документировать approximation/limitations.
```

