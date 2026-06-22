from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from adaptive_bybit_bot.domain.enums import Regime, Side, SignalAction


def utc_now() -> datetime:
    return datetime.now(UTC)


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
