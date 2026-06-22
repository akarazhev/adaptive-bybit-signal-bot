from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, cast

import pytest

from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.exchange.bybit_client import BybitApiError, BybitRestClient


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeAsyncClient:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = payloads
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    async def get(
        self,
        url: str,
        *,
        params: object = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        self.requests.append({"url": url, "params": params, "headers": headers or {}})
        return FakeResponse(self.payloads.pop(0))

    async def aclose(self) -> None:
        self.closed = True


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def ok(result: Any) -> dict[str, Any]:
    return {"retCode": 0, "result": result}


def test_bybit_client_builds_market_snapshot_from_public_payloads() -> None:
    fake = FakeAsyncClient(
        [
            ok(
                {
                    "list": [
                        ["2000", "101", "103", "100", "102", "11"],
                        ["1000", "100", "102", "99", "101", "10"],
                    ]
                }
            ),
            ok({"b": [["100", "2"]], "a": [["101", "3"]], "ts": "3000"}),
            ok(
                {
                    "list": [
                        {"time": "5000", "price": "101", "size": "0.2", "side": "Sell"},
                        {"time": "4000", "price": "100", "size": "0.1", "side": "Buy"},
                    ]
                }
            ),
            ok({"list": [{"fundingRate": "0.001"}, {"fundingRate": "0.002"}]}),
            ok({"list": [{"openInterest": "10"}, {"openInterest": "12"}]}),
        ]
    )
    client = BybitRestClient(client=cast(Any, fake))

    snapshot = run(client.get_market_snapshot("BTCUSDT"))

    assert [candle.close for candle in snapshot.candles] == [101.0, 102.0]
    assert snapshot.orderbook.best_bid == 100.0
    assert [trade.side for trade in snapshot.trades] == [Side.BUY, Side.SELL]
    assert snapshot.derivatives.funding_rates == [0.002, 0.001]
    assert snapshot.derivatives.open_interest_values == [12.0, 10.0]


def test_bybit_client_signed_request_headers_and_read_only_validation() -> None:
    fake = FakeAsyncClient([ok({"readOnly": 1})])
    client = BybitRestClient(api_key="key", api_secret="secret", client=cast(Any, fake))

    info = run(client.assert_read_only_key())

    assert info == {"readOnly": 1}
    headers = fake.requests[0]["headers"]
    assert headers["X-BAPI-API-KEY"] == "key"
    assert headers["X-BAPI-SIGN"]


def test_bybit_client_rejects_bybit_error_and_non_read_only_key() -> None:
    error_client = BybitRestClient(client=cast(Any, FakeAsyncClient([{"retCode": 10001}])))
    with pytest.raises(BybitApiError):
        run(error_client.get_klines("BTCUSDT"))

    write_key_client = BybitRestClient(
        api_key="key",
        api_secret="secret",
        client=cast(Any, FakeAsyncClient([ok({"readOnly": 0})])),
    )
    with pytest.raises(BybitApiError):
        run(write_key_client.assert_read_only_key())


def test_bybit_client_private_read_methods_return_result_dicts() -> None:
    fake = FakeAsyncClient(
        [
            ok({"wallet": []}),
            ok({"orders": []}),
            ok({"list": []}),
            ok([]),
        ]
    )
    client = BybitRestClient(api_key="key", api_secret="secret", client=cast(Any, fake))

    assert run(client.get_wallet_balance(coins=["BTC", "USDT"])) == {"wallet": []}
    assert run(client.get_open_orders(symbol="BTCUSDT")) == {"orders": []}
    assert run(client.get_trade_history(symbol="BTCUSDT")) == {"list": []}
    assert run(client.query_api_key_info()) == {}


def test_bybit_client_requires_credentials_for_signed_calls() -> None:
    client = BybitRestClient(client=cast(Any, FakeAsyncClient([])))

    with pytest.raises(BybitApiError, match="required"):
        run(client.query_api_key_info())
