from __future__ import annotations

from datetime import UTC, datetime, timedelta

from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.domain.models import Candle
from adaptive_bybit_bot.market_data.orderbook import LocalOrderBook, LocalOrderBookStore
from adaptive_bybit_bot.market_data.ws_cache import WebSocketMarketDataCache


def test_local_orderbook_applies_snapshot_and_delta() -> None:
    book = LocalOrderBook("BTCUSDT", depth=2)
    snapshot = {
        "topic": "orderbook.50.BTCUSDT",
        "type": "snapshot",
        "ts": 1_700_000_000_000,
        "data": {
            "s": "BTCUSDT",
            "b": [["100.0", "1.0"], ["99.5", "2.0"]],
            "a": [["100.5", "1.5"], ["101.0", "2.5"]],
            "u": 10,
            "seq": 100,
        },
    }
    assert book.apply_message(snapshot)
    orderbook = book.as_orderbook()
    assert orderbook.best_bid == 100.0
    assert orderbook.best_ask == 100.5

    delta = {
        "topic": "orderbook.50.BTCUSDT",
        "type": "delta",
        "ts": 1_700_000_000_100,
        "data": {
            "s": "BTCUSDT",
            "b": [["100.0", "0"], ["99.8", "3.0"]],
            "a": [["100.5", "1.0"], ["101.0", "0"]],
            "u": 11,
            "seq": 101,
        },
    }
    assert book.apply_message(delta)
    orderbook = book.as_orderbook()
    assert orderbook.best_bid == 99.8
    assert orderbook.bids[0].qty == 3.0
    assert orderbook.best_ask == 100.5
    assert len(orderbook.asks) == 1
    assert book.last_update_id == 11


def test_ws_cache_parses_trades_and_ticker() -> None:
    cache = WebSocketMarketDataCache(symbols=["BTCUSDT"], orderbook_depth=2)
    cache.handle_message(
        {
            "topic": "publicTrade.BTCUSDT",
            "type": "snapshot",
            "ts": 1_700_000_000_000,
            "data": [
                {"T": 1_700_000_000_001, "s": "BTCUSDT", "S": "Buy", "v": "0.1", "p": "100"},
                {"T": 1_700_000_000_002, "s": "BTCUSDT", "S": "Sell", "v": "0.2", "p": "99"},
            ],
        }
    )
    trades = cache.recent_trades("BTCUSDT")
    assert len(trades) == 2
    assert trades[0].side == Side.BUY
    assert trades[1].side == Side.SELL
    assert trades[1].qty == 0.2

    assert cache.handle_message(
        {
            "topic": "tickers.BTCUSDT",
            "ts": 1_700_000_000_003,
            "data": {"lastPrice": "101", "bid1Price": "100.5", "ask1Price": "101.5"},
        }
    )
    ticker = cache.tickers["BTCUSDT"]
    assert ticker.last_price == 101.0
    assert ticker.bid1_price == 100.5
    assert ticker.ask1_price == 101.5


def test_ws_cache_builds_snapshot_and_diagnostics_from_orderbook() -> None:
    cache = WebSocketMarketDataCache(symbols=["btcusdt"], orderbook_depth=2)
    assert not cache.is_ready("BTCUSDT")
    assert not cache.handle_message({"topic": "unknown.BTCUSDT", "data": {}})

    assert cache.handle_message(
        {
            "topic": "orderbook.50.BTCUSDT",
            "type": "snapshot",
            "ts": 1_700_000_000_000,
            "data": {
                "s": "BTCUSDT",
                "b": [["100.0", "1.0"]],
                "a": [["100.5", "1.5"]],
                "u": 1,
                "seq": 100,
            },
        }
    )
    assert cache.is_ready("BTCUSDT")
    assert cache.ready_symbols() == ["BTCUSDT"]

    now = datetime.now(UTC)
    snapshot = cache.build_snapshot(
        symbol="BTCUSDT",
        candles=[
            Candle(
                ts=now - timedelta(minutes=1),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=10.0,
            )
        ],
    )
    assert snapshot is not None
    assert snapshot.orderbook.best_bid == 100.0
    diagnostics = cache.diagnostics()
    assert diagnostics["ready_symbols"] == ["BTCUSDT"]
    assert diagnostics["books"]["BTCUSDT"]["spread_bps"] is not None


def test_local_orderbook_store_routes_messages_by_symbol() -> None:
    store = LocalOrderBookStore(["BTCUSDT", "ETHUSDT"], depth=1)
    assert store.apply_message({"topic": "ticker.BTCUSDT", "data": {}}) is None
    assert store.apply_message({"topic": "orderbook.50.XRPUSDT", "data": {}}) is None

    orderbook = store.apply_message(
        {
            "topic": "orderbook.50.ETHUSDT",
            "type": "snapshot",
            "ts": 1_700_000_000_000,
            "data": {
                "s": "ETHUSDT",
                "b": [["2000", "1"], ["1999", "1"]],
                "a": [["2001", "1"], ["2002", "1"]],
            },
        }
    )
    assert orderbook is not None
    assert orderbook.symbol == "ETHUSDT"
    assert len(orderbook.bids) == 1
    assert store.get("ethusdt") is not None
