from __future__ import annotations

import math


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def round_price(price: float, *, tick_size: float = 0.01, side: str = "BUY") -> float:
    if tick_size <= 0:
        return price
    if side.upper() == "BUY":
        return math.floor(price / tick_size) * tick_size
    return math.ceil(price / tick_size) * tick_size


def round_qty(qty: float, *, step: float = 0.000001) -> float:
    if step <= 0:
        return qty
    return math.floor(qty / step) * step


def bps_diff(new_price: float, old_price: float) -> float:
    if old_price <= 0:
        return 0.0
    return (new_price / old_price - 1) * 10_000
