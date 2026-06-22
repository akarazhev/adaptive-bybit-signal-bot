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
class FearGreedValue:
    """Single Alternative.me Crypto Fear & Greed Index observation.

    The current Alternative.me index is primarily a Bitcoin/crypto-market
    sentiment measure, not a per-symbol spot signal.
    """

    value: int
    classification: str
    timestamp: datetime
    source: str = "alternative.me"
    time_until_update_seconds: int | None = None
    fetched_at: datetime = field(default_factory=utc_now)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def attribution(self) -> str:
        return "Fear & Greed Index data source: Alternative.me"

    @property
    def normalized_classification(self) -> str:
        return self.classification.strip().lower().replace(" ", "_")

    def age_hours(self, now: datetime | None = None) -> float:
        current = now or utc_now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        ts = self.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return max(0.0, (current.astimezone(UTC) - ts.astimezone(UTC)).total_seconds() / 3600)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "value": self.value,
            "classification": self.classification,
            "timestamp": self.timestamp.isoformat(),
            "time_until_update_seconds": self.time_until_update_seconds,
            "fetched_at": self.fetched_at.isoformat(),
            "attribution": self.attribution,
        }


@dataclass(frozen=True)
class FearGreedContext:
    """Latest Fear & Greed value plus simple daily momentum deltas."""

    current: FearGreedValue
    previous_1d: FearGreedValue | None = None
    previous_7d: FearGreedValue | None = None

    @property
    def source(self) -> str:
        return self.current.source

    @property
    def value(self) -> int:
        return self.current.value

    @property
    def classification(self) -> str:
        return self.current.classification

    @property
    def timestamp(self) -> datetime:
        return self.current.timestamp

    @property
    def time_until_update_seconds(self) -> int | None:
        return self.current.time_until_update_seconds

    @property
    def attribution(self) -> str:
        return self.current.attribution

    @property
    def delta_1d(self) -> int | None:
        return self.current.value - self.previous_1d.value if self.previous_1d else None

    @property
    def delta_7d(self) -> int | None:
        return self.current.value - self.previous_7d.value if self.previous_7d else None

    def age_hours(self, now: datetime | None = None) -> float:
        return self.current.age_hours(now)

    def as_dict(self, *, now: datetime | None = None) -> dict[str, Any]:
        payload = self.current.as_dict()
        payload.update(
            {
                "age_hours": self.age_hours(now),
                "delta_1d": self.delta_1d,
                "delta_7d": self.delta_7d,
                "previous_1d": self.previous_1d.as_dict() if self.previous_1d else None,
                "previous_7d": self.previous_7d.as_dict() if self.previous_7d else None,
            }
        )
        return payload

    @classmethod
    def from_values(cls, values: list[FearGreedValue]) -> FearGreedContext | None:
        if not values:
            return None
        ordered = sorted(values, key=lambda item: item.timestamp, reverse=True)
        current = ordered[0]
        previous_1d = ordered[1] if len(ordered) > 1 else None
        previous_7d = ordered[7] if len(ordered) > 7 else None
        return cls(current=current, previous_1d=previous_1d, previous_7d=previous_7d)


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
