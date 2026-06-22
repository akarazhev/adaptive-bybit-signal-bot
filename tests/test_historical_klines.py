from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from adaptive_bybit_bot.backtesting.engine import interval_to_timedelta
from adaptive_bybit_bot.backtesting.historical import fetch_historical_klines, parse_datetime
from adaptive_bybit_bot.exchange.bybit_client import BybitRestClient


def test_parse_datetime_and_interval_helpers() -> None:
    assert parse_datetime("2026-06-01").tzinfo is not None
    assert parse_datetime("2026-06-01T12:00:00Z").hour == 12
    assert interval_to_timedelta("15").total_seconds() == 900
    assert interval_to_timedelta("D").days == 1


def test_parse_datetime_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match="datetime value cannot be empty"):
        parse_datetime(" ")


def test_bybit_client_kline_start_end_and_limit_clamp() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 2, tzinfo=UTC)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/market/kline"
        assert request.url.params.get("category") == "spot"
        assert request.url.params.get("symbol") == "BTCUSDT"
        assert request.url.params.get("interval") == "1"
        assert request.url.params.get("limit") == "1000"
        assert request.url.params.get("start") == str(int(start.timestamp() * 1000))
        assert request.url.params.get("end") == str(int(end.timestamp() * 1000))
        return httpx.Response(
            200,
            json={
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "list": [[str(int(start.timestamp() * 1000)), "1", "2", "0.5", "1.5", "10"]]
                },
            },
        )

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BybitRestClient(base_url="https://api.bybit.com", client=http_client)
            candles = await client.get_klines("BTCUSDT", start=start, end=end, limit=5000)
            assert len(candles) == 1
            assert candles[0].close == 1.5

    asyncio.run(run())


def test_fetch_historical_klines_paginates_and_deduplicates() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candle_ms = [int((start.timestamp() + offset * 60) * 1000) for offset in range(4)]
    final_end = datetime.fromtimestamp(candle_ms[-1] / 1000, tz=UTC)
    calls: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        end_param = request.url.params.get("end")
        assert end_param is not None
        calls.append(int(end_param))
        rows = (
            [
                [str(candle_ms[2]), "102", "103", "101", "102.5", "12"],
                [str(candle_ms[3]), "103", "104", "102", "103.5", "13"],
            ]
            if int(end_param) == candle_ms[-1]
            else [
                [str(candle_ms[0]), "100", "101", "99", "100.5", "10"],
                [str(candle_ms[2]), "102", "103", "101", "102.5", "12"],
            ]
        )
        return httpx.Response(
            200,
            json={"retCode": 0, "retMsg": "OK", "result": {"list": rows}},
        )

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BybitRestClient(base_url="https://api.bybit.com", client=http_client)
            candles = await fetch_historical_klines(
                client=client,
                symbol="BTCUSDT",
                interval="1",
                start=start,
                end=final_end,
                page_limit=2,
            )
            assert [candle.ts for candle in candles] == sorted({candle.ts for candle in candles})
            assert [candle.close for candle in candles] == [100.5, 102.5, 103.5]

    asyncio.run(run())
    assert len(calls) == 2


def test_fetch_historical_klines_validates_range_and_limit() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    client = BybitRestClient(base_url="https://api.bybit.com")

    async def run() -> None:
        with pytest.raises(ValueError, match="end must be after start"):
            await fetch_historical_klines(
                client=client,
                symbol="BTCUSDT",
                interval="1",
                start=start,
                end=start,
            )
        with pytest.raises(ValueError, match="page_limit must be positive"):
            await fetch_historical_klines(
                client=client,
                symbol="BTCUSDT",
                interval="1",
                start=start,
                end=datetime(2026, 1, 2, tzinfo=UTC),
                page_limit=0,
            )

    asyncio.run(run())
