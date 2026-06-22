from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from adaptive_bybit_bot.domain.models import Candle
from adaptive_bybit_bot.features.indicators import atr, ema, rsi, vwap


def candles(count: int = 20) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Candle(
            ts=start + timedelta(minutes=i),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100 + i,
            volume=10 + i,
        )
        for i in range(count)
    ]


def test_ema_returns_last_weighted_value() -> None:
    assert ema([1, 2, 3, 4, 5], 3) == pytest.approx(4.0)


def test_atr_is_positive() -> None:
    assert atr(candles(), 14) == pytest.approx(2.0)


def test_rsi_uptrend_is_high() -> None:
    assert rsi([1, 2, 3, 4, 5, 6], 5) == 100.0


def test_vwap_uses_volume() -> None:
    result = vwap(candles(3), 3)
    assert result is not None
    assert result > 100
