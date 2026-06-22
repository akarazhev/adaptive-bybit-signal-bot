from __future__ import annotations

import asyncio

import httpx

from adaptive_bybit_bot.exchange.bybit_client import BybitRestClient


def test_bybit_client_parses_spot_instrument_info() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/market/instruments-info"
        return httpx.Response(
            200,
            json={
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "status": "Trading",
                            "baseCoin": "BTC",
                            "quoteCoin": "USDT",
                            "priceFilter": {"tickSize": "0.01"},
                            "lotSizeFilter": {
                                "basePrecision": "0.000001",
                                "quotePrecision": "0.00000001",
                                "minOrderQty": "0.00001",
                                "minOrderAmt": "5",
                                "maxLimitOrderQty": "100",
                            },
                        }
                    ]
                },
            },
        )

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BybitRestClient(base_url="https://api.bybit.com", client=http_client)
            spec = await client.get_instrument_info("BTCUSDT")
            assert spec.symbol == "BTCUSDT"
            assert spec.base_coin == "BTC"
            assert spec.quote_coin == "USDT"
            assert spec.price_tick_size == 0.01
            assert spec.qty_step == 0.000001
            assert spec.min_order_qty == 0.00001
            assert spec.min_order_amount_quote == 5
            assert spec.max_limit_order_qty == 100

    asyncio.run(run())


def test_bybit_client_clamps_spot_recent_trades_limit() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/market/recent-trade"
        assert request.url.params.get("category") == "spot"
        assert request.url.params.get("limit") == "60"
        return httpx.Response(
            200,
            json={
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "price": "100",
                            "size": "0.1",
                            "side": "Buy",
                            "time": "1767225600000",
                        }
                    ]
                },
            },
        )

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BybitRestClient(base_url="https://api.bybit.com", client=http_client)
            trades = await client.get_recent_trades("BTCUSDT", limit=100)
            assert len(trades) == 1
            assert trades[0].price == 100.0

    asyncio.run(run())
