from __future__ import annotations

from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.domain.models import InstrumentSpec


def test_instrument_spec_rounds_price_and_qty_to_exchange_filters() -> None:
    spec = InstrumentSpec(
        symbol="BTCUSDT",
        price_tick_size=0.1,
        qty_step=0.001,
        min_order_qty=0.001,
        min_order_amount_quote=10.0,
    )

    assert spec.normalize_price(100.09, Side.BUY) == 100.0
    assert spec.normalize_price(100.01, Side.SELL) == 100.1
    assert spec.normalize_qty(0.0019) == 0.001
    assert spec.validate_limit_order(price=20_000, qty=0.001) == []


def test_instrument_spec_rejects_below_min_notional() -> None:
    spec = InstrumentSpec(
        symbol="BTCUSDT",
        price_tick_size=0.1,
        qty_step=0.001,
        min_order_qty=0.001,
        min_order_amount_quote=10.0,
    )

    errors = spec.validate_limit_order(price=100.0, qty=0.001)

    assert errors
    assert errors[0].startswith("notional_below_min")
