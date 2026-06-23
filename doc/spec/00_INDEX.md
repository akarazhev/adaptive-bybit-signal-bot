# Adaptive Bybit Signal Bot — спецификации и handoff для Codex CLI

Этот каталог содержит версионные Markdown-спецификации проекта `adaptive-bybit-signal-bot`, начиная с v0.1 и заканчивая текущей реализованной версией v0.6.

Цель документов — дать консольному агенту разработки полный контекст:

- что было реализовано в каждой версии;
- какие архитектурные решения уже приняты;
- какие команды, таблицы, сервисы и ограничения существуют;
- что важно не сломать;
- какие следующие инкременты логично делать дальше.

## Текущая версия проекта

Текущий архив проекта: `adaptive-bybit-signal-bot-v0.6.zip`.

Текущий пакет Python:

```text
adaptive-bybit-signal-bot 0.6.0
Python >= 3.14
CLI entrypoint: adaptive-bybit-bot
```

Главный safety-инвариант проекта:

```text
Бот не размещает, не отменяет и не изменяет ордера на Bybit.
Он только читает public/read-only данные и пишет локальные order intents/signals в БД.
```

## Состав документации

```text
00_INDEX.md
01_v0.1_MVP_ORDER_INTENT_BOT.md
02_v0.2_INSTRUMENT_SPECS_PAPER_WS.md
03_v0.3_WS_SHADOW_BACKTEST.md
04_v0.4_FEAR_GREED_SENTIMENT.md
05_v0.5_PODMAN_COMPOSE_RUNTIME.md
06_v0.6_MARKET_RECORDER_REPLAY.md
07_CURRENT_ARCHITECTURE.md
08_NEXT_ROADMAP_V0.7_PLUS.md
09_CODEX_CLI_HANDOFF.md
10_SUPERPOWERS_CODEX_CONFIGURATION.md
```

## Как использовать с Codex CLI

Рекомендуемый порядок чтения для агента:

1. `07_CURRENT_ARCHITECTURE.md` — понять текущее состояние v0.6.
2. `06_v0.6_MARKET_RECORDER_REPLAY.md` — понять последний реализованный инкремент.
3. `08_NEXT_ROADMAP_V0.7_PLUS.md` — выбрать следующую задачу.
4. `09_CODEX_CLI_HANDOFF.md` — команды, инварианты, DoD и стиль разработки.
5. `10_SUPERPOWERS_CODEX_CONFIGURATION.md` — проектная конфигурация Superpowers/Codex.
6. Версионные файлы `01`–`05` — читать при необходимости исторического контекста.

## Быстрая карта версий

| Версия | Основной смысл | Статус |
|---|---|---|
| v0.1 | MVP: read-only Bybit, feature/regime/strategy, order-intent ledger, CLI/API, SQLite/PostgreSQL | Реализовано |
| v0.2 | Instrument specs, нормализация лимиток, paper-fill симулятор, public WS client | Реализовано |
| v0.3 | Локальная WS-книга, WS shadow mode, candle-level backtest | Реализовано |
| v0.4 | Alternative.me Fear & Greed sentiment overlay | Реализовано |
| v0.5 | Multi-service Podman Compose, PostgreSQL-first, heartbeats, strategy locks | Реализовано |
| v0.6 | File-backed market recorder и replay engine на raw public WS events | Реализовано |
| v0.7+ | Метрики стратегии, отчёты, улучшенный fill model, risk engine, dashboard/alerts | Запланировано |

## Главные ограничения текущей версии

1. Исполнение лимитных ордеров в paper/backtest/replay остаётся приближением.
2. Реальная позиция в очереди лимитной книги не моделируется.
3. Hidden/RPI liquidity не моделируется.
4. Liquidation stream пока не подключён полноценно как derivatives context.
5. Нет полноценного strategy metrics/reporting слоя.
6. Нет Telegram/dashboard/Prometheus.
7. Нет Alembic/миграционного слоя; схема создаётся через SQLAlchemy metadata.
8. Нет production-grade секрет-менеджмента.

## Рекомендуемый следующий инкремент

Следующий инкремент: **v0.7 Strategy Metrics & Reporting**.

Смысл v0.7:

```text
Из накопленных signals/intents/paper fills/backtests/replays получить измеримые ответы:
- strategy net PnL после комиссий;
- fill rate;
- cancel/reprice rate;
- adverse selection;
- качество сигналов через 1/5/15/60 минут;
- PnL по режимам рынка;
- влияние Fear & Greed;
- где стратегия системно ошибается.
```
