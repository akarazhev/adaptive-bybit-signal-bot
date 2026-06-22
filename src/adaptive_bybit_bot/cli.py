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
from adaptive_bybit_bot.logging_config import configure_logging
from adaptive_bybit_bot.services.account_sync import sync_account_once, validate_read_only_key
from adaptive_bybit_bot.services.market_loop import run_forever, run_symbol_once

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
    # Create database path before uvicorn imports the app.
    Path(settings.database_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    uvicorn.run(create_app(settings), host=host, port=port)


if __name__ == "__main__":
    app()
