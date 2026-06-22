from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.db import create_database_engine
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.models import (
    Candle,
    InstrumentSpec,
    MarketSnapshot,
    OrderBook,
    OrderBookLevel,
)
from adaptive_bybit_bot.services import market_loop
from adaptive_bybit_bot.services.account_sync import sync_account_once, validate_read_only_key
from adaptive_bybit_bot.services.factory import risk_config_from_settings


class FakeMarketClient:
    async def get_instrument_info(self, symbol: str, *, category: str = "spot") -> InstrumentSpec:
        return InstrumentSpec.fallback(symbol)

    async def get_market_snapshot(self, symbol: str, **_kwargs: Any) -> MarketSnapshot:
        return market_snapshot(symbol)


class FakeAccountClient:
    def __init__(self) -> None:
        self.validated = False

    async def assert_read_only_key(self, *, allow_read_write_key: bool = False) -> dict[str, Any]:
        self.validated = True
        return {"readOnly": 1, "allow": allow_read_write_key}

    async def get_wallet_balance(self, **_kwargs: Any) -> dict[str, Any]:
        return {"list": [{"coin": "USDT", "walletBalance": "100"}]}

    async def get_open_orders(self, symbol: str | None = None) -> dict[str, Any]:
        return {"list": [{"symbol": symbol}]}

    async def get_trade_history(
        self,
        symbol: str | None = None,
        *,
        limit: int = 50,
    ) -> dict[str, Any]:
        return {
            "list": [
                {
                    "execId": f"{symbol}-1",
                    "execTime": "1700000000000",
                    "symbol": symbol,
                    "side": "Buy",
                    "execPrice": "100",
                    "execQty": "0.1",
                    "execFee": "0.01",
                    "feeCurrency": "USDT",
                }
            ]
        }


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path}/bot.db",
        bybit_api_key="key",
        bybit_api_secret="secret",
        symbols=["BTCUSDT"],
        order_quote_usdt=50,
    )


def market_snapshot(symbol: str = "BTCUSDT") -> MarketSnapshot:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = [
        Candle(
            ts=start + timedelta(minutes=i),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0 if i < 239 else 99.6,
            volume=10.0,
        )
        for i in range(240)
    ]
    return MarketSnapshot(
        symbol=symbol,
        ts=start + timedelta(minutes=240),
        candles=candles,
        orderbook=OrderBook(
            symbol=symbol,
            ts=start,
            bids=[OrderBookLevel(price=99.58, qty=2.0)],
            asks=[OrderBookLevel(price=99.60, qty=1.0)],
        ),
        trades=[],
    )


def test_run_symbol_once_persists_cycle_result(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    repository = BotRepository(create_database_engine(settings.database_url))
    repository.create_schema()

    result = run(
        market_loop.run_symbol_once(
            settings=settings,
            repository=repository,
            client=FakeMarketClient(),  # type: ignore[arg-type]
            symbol="BTCUSDT",
        )
    )

    assert result.symbol == "BTCUSDT"
    assert repository.list_recent_signals(limit=1)


def test_run_forever_processes_symbols_and_logs_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/bot.db",
        symbols=["BTCUSDT", "ETHUSDT"],
        service_heartbeat_seconds=0,
    )
    repository = BotRepository(create_database_engine(settings.database_url))
    repository.create_schema()

    async def fake_run_symbol_once(**kwargs: Any) -> None:
        symbol = str(kwargs["symbol"])
        calls.append(symbol)
        if symbol == "ETHUSDT":
            raise RuntimeError("boom")

    async def fake_sleep(_seconds: int) -> None:
        raise StopAsyncIteration

    monkeypatch.setattr(market_loop, "run_symbol_once", fake_run_symbol_once)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(StopAsyncIteration):
        run(
            market_loop.run_forever(
                settings=settings,
                repository=repository,
                client=object(),  # type: ignore[arg-type]
            )
        )

    assert calls == ["BTCUSDT", "ETHUSDT"]


def test_account_sync_validates_key_and_persists_snapshots(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    repository = BotRepository(create_database_engine(settings.database_url))
    repository.create_schema()
    client = FakeAccountClient()

    result = run(
        sync_account_once(
            settings=settings,
            repository=repository,
            client=client,  # type: ignore[arg-type]
            symbols=["BTCUSDT"],
        )
    )

    assert client.validated
    assert result.saved_executions == 1
    assert result.as_dict()["api_key_read_only"] == 1


def test_account_sync_requires_credentials_and_factory_maps_settings(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path}/bot.db", symbols=["BTCUSDT"])
    repository = BotRepository(create_database_engine(settings.database_url))

    with pytest.raises(RuntimeError, match="required"):
        run(
            sync_account_once(
                settings=settings,
                repository=repository,
                client=FakeAccountClient(),  # type: ignore[arg-type]
            )
        )

    client = FakeAccountClient()
    assert run(validate_read_only_key(settings=settings, client=client))["readOnly"] == 1  # type: ignore[arg-type]
    assert risk_config_from_settings(Settings(order_quote_usdt=75)).order_quote_usdt == 75
