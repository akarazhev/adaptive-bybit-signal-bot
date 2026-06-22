from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from adaptive_bybit_bot.domain.enums import Regime, Side, SignalAction


def utc_now() -> datetime:
    return datetime.now(UTC)


def _decimal(value: float | int | str | None, default: str = "0") -> Decimal:
    try:
        if value in (None, ""):
            return Decimal(default)
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _round_to_step(value: float, step: float, rounding: str) -> float:
    if step <= 0:
        return value
    value_d = _decimal(value)
    step_d = _decimal(step)
    if step_d <= 0:
        return value
    mode = ROUND_CEILING if rounding == "ceil" else ROUND_FLOOR
    units = (value_d / step_d).to_integral_value(rounding=mode)
    return float(units * step_d)


@dataclass(frozen=True)
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    qty: float


@dataclass(frozen=True)
class OrderBook:
    symbol: str
    ts: datetime
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2


@dataclass(frozen=True)
class Trade:
    ts: datetime
    price: float
    qty: float
    side: Side | None = None


@dataclass(frozen=True)
class InstrumentSpec:
    """Trading filters for a Bybit instrument, used only for local validation."""

    symbol: str
    category: str = "spot"
    status: str = "Trading"
    base_coin: str | None = None
    quote_coin: str | None = None
    price_tick_size: float = 0.01
    qty_step: float = 0.000001
    min_order_qty: float | None = None
    min_order_amount_quote: float | None = None
    max_limit_order_qty: float | None = None
    max_market_order_qty: float | None = None
    base_precision: float | None = None
    quote_precision: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_trading(self) -> bool:
        return not self.status or self.status.lower() == "trading"

    @property
    def min_order_amt(self) -> float:
        return self.min_order_amount_quote or 0.0

    @classmethod
    def fallback(cls, symbol: str) -> InstrumentSpec:
        return cls(symbol=symbol.upper(), status="Trading")

    def normalize_price(self, price: float, side: Side | str) -> float:
        side_value = side.value if isinstance(side, Side) else side.upper()
        rounding = "floor" if side_value == Side.BUY.value else "ceil"
        return _round_to_step(price, self.price_tick_size, rounding)

    def normalize_qty(self, qty: float) -> float:
        step = self.qty_step or self.base_precision or 0.000001
        return _round_to_step(qty, step, "floor")

    def notional(self, *, price: float, qty: float) -> float:
        return price * qty

    def validate_limit_order(self, *, price: float, qty: float) -> list[str]:
        errors: list[str] = []
        if self.status and self.status.lower() != "trading":
            errors.append(f"instrument_not_trading:{self.status}")
        if price <= 0:
            errors.append("price_must_be_positive")
        if qty <= 0:
            errors.append("qty_must_be_positive")
        if self.min_order_qty is not None and qty < self.min_order_qty:
            errors.append(f"qty_below_min:{qty:g}<{self.min_order_qty:g}")
        if self.max_limit_order_qty is not None and qty > self.max_limit_order_qty:
            errors.append(f"qty_above_max_limit:{qty:g}>{self.max_limit_order_qty:g}")
        if self.min_order_amount_quote is not None:
            notional = self.notional(price=price, qty=qty)
            if notional < self.min_order_amount_quote:
                errors.append(f"notional_below_min:{notional:.8g}<{self.min_order_amount_quote:g}")
        return errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "category": self.category,
            "status": self.status,
            "base_coin": self.base_coin,
            "quote_coin": self.quote_coin,
            "price_tick_size": self.price_tick_size,
            "qty_step": self.qty_step,
            "min_order_qty": self.min_order_qty,
            "min_order_amount_quote": self.min_order_amount_quote,
            "max_limit_order_qty": self.max_limit_order_qty,
            "max_market_order_qty": self.max_market_order_qty,
            "base_precision": self.base_precision,
            "quote_precision": self.quote_precision,
            "raw": self.raw,
        }



@dataclass(frozen=True)
class DerivativesContext:
    funding_rates: list[float] = field(default_factory=list)
    open_interest_values: list[float] = field(default_factory=list)
    liquidation_buy_qty: float = 0.0
    liquidation_sell_qty: float = 0.0


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    ts: datetime
    candles: list[Candle]
    orderbook: OrderBook
    trades: list[Trade]
    derivatives: DerivativesContext = field(default_factory=DerivativesContext)


@dataclass(frozen=True)
class FeatureSet:
    symbol: str
    ts: datetime
    last_price: float
    mid_price: float
    best_bid: float | None
    best_ask: float | None
    spread_bps: float
    ema20: float | None
    ema50: float | None
    ema200: float | None
    ema20_slope_bps: float | None
    atr_pct: float | None
    rsi14: float | None
    vwap: float | None
    vwap_deviation_bps: float | None
    orderbook_imbalance: float | None
    microprice: float | None
    trade_imbalance: float | None
    funding_rate: float | None
    funding_zscore: float | None
    open_interest_change_pct: float | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class PositionState:
    symbol: str
    qty: float = 0.0
    avg_entry: float = 0.0
    opened_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.qty > 0 and self.avg_entry > 0

    def unrealized_pnl_bps(self, current_price: float) -> float:
        if not self.is_open:
            return 0.0
        return (current_price / self.avg_entry - 1.0) * 10_000


@dataclass(frozen=True)
class SignalDecision:
    action: SignalAction
    symbol: str
    side: Side | None
    price: float | None
    qty: float | None
    regime: Regime
    confidence: float
    expected_edge_bps: float
    reason: list[str]
    ttl_seconds: int | None = None
    replaces_intent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    ts: datetime = field(default_factory=utc_now)

    @classmethod
    def hold(
        cls,
        symbol: str,
        regime: Regime,
        reason: list[str],
        confidence: float = 0.0,
        expected_edge_bps: float = 0.0,
    ) -> SignalDecision:
        return cls(
            action=SignalAction.HOLD,
            symbol=symbol,
            side=None,
            price=None,
            qty=None,
            regime=regime,
            confidence=confidence,
            expected_edge_bps=expected_edge_bps,
            reason=reason,
        )
