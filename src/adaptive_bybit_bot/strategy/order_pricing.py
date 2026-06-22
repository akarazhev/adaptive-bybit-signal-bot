from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _decimal(value: float | str | Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid decimal value: {value!r}") from exc


def round_to_step(value: float, *, step: float, mode: str = "floor") -> float:
    if step <= 0:
        return value
    rounding = ROUND_CEILING if mode == "ceil" else ROUND_FLOOR
    units = (_decimal(value) / _decimal(step)).to_integral_value(rounding=rounding)
    return float(units * _decimal(step))


def round_price(price: float, *, tick_size: float = 0.01, side: str = "BUY") -> float:
    mode = "floor" if side.upper() == "BUY" else "ceil"
    return round_to_step(price, step=tick_size, mode=mode)


def round_qty(qty: float, *, step: float = 0.000001) -> float:
    return round_to_step(qty, step=step, mode="floor")


def bps_diff(new_price: float, old_price: float) -> float:
    if old_price <= 0:
        return 0.0
    return (new_price / old_price - 1) * 10_000
