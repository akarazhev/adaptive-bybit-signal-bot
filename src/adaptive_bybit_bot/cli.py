from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from adaptive_bybit_bot.api.app import create_app
from adaptive_bybit_bot.config import Settings, get_settings
from adaptive_bybit_bot.data.db import create_database_engine, create_schema
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.exchange.bybit_client import BybitRestClient
from adaptive_bybit_bot.exchange.bybit_ws import BybitPublicWebSocketClient
from adaptive_bybit_bot.logging_config import configure_logging
from adaptive_bybit_bot.services.account_sync import sync_account_once, validate_read_only_key
from adaptive_bybit_bot.services.market_loop import (
    refresh_instruments_once,
    run_forever,
    run_paper_fill_once,
    run_symbol_once,
)

app = typer.Typer(no_args_is_help=True, help="Adaptive Bybit spot signal/order-intent bot.")
console = Console()


def _settings() -> Settings:
    settings = get_settings()
    configure_logging(settings.log_level)
    return settings


def _repo(settings: Settings) -> BotRepository:
    engine = create_database_engine(settings.database_url)
    create_schema(engine)
    return BotRepository(engine)


def _parse_symbols(value: str | None, settings: Settings) -> list[str]:
    if not value:
        return settings.symbols
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _print_json(payload: object) -> None:
    console.print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("init-db")
def init_db() -> None:
    """Create database tables."""
    settings = _settings()
    engine = create_database_engine(settings.database_url)
    create_schema(engine)
    console.print(f"Database initialized: {settings.database_url}")


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
