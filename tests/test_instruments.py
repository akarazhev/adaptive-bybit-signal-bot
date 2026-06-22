from __future__ import annotations

from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.domain.models import InstrumentSpec
from adaptive_bybit_bot.exchange.bybit_client import BybitRestClient


def test_instrument_spec_normalizes_price_qty_and_validates_notional() -> None:
    spec = InstrumentSpec(
        symbol="BTCUSDT",
        price_tick_size=0.1,
        qty_step=0.001,
        min_order_amount_quote=10.0,
        max_limit_order_qty=2.0,
    )

    assert spec.normalize_price(100.19, Side.BUY) == 100.1
    assert spec.normalize_price(100.11, Side.SELL) == 100.2
    assert spec.normalize_qty(0.1239) == 0.123
    assert spec.validate_limit_order(price=100.0, qty=0.05) == ["notional_below_min:5<10"]
    assert spec.validate_limit_order(price=100.0, qty=0.2) == []


def test_bybit_instrument_parser_reads_spot_filters() -> None:
    row = {
        "symbol": "ETHUSDT",
        "status": "Trading",
        "baseCoin": "ETH",
        "quoteCoin": "USDT",
        "priceFilter": {"tickSize": "0.01"},
        "lotSizeFilter": {
            "basePrecision": "0.000001",
            "quotePrecision": "0.00000001",
            "minOrderAmt": "5",
            "maxLimitOrderQty": "999",
        },
    }

    spec = BybitRestClient._parse_instrument_spec(row, category="spot", requested_symbol="ETHUSDT")

    assert spec.symbol == "ETHUSDT"
    assert spec.base_coin == "ETH"
    assert spec.quote_coin == "USDT"
    assert spec.price_tick_size == 0.01
    assert spec.qty_step == 0.000001
    assert spec.min_order_amount_quote == 5.0
