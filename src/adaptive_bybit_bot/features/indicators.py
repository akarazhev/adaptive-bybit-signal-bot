from __future__ import annotations

import math

from adaptive_bybit_bot.domain.models import Candle


def ema(values: list[float], period: int) -> float | None:
    if period <= 0:
        raise ValueError("period must be positive")
    if not values:
        return None
    if len(values) < period:
        return sum(values) / len(values)
    alpha = 2 / (period + 1)
    value = sum(values[:period]) / period
    for item in values[period:]:
        value = alpha * item + (1 - alpha) * value
    return value


def ema_series(values: list[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    if not values:
        return []
    alpha = 2 / (period + 1)
    result: list[float] = []
    value = values[0]
    for item in values:
        value = alpha * item + (1 - alpha) * value
        result.append(value)
    return result


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(candles) < 2:
        return None
    true_ranges: list[float] = []
    previous_close = candles[0].close
    for candle in candles[1:]:
        true_range = max(
            candle.high - candle.low,
            abs(candle.high - previous_close),
            abs(candle.low - previous_close),
        )
        true_ranges.append(true_range)
        previous_close = candle.close
    window = true_ranges[-period:]
    if not window:
        return None
    return sum(window) / len(window)


def rsi(values: list[float], period: int = 14) -> float | None:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < 2:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    window = changes[-period:]
    if not window:
        return None
    gains = [max(change, 0.0) for change in window]
    losses = [abs(min(change, 0.0)) for change in window]
    avg_gain = sum(gains) / len(window)
    avg_loss = sum(losses) / len(window)
    if math.isclose(avg_loss, 0.0):
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def vwap(candles: list[Candle], period: int = 50) -> float | None:
    if not candles:
        return None
    window = candles[-period:]
    total_volume = sum(max(candle.volume, 0.0) for candle in window)
    if total_volume <= 0:
        return None
    weighted = sum(candle.close * max(candle.volume, 0.0) for candle in window)
    return weighted / total_volume


def zscore(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((item - mean) ** 2 for item in values) / (len(values) - 1)
    stdev = math.sqrt(variance)
    if math.isclose(stdev, 0.0):
        return 0.0
    return (values[-1] - mean) / stdev
