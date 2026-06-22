from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from adaptive_bybit_bot.api.app import create_app
from adaptive_bybit_bot.backtesting import BacktestConfig, BacktestResult, CandleBacktestRunner
from adaptive_bybit_bot.backtesting.csv_io import read_candles_csv, write_candles_csv
from adaptive_bybit_bot.backtesting.historical import fetch_historical_klines, parse_datetime
from adaptive_bybit_bot.config import Settings, get_settings
from adaptive_bybit_bot.data.db import wait_for_database
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.models import Candle, FearGreedContext, InstrumentSpec
from adaptive_bybit_bot.exchange.bybit_client import BybitRestClient
from adaptive_bybit_bot.exchange.bybit_ws import BybitPublicWebSocketClient
from adaptive_bybit_bot.logging_config import configure_logging
from adaptive_bybit_bot.sentiment.service import refresh_fear_greed_cache
from adaptive_bybit_bot.services.account_sync import sync_account_once, validate_read_only_key
from adaptive_bybit_bot.services.factory import (
    fear_greed_policy_from_settings,
    risk_config_from_settings,
)
from adaptive_bybit_bot.services.maintenance import (
    run_fng_loop,
    run_instrument_loop,
    run_paper_loop,
)
from adaptive_bybit_bot.services.market_loop import (
    refresh_instruments_once,
    run_forever,
    run_paper_fill_once,
    run_symbol_once,
)
from adaptive_bybit_bot.services.paper_trading import PaperFillSimulator
from adaptive_bybit_bot.services.ws_shadow import (
    collect_ws_cache_for_seconds,
    run_ws_shadow_forever,
)

app = typer.Typer(no_args_is_help=True, help="Adaptive Bybit spot signal/order-intent bot.")
console = Console()


def _settings() -> Settings:
    settings = get_settings()
    configure_logging(settings.log_level)
    return settings


def _repo(settings: Settings) -> BotRepository:
    engine = wait_for_database(
        settings.database_url,
        timeout_seconds=settings.db_wait_timeout_seconds,
        interval_seconds=settings.db_wait_interval_seconds,
        create=True,
    )
    return BotRepository(engine)


def _parse_symbols(value: str | None, settings: Settings) -> list[str]:
    if not value:
        return settings.symbols
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _print_json(payload: object) -> None:
    console.print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _backtest_config(settings: Settings, *, symbol: str, interval: str) -> BacktestConfig:
    del symbol  # reserved for future per-symbol overrides
    return BacktestConfig(
        interval=interval,
        initial_quote=settings.backtest_starting_quote,
        lookback_candles=settings.backtest_warmup_candles,
        synthetic_spread_bps=settings.backtest_synthetic_spread_bps,
        maker_fee_bps=settings.spot_maker_fee_bps,
        fill_model="touch",
        force_close=settings.backtest_force_close,
        sentiment_enabled=settings.fng_enabled,
    )


def _run_backtest(
    *,
    settings: Settings,
    repository: BotRepository,
    symbol: str,
    interval: str,
    candles: list[Candle],
    instrument: InstrumentSpec,
) -> BacktestResult:
    sentiment_provider: Callable[[datetime], FearGreedContext | None] | None = None
    if settings.fng_enabled:

        def sentiment_provider(ts: datetime) -> FearGreedContext | None:
            return repository.get_fear_greed_at(ts)

    runner = CandleBacktestRunner(
        risk=risk_config_from_settings(settings),
        instrument=instrument,
        config=_backtest_config(settings, symbol=symbol, interval=interval),
        sentiment_policy=fear_greed_policy_from_settings(settings),
        sentiment_provider=sentiment_provider,
    )
    return runner.run(symbol=symbol.upper(), candles=candles)


@app.command("init-db")
def init_db() -> None:
    """Create database tables."""
    settings = _settings()
    wait_for_database(
        settings.database_url,
        timeout_seconds=settings.db_wait_timeout_seconds,
        interval_seconds=settings.db_wait_interval_seconds,
        create=True,
    )
    console.print(f"Database initialized: {settings.database_url}")


@app.command("wait-db")
def wait_db() -> None:
    """Wait until the configured database is reachable and schema is created."""
    settings = _settings()
    wait_for_database(
        settings.database_url,
        timeout_seconds=settings.db_wait_timeout_seconds,
        interval_seconds=settings.db_wait_interval_seconds,
        create=True,
    )
    console.print("Database is ready")


@app.command("run-once")
def run_once(
    symbol: Annotated[str, typer.Option(help="Spot symbol, e.g. BTCUSDT")] = "BTCUSDT",
) -> None:
    """Run one market evaluation cycle and persist the signal/order intent."""
    settings = _settings()
    repository = _repo(settings)

    async def _run() -> None:
        async with BybitRestClient(
            base_url=settings.bybit_base_url,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
            recv_window=settings.bybit_recv_window,
        ) as client:
            result = await run_symbol_once(
                settings=settings,
                repository=repository,
                client=client,
                symbol=symbol.upper(),
            )
            _print_json(result.as_dict())

    asyncio.run(_run())


@app.command("run")
def run(
    symbols: Annotated[str | None, typer.Option(help="Comma-separated symbols")] = None,
    service_name: Annotated[
        str, typer.Option(help="Service name used for heartbeat/locks")
    ] = "bot-rest",
) -> None:
    """Run the continuous polling loop."""
    settings = _settings()
    repository = _repo(settings)
    selected_symbols = _parse_symbols(symbols, settings)
    logging.getLogger(__name__).info("starting symbols=%s", selected_symbols)

    async def _run() -> None:
        async with BybitRestClient(
            base_url=settings.bybit_base_url,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
            recv_window=settings.bybit_recv_window,
        ) as client:
            await run_forever(
                settings=settings,
                repository=repository,
                client=client,
                symbols=selected_symbols,
                service_name=service_name,
            )

    asyncio.run(_run())


@app.command("run-ws")
def run_ws(
    symbols: Annotated[str | None, typer.Option(help="Comma-separated symbols")] = None,
    seconds: Annotated[int, typer.Option(help="Seconds to run; 0 means forever")] = 0,
    service_name: Annotated[
        str, typer.Option(help="Service name used for heartbeat/locks")
    ] = "ws-shadow",
) -> None:
    """Run public WebSocket shadow loop and persist local order intents."""
    settings = _settings()
    repository = _repo(settings)
    selected_symbols = _parse_symbols(symbols, settings)
    logging.getLogger(__name__).info("starting_ws_shadow symbols=%s", selected_symbols)

    async def _run() -> None:
        async with BybitRestClient(
            base_url=settings.bybit_base_url,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
            recv_window=settings.bybit_recv_window,
        ) as client:
            await run_ws_shadow_forever(
                settings=settings,
                repository=repository,
                rest_client=client,
                symbols=selected_symbols,
                seconds=seconds,
                service_name=service_name,
            )

    asyncio.run(_run())


@app.command("refresh-instruments")
def refresh_instruments(
    symbols: Annotated[str | None, typer.Option(help="Comma-separated symbols")] = None,
) -> None:
    """Fetch and persist Bybit spot instruments-info for configured symbols."""
    settings = _settings()
    repository = _repo(settings)
    selected_symbols = _parse_symbols(symbols, settings)

    async def _run() -> None:
        async with BybitRestClient(base_url=settings.bybit_base_url) as client:
            specs = await refresh_instruments_once(
                repository=repository,
                client=client,
                symbols=selected_symbols,
            )
            _print_json([spec.as_dict() for spec in specs])

    asyncio.run(_run())


@app.command("instrument-loop")
def instrument_loop(
    symbols: Annotated[str | None, typer.Option(help="Comma-separated symbols")] = None,
    once: Annotated[bool, typer.Option("--once/--loop", help="Run once then exit")] = False,
    service_name: Annotated[
        str, typer.Option(help="Service name used for heartbeat")
    ] = "instrument-sync",
) -> None:
    """Continuously refresh Bybit spot instrument constraints."""
    settings = _settings()
    repository = _repo(settings)
    selected_symbols = _parse_symbols(symbols, settings)

    async def _run() -> None:
        async with BybitRestClient(base_url=settings.bybit_base_url) as client:
            await run_instrument_loop(
                settings=settings,
                repository=repository,
                client=client,
                symbols=selected_symbols,
                service_name=service_name,
                once=once,
            )

    asyncio.run(_run())


@app.command("fetch-fng")
def fetch_fng(
    limit: Annotated[int, typer.Option(help="Number of daily FNG values to cache")] = 30,
) -> None:
    """Fetch and cache Alternative.me Crypto Fear & Greed Index values."""
    settings = _settings()
    repository = _repo(settings)

    async def _run() -> None:
        context = await refresh_fear_greed_cache(
            settings=settings,
            repository=repository,
            limit=limit,
        )
        _print_json(context.as_dict() if context else None)

    asyncio.run(_run())


@app.command("fng-loop")
def fng_loop(
    once: Annotated[bool, typer.Option("--once/--loop", help="Run once then exit")] = False,
    service_name: Annotated[str, typer.Option(help="Service name used for heartbeat")] = "fng-sync",
) -> None:
    """Continuously refresh cached Alternative.me Fear & Greed values."""
    settings = _settings()
    repository = _repo(settings)

    async def _run() -> None:
        await run_fng_loop(
            settings=settings,
            repository=repository,
            service_name=service_name,
            once=once,
        )

    asyncio.run(_run())


@app.command("list-fng")
def list_fng(limit: Annotated[int, typer.Option(help="Rows to show")] = 30) -> None:
    """Show cached Fear & Greed Index values with required attribution."""
    settings = _settings()
    repository = _repo(settings)
    rows = repository.list_fear_greed_values(limit=limit)
    table = Table(title="Crypto Fear & Greed Index — data source: Alternative.me")
    for column in ["timestamp", "value", "classification", "fetched_at", "source"]:
        table.add_column(column)
    for row in rows:
        table.add_row(
            str(row["timestamp"]),
            str(row["value"]),
            str(row["classification"]),
            str(row["fetched_at"]),
            str(row["source"]),
        )
    console.print(table)


@app.command("list-instruments")
def list_instruments(limit: Annotated[int, typer.Option(help="Rows to show")] = 100) -> None:
    """Show persisted exchange instrument constraints."""
    settings = _settings()
    repository = _repo(settings)
    rows = repository.list_instrument_specs(limit=limit)
    table = Table(title="Instrument specs")
    for column in [
        "symbol",
        "status",
        "tick",
        "qty_step",
        "min_amount",
        "min_qty",
        "max_limit_qty",
        "updated_at",
    ]:
        table.add_column(column)
    for row in rows:
        table.add_row(
            str(row["symbol"]),
            str(row["status"]),
            str(row["price_tick_size"]),
            str(row["qty_step"]),
            str(row["min_order_amount"]),
            str(row["min_order_qty"]),
            str(row["max_limit_order_qty"]),
            str(row["updated_at"]),
        )
    console.print(table)


@app.command("paper-fill-once")
def paper_fill_once(
    symbol: Annotated[str, typer.Option(help="Spot symbol, e.g. BTCUSDT")] = "BTCUSDT",
) -> None:
    """Apply paper fill simulation to active intents using current public market data."""
    settings = _settings()
    repository = _repo(settings)

    async def _run() -> None:
        async with BybitRestClient(base_url=settings.bybit_base_url) as client:
            fills = await run_paper_fill_once(
                settings=settings,
                repository=repository,
                client=client,
                symbol=symbol.upper(),
            )
            _print_json([fill.as_dict() for fill in fills])

    asyncio.run(_run())


@app.command("paper-loop")
def paper_loop(
    symbols: Annotated[str | None, typer.Option(help="Comma-separated symbols")] = None,
    once: Annotated[bool, typer.Option("--once/--loop", help="Run once then exit")] = False,
    service_name: Annotated[
        str, typer.Option(help="Service name used for heartbeat")
    ] = "paper-runner",
) -> None:
    """Continuously simulate fills for active local order intents."""
    settings = _settings()
    repository = _repo(settings)
    selected_symbols = _parse_symbols(symbols, settings)

    async def _run() -> None:
        async with BybitRestClient(base_url=settings.bybit_base_url) as client:
            await run_paper_loop(
                settings=settings,
                repository=repository,
                client=client,
                symbols=selected_symbols,
                service_name=service_name,
                once=once,
            )

    asyncio.run(_run())


@app.command("validate-key")
def validate_key() -> None:
    """Validate that the configured API key is read-only."""
    settings = _settings()

    async def _run() -> None:
        async with BybitRestClient(
            base_url=settings.bybit_base_url,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
            recv_window=settings.bybit_recv_window,
        ) as client:
            info = await validate_read_only_key(settings=settings, client=client)
            _print_json(info)

    asyncio.run(_run())


@app.command("sync-account")
def sync_account(
    symbols: Annotated[str | None, typer.Option(help="Comma-separated symbols")] = None,
) -> None:
    """Read-only sync: key info, balances, open orders and executions."""
    settings = _settings()
    repository = _repo(settings)
    selected_symbols = _parse_symbols(symbols, settings)

    async def _run() -> None:
        async with BybitRestClient(
            base_url=settings.bybit_base_url,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
            recv_window=settings.bybit_recv_window,
        ) as client:
            result = await sync_account_once(
                settings=settings,
                repository=repository,
                client=client,
                symbols=selected_symbols,
            )
            _print_json(result.as_dict())

    asyncio.run(_run())


@app.command("instrument-info")
def instrument_info(
    symbol: Annotated[str, typer.Option(help="Spot symbol, e.g. BTCUSDT")] = "BTCUSDT",
) -> None:
    """Fetch Bybit spot instrument filters: tick size, lot step and minimum notional."""
    settings = _settings()

    async def _run() -> None:
        async with BybitRestClient(
            base_url=settings.bybit_base_url,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
            recv_window=settings.bybit_recv_window,
        ) as client:
            info = await client.get_instrument_info(symbol.upper(), category="spot")
            _print_json(info.as_dict())

    asyncio.run(_run())


@app.command("paper-step")
def paper_step(
    symbol: Annotated[str, typer.Option(help="Spot symbol, e.g. BTCUSDT")] = "BTCUSDT",
) -> None:
    """Evaluate active local intents against fresh market data and mark paper fills."""
    settings = _settings()
    repository = _repo(settings)

    async def _run() -> None:
        async with BybitRestClient(
            base_url=settings.bybit_base_url,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
            recv_window=settings.bybit_recv_window,
        ) as client:
            snapshot = await client.get_market_snapshot(
                symbol.upper(),
                kline_interval=settings.kline_interval,
                kline_limit=settings.kline_limit,
                orderbook_limit=settings.orderbook_limit,
                recent_trades_limit=settings.recent_trades_limit,
            )
            fills = PaperFillSimulator(
                repository,
                mode=settings.paper_fill_mode,
                min_fill_ratio=settings.paper_min_fill_ratio,
                max_trade_age_seconds=settings.paper_max_trade_age_seconds,
            ).simulate_snapshot(snapshot)
            _print_json([fill.as_dict() for fill in fills])

    asyncio.run(_run())


@app.command("ws-print")
def ws_print(
    symbols: Annotated[str | None, typer.Option(help="Comma-separated symbols")] = None,
    seconds: Annotated[int, typer.Option(help="Seconds to stream; 0 means forever")] = 30,
    orderbook_depth: Annotated[
        int,
        typer.Option(help="Public orderbook depth topic, e.g. 1/50/200/1000"),
    ] = 1,
) -> None:
    """Print public Bybit spot WebSocket messages for tickers, trades and orderbook."""
    settings = _settings()
    selected_symbols = _parse_symbols(symbols, settings)
    topics: list[str] = []
    for item in selected_symbols:
        topics.extend(
            [f"tickers.{item}", f"publicTrade.{item}", f"orderbook.{orderbook_depth}.{item}"]
        )

    async def _consume() -> None:
        client = BybitPublicWebSocketClient(url=settings.bybit_public_ws_spot_url)
        async for payload in client.stream(topics):
            _print_json(payload)

    async def _run() -> None:
        if seconds <= 0:
            await _consume()
            return
        try:
            async with asyncio.timeout(seconds):
                await _consume()
        except TimeoutError:
            console.print(f"Stopped after {seconds} seconds")

    asyncio.run(_run())


@app.command("ws-snapshot")
def ws_snapshot(
    symbols: Annotated[str | None, typer.Option(help="Comma-separated symbols")] = None,
    seconds: Annotated[int, typer.Option(help="Seconds to collect public WS data")] = 10,
) -> None:
    """Collect public WS data briefly and print local cache diagnostics."""
    settings = _settings()
    selected_symbols = _parse_symbols(symbols, settings)

    async def _run() -> None:
        cache = await collect_ws_cache_for_seconds(
            settings=settings,
            symbols=selected_symbols,
            seconds=seconds,
        )
        _print_json(cache.diagnostics())

    asyncio.run(_run())


@app.command("ws-book")
def ws_book(
    symbols: Annotated[str | None, typer.Option(help="Comma-separated symbols")] = None,
    seconds: Annotated[int, typer.Option(help="Seconds to stream; 0 means forever")] = 30,
    depth: Annotated[int, typer.Option(help="Orderbook depth topic, e.g. 1/50/200/1000")] = 50,
) -> None:
    """Maintain a local public WS orderbook and print top-of-book updates."""
    settings = _settings()
    selected_symbols = _parse_symbols(symbols, settings)

    async def _consume() -> None:
        client = BybitPublicWebSocketClient(url=settings.bybit_public_ws_spot_url)
        async for orderbook in client.stream_orderbooks(symbols=selected_symbols, depth=depth):
            _print_json(
                {
                    "symbol": orderbook.symbol,
                    "ts": orderbook.ts.isoformat(),
                    "best_bid": orderbook.best_bid,
                    "best_ask": orderbook.best_ask,
                    "mid": orderbook.mid,
                }
            )

    async def _run() -> None:
        if seconds <= 0:
            await _consume()
            return
        try:
            async with asyncio.timeout(seconds):
                await _consume()
        except TimeoutError:
            console.print(f"Stopped after {seconds} seconds")

    asyncio.run(_run())


@app.command("download-klines")
def download_klines(
    symbol: Annotated[str, typer.Option(help="Spot symbol, e.g. BTCUSDT")] = "BTCUSDT",
    start: Annotated[
        str, typer.Option(help="UTC start, e.g. 2026-06-01 or ISO timestamp")
    ] = "2026-06-01",
    end: Annotated[
        str, typer.Option(help="UTC end, e.g. 2026-06-02 or ISO timestamp")
    ] = "2026-06-02",
    interval: Annotated[str, typer.Option(help="Bybit kline interval, e.g. 1,5,15,60,D")] = "1",
    output: Annotated[Path, typer.Option(help="Output CSV path")] = Path("data/klines.csv"),
) -> None:
    """Download historical Bybit spot klines to CSV for offline backtesting."""
    settings = _settings()
    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end)

    async def _run() -> None:
        async with BybitRestClient(base_url=settings.bybit_base_url) as client:
            candles = await fetch_historical_klines(
                client=client,
                symbol=symbol.upper(),
                interval=interval,
                start=start_dt,
                end=end_dt,
            )
            write_candles_csv(output, candles)
            console.print(f"Saved {len(candles)} candles to {output}")

    asyncio.run(_run())


@app.command("backtest-fetch")
def backtest_fetch(
    symbol: Annotated[str, typer.Option(help="Spot symbol, e.g. BTCUSDT")] = "BTCUSDT",
    start: Annotated[
        str, typer.Option(help="UTC start, e.g. 2026-06-01 or ISO timestamp")
    ] = "2026-06-01",
    end: Annotated[
        str, typer.Option(help="UTC end, e.g. 2026-06-02 or ISO timestamp")
    ] = "2026-06-02",
    interval: Annotated[str, typer.Option(help="Bybit kline interval, e.g. 1,5,15,60,D")] = "1",
    save: Annotated[bool, typer.Option("--save/--no-save", help="Persist summary to DB")] = True,
) -> None:
    """Fetch historical klines and run candle-level backtest."""
    settings = _settings()
    repository = _repo(settings)
    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end)

    async def _run() -> None:
        async with BybitRestClient(base_url=settings.bybit_base_url) as client:
            instrument = await client.get_instrument_info(symbol.upper(), category="spot")
            repository.save_instrument_spec(instrument)
            candles = await fetch_historical_klines(
                client=client,
                symbol=symbol.upper(),
                interval=interval,
                start=start_dt,
                end=end_dt,
            )
            result = _run_backtest(
                settings=settings,
                repository=repository,
                symbol=symbol.upper(),
                interval=interval,
                candles=candles,
                instrument=instrument,
            )
            payload = result.as_dict()
            if save:
                payload["backtest_run_id"] = repository.save_backtest_result(result)
            _print_json(payload)

    asyncio.run(_run())


@app.command("backtest-csv")
def backtest_csv(
    symbol: Annotated[str, typer.Option(help="Spot symbol, e.g. BTCUSDT")] = "BTCUSDT",
    interval: Annotated[str, typer.Option(help="Bybit kline interval used in the CSV")] = "1",
    input_path: Annotated[
        Path, typer.Option("--input", help="CSV with ts,open,high,low,close,volume")
    ] = Path("data/klines.csv"),
    save: Annotated[bool, typer.Option("--save/--no-save", help="Persist summary to DB")] = True,
) -> None:
    """Run candle-level backtest from a local CSV file."""
    settings = _settings()
    repository = _repo(settings)
    candles = read_candles_csv(input_path)
    instrument = repository.get_latest_instrument_spec(symbol.upper()) or InstrumentSpec.fallback(
        symbol.upper()
    )
    result = _run_backtest(
        settings=settings,
        repository=repository,
        symbol=symbol.upper(),
        interval=interval,
        candles=candles,
        instrument=instrument,
    )
    payload = result.as_dict()
    if save:
        payload["backtest_run_id"] = repository.save_backtest_result(result)
    _print_json(payload)


@app.command("list-backtests")
def list_backtests(limit: Annotated[int, typer.Option(help="Rows to show")] = 20) -> None:
    """Show persisted backtest summaries."""
    settings = _settings()
    repository = _repo(settings)
    _print_json(repository.list_backtests(limit=limit))


@app.command("list-backtest-fills")
def list_backtest_fills(
    run_id: Annotated[str | None, typer.Option(help="Backtest run id")] = None,
    limit: Annotated[int, typer.Option(help="Rows to show")] = 100,
) -> None:
    """Show persisted backtest fills."""
    settings = _settings()
    repository = _repo(settings)
    _print_json(repository.list_backtest_fills(run_id=run_id, limit=limit))


@app.command("list-intents")
def list_intents(limit: Annotated[int, typer.Option(help="Rows to show")] = 20) -> None:
    """Show recent order intents."""
    settings = _settings()
    repository = _repo(settings)
    rows = repository.list_recent_intents(limit=limit)
    table = Table(title="Recent order intents")
    for column in ["id", "symbol", "side", "limit_price", "qty", "status", "created_at"]:
        table.add_column(column)
    for row in rows:
        table.add_row(
            str(row["id"]),
            str(row["symbol"]),
            str(row["side"]),
            str(row["limit_price"]),
            str(row["qty"]),
            str(row["status"]),
            str(row["created_at"]),
        )
    console.print(table)


@app.command("list-signals")
def list_signals(limit: Annotated[int, typer.Option(help="Rows to show")] = 20) -> None:
    """Show recent signals."""
    settings = _settings()
    repository = _repo(settings)
    _print_json(repository.list_recent_signals(limit=limit))


@app.command("list-paper-fills")
def list_paper_fills(limit: Annotated[int, typer.Option(help="Rows to show")] = 20) -> None:
    """Show recent paper fills."""
    settings = _settings()
    repository = _repo(settings)
    _print_json(repository.list_recent_paper_fills(limit=limit))


@app.command("list-services")
def list_services(limit: Annotated[int, typer.Option(help="Rows to show")] = 50) -> None:
    """Show service heartbeat rows for compose deployments."""
    settings = _settings()
    repository = _repo(settings)
    _print_json(repository.list_service_heartbeats(limit=limit))


@app.command("list-locks")
def list_locks(limit: Annotated[int, typer.Option(help="Rows to show")] = 50) -> None:
    """Show active/recent DB strategy locks."""
    settings = _settings()
    repository = _repo(settings)
    _print_json(repository.list_strategy_locks(limit=limit))


@app.command("list-positions")
def list_positions(limit: Annotated[int, typer.Option(help="Rows to show")] = 20) -> None:
    """Show local positions created by manual or paper fill confirmations."""
    settings = _settings()
    repository = _repo(settings)
    _print_json(repository.list_positions(limit=limit))


@app.command("mark-filled")
def mark_filled(
    intent_id: Annotated[str, typer.Option(help="Order intent id")],
    price: Annotated[float, typer.Option(help="Actual fill price")],
    qty: Annotated[float, typer.Option(help="Actual filled quantity")],
) -> None:
    """Manually confirm that an external/manual order intent has been filled."""
    settings = _settings()
    repository = _repo(settings)
    repository.mark_intent_filled(intent_id, fill_price=price, fill_qty=qty)
    console.print(f"Intent marked as filled: {intent_id}")


@app.command("api")
def api(
    host: Annotated[str, typer.Option(help="Bind host")] = "0.0.0.0",
    port: Annotated[int, typer.Option(help="Bind port")] = 8080,
) -> None:
    """Run a small read-only HTTP API for recent signals/intents."""
    import uvicorn

    settings = _settings()
    # Create SQLite database path before uvicorn imports the app.
    if settings.database_url.startswith("sqlite:///"):
        sqlite_path = settings.database_url.replace("sqlite:///", "", 1)
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    uvicorn.run(create_app(settings), host=host, port=port)


if __name__ == "__main__":
    app()
