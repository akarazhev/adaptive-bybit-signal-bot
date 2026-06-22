from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.domain.models import (
    Candle,
    DerivativesContext,
    MarketSnapshot,
    OrderBook,
    OrderBookLevel,
    Trade,
)
from adaptive_bybit_bot.features.engine import FeatureEngine
from adaptive_bybit_bot.features.indicators import atr, ema, ema_series, rsi, vwap, zscore


def candles(count: int = 60) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Candle(
            ts=start + timedelta(minutes=i),
            open=100 + i * 0.1,
            high=101 + i * 0.1,
            low=99 + i * 0.1,
            close=100 + i * 0.1,
            volume=10 + i,
        )
        for i in range(count)
    ]


def test_feature_engine_builds_full_feature_set() -> None:
    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        ts=datetime.now(UTC),
        candles=candles(240),
        orderbook=OrderBook(
            symbol="BTCUSDT",
            ts=datetime.now(UTC),
            bids=[OrderBookLevel(price=123.8, qty=2), OrderBookLevel(price=123.7, qty=1)],
            asks=[OrderBookLevel(price=124.0, qty=1), OrderBookLevel(price=124.1, qty=1)],
        ),
        trades=[
            Trade(ts=datetime.now(UTC), price=123.9, qty=2, side=Side.BUY),
            Trade(ts=datetime.now(UTC), price=123.8, qty=1, side=Side.SELL),
        ],
        derivatives=DerivativesContext(
            funding_rates=[0.001, 0.002, 0.003],
            open_interest_values=[100, 110],
        ),
    )

    features = FeatureEngine().build(snapshot)

    assert features.symbol == "BTCUSDT"
    assert features.spread_bps > 0
    assert features.microprice is not None
    assert features.trade_imbalance == pytest.approx(1 / 3)
    assert features.open_interest_change_pct == pytest.approx(10)


def test_feature_engine_rejects_empty_candles_and_handles_empty_books() -> None:
    engine = FeatureEngine()
    empty_book = OrderBook(symbol="BTCUSDT", ts=datetime.now(UTC), bids=[], asks=[])

    with pytest.raises(ValueError, match="candles"):
        engine.build(
            MarketSnapshot(
                symbol="BTCUSDT",
                ts=datetime.now(UTC),
                candles=[],
                orderbook=empty_book,
                trades=[],
            )
        )

    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        ts=datetime.now(UTC),
        candles=candles(3),
        orderbook=empty_book,
        trades=[],
    )
    features = engine.build(snapshot)
    assert features.spread_bps == 10_000.0
    assert features.orderbook_imbalance is None
    assert features.microprice is None
    assert features.trade_imbalance is None


def test_indicator_edge_cases() -> None:
    with pytest.raises(ValueError):
        ema([1.0], 0)
    with pytest.raises(ValueError):
        ema_series([1.0], 0)
    with pytest.raises(ValueError):
        atr(candles(2), 0)
    with pytest.raises(ValueError):
        rsi([1.0, 2.0], 0)

    assert ema([], 3) is None
    assert ema_series([], 3) == []
    assert atr([candles(1)[0]]) is None
    assert rsi([1.0]) is None
    assert rsi([1.0, 1.0, 1.0]) == 50.0
    assert vwap([], 3) is None
    assert vwap([Candle(datetime.now(UTC), 1, 1, 1, 1, 0)], 1) is None
    assert zscore([1.0]) is None
    assert zscore([1.0, 1.0]) == 0.0
