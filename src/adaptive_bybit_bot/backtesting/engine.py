from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from adaptive_bybit_bot.domain.enums import OrderIntentStatus, Side, SignalAction
from adaptive_bybit_bot.domain.models import (
    Candle,
    DerivativesContext,
    FearGreedContext,
    FearGreedValue,
    InstrumentSpec,
    MarketSnapshot,
    OrderBook,
    OrderBookLevel,
    PositionState,
    SignalDecision,
)
from adaptive_bybit_bot.features.engine import FeatureEngine
from adaptive_bybit_bot.sentiment.policy import FearGreedSentimentPolicy
from adaptive_bybit_bot.strategy.regime import RegimeClassifier
from adaptive_bybit_bot.strategy.risk import RiskConfig
from adaptive_bybit_bot.strategy.strategy import StrategyEngine


def ensure_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def interval_to_timedelta(interval: str) -> timedelta:
    """Convert Bybit kline interval tokens to a timedelta."""
    normalized = interval.strip().upper()
    if normalized.isdigit():
        return timedelta(minutes=int(normalized))
    mapping = {
        "D": timedelta(days=1),
        "W": timedelta(weeks=1),
        "M": timedelta(days=31),
    }
    if normalized not in mapping:
        raise ValueError(f"unsupported kline interval: {interval}")
    return mapping[normalized]


@dataclass(frozen=True)
class BacktestConfig:
    initial_quote: float = 1_000.0
    lookback_candles: int = 240
    synthetic_spread_bps: float = 2.0
    synthetic_depth_quote: float = 10_000.0
    maker_fee_bps: float = 10.0
    fill_model: str = "touch"
    interval: str = "1"
    force_close: bool = True
    sentiment_enabled: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "initial_quote": self.initial_quote,
            "lookback_candles": self.lookback_candles,
            "synthetic_spread_bps": self.synthetic_spread_bps,
            "synthetic_depth_quote": self.synthetic_depth_quote,
            "maker_fee_bps": self.maker_fee_bps,
            "fill_model": self.fill_model,
            "interval": self.interval,
            "force_close": self.force_close,
            "sentiment_enabled": self.sentiment_enabled,
        }


@dataclass
class BacktestIntent:
    id: str
    symbol: str
    side: str
    limit_price: float
    qty: float
    created_at: datetime
    expires_at: datetime | None = None
    status: str = OrderIntentStatus.ACTIVE.value


@dataclass(frozen=True)
class BacktestFill:
    ts: datetime
    intent_id: str
    symbol: str
    side: str
    price: float
    qty: float
    fee_quote: float
    cash_after: float
    base_after: float
    reason: str
    pnl_quote: float | None = None

    @property
    def realized_pnl_quote(self) -> float | None:
        return self.pnl_quote

    def as_dict(self) -> dict[str, object]:
        return {
            "ts": self.ts.isoformat(),
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "qty": self.qty,
            "fee_quote": self.fee_quote,
            "cash_after": self.cash_after,
            "base_after": self.base_after,
            "reason": self.reason,
            "pnl_quote": self.pnl_quote,
        }


@dataclass(frozen=True)
class BacktestDecisionEvent:
    ts: datetime
    action: str
    regime: str
    price: float | None
    qty: float | None
    confidence: float
    expected_edge_bps: float
    reason: list[str]
    metadata: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "ts": self.ts.isoformat(),
            "action": self.action,
            "regime": self.regime,
            "price": self.price,
            "qty": self.qty,
            "confidence": self.confidence,
            "expected_edge_bps": self.expected_edge_bps,
            "reason": self.reason,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    started_at: datetime
    finished_at: datetime
    candles: int
    decisions: list[BacktestDecisionEvent]
    fills: list[BacktestFill]
    initial_quote: float
    final_quote_equity: float
    realized_quote: float
    unrealized_quote: float
    return_pct: float
    max_drawdown_pct: float
    win_rate: float
    closed_round_trips: int
    open_base_qty: float
    open_avg_entry: float
    interval: str
    config: BacktestConfig

    @property
    def start_ts(self) -> datetime:
        return self.started_at

    @property
    def end_ts(self) -> datetime:
        return self.finished_at

    @property
    def candle_count(self) -> int:
        return self.candles

    @property
    def decision_count(self) -> int:
        return len(self.decisions)

    @property
    def fill_count(self) -> int:
        return len(self.fills)

    def summary_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "candles": self.candles,
            "initial_quote": self.initial_quote,
            "final_quote_equity": self.final_quote_equity,
            "realized_quote": self.realized_quote,
            "unrealized_quote": self.unrealized_quote,
            "return_pct": self.return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "win_rate": self.win_rate,
            "closed_round_trips": self.closed_round_trips,
            "open_base_qty": self.open_base_qty,
            "open_avg_entry": self.open_avg_entry,
            "fill_count": len(self.fills),
            "decision_count": len(self.decisions),
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "config": self.config.as_dict(),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "candles": self.candles,
            "initial_quote": self.initial_quote,
            "final_quote_equity": self.final_quote_equity,
            "realized_quote": self.realized_quote,
            "unrealized_quote": self.unrealized_quote,
            "return_pct": self.return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "win_rate": self.win_rate,
            "closed_round_trips": self.closed_round_trips,
            "open_base_qty": self.open_base_qty,
            "open_avg_entry": self.open_avg_entry,
            "fills": [fill.as_dict() for fill in self.fills],
            "decision_count": len(self.decisions),
            "last_decisions": [event.as_dict() for event in self.decisions[-20:]],
        }


class CandleBacktestRunner:
    """Candle-level backtester for the production order-intent strategy.

    It is intentionally conservative and simple: it cannot model real queue
    position, partial fills or true intrabar order sequencing. Use it as a
    rejection/diagnostic tool before live paper/shadow testing.
    """

    def __init__(
        self,
        *,
        risk: RiskConfig,
        instrument: InstrumentSpec,
        config: BacktestConfig | None = None,
        sentiment_policy: FearGreedSentimentPolicy | None = None,
        sentiment_provider: Callable[
            [datetime],
            FearGreedContext | FearGreedValue | None,
        ]
        | None = None,
    ) -> None:
        self.risk = risk
        self.instrument = instrument
        self.config = config or BacktestConfig(maker_fee_bps=risk.spot_maker_fee_bps)
        self.sentiment_policy = sentiment_policy or FearGreedSentimentPolicy()
        self.sentiment_provider = sentiment_provider
        if self.config.fill_model not in {"touch", "trade_through"}:
            raise ValueError("fill_model must be 'touch' or 'trade_through'")

    def run(self, candles: list[Candle], *, symbol: str | None = None) -> BacktestResult:
        candles = sorted(candles, key=lambda candle: ensure_utc(candle.ts))
        min_needed = max(60, min(self.config.lookback_candles, 240))
        if len(candles) < min_needed:
            raise ValueError(f"at least {min_needed} candles are required for backtest")

        backtest_symbol = (symbol or self.instrument.symbol or "UNKNOWN").upper()
        cash = self.config.initial_quote
        base_qty = 0.0
        avg_entry = 0.0
        active_buy: BacktestIntent | None = None
        active_sell: BacktestIntent | None = None
        fills: list[BacktestFill] = []
        decisions: list[BacktestDecisionEvent] = []
        equity_curve: list[float] = []
        closed_trade_pnls: list[float] = []
        pending_entry_cost = 0.0
        position_opened_at: datetime | None = None

        feature_engine = FeatureEngine()
        regime_classifier = RegimeClassifier(self.risk)
        strategy = StrategyEngine(
            self.risk,
            instrument=self.instrument,
            sentiment_policy=self.sentiment_policy,
        )

        start_index = min(self.config.lookback_candles, len(candles) - 1)
        for index in range(start_index, len(candles)):
            candle = candles[index]
            active_buy, active_sell, cash, base_qty, avg_entry, pending_entry_cost, new_fills = (
                self._simulate_fills_for_candle(
                    candle=candle,
                    active_buy=active_buy,
                    active_sell=active_sell,
                    cash=cash,
                    base_qty=base_qty,
                    avg_entry=avg_entry,
                    pending_entry_cost=pending_entry_cost,
                )
            )
            for fill in new_fills:
                if fill.side == Side.BUY.value and position_opened_at is None:
                    position_opened_at = fill.ts
                if fill.side == Side.SELL.value and base_qty <= 0:
                    position_opened_at = None
                if fill.pnl_quote is not None:
                    closed_trade_pnls.append(fill.pnl_quote)
            fills.extend(new_fills)

            active_buy = self._expire_if_needed(active_buy, candle.ts)
            active_sell = self._expire_if_needed(active_sell, candle.ts)

            position = PositionState(
                symbol=backtest_symbol,
                qty=base_qty,
                avg_entry=avg_entry,
                opened_at=position_opened_at if base_qty > 0 else None,
            )
            window = candles[max(0, index - self.config.lookback_candles + 1) : index + 1]
            snapshot = MarketSnapshot(
                symbol=backtest_symbol,
                ts=ensure_utc(candle.ts),
                candles=window,
                orderbook=self._synthetic_book(backtest_symbol, candle.close, candle.ts),
                trades=[],
                derivatives=DerivativesContext(),
            )
            features = feature_engine.build(snapshot)
            regime = regime_classifier.classify(features)
            sentiment = (
                self.sentiment_provider(ensure_utc(candle.ts))
                if self.sentiment_provider is not None
                else None
            )
            decision = strategy.evaluate(
                features=features,
                regime=regime,
                position=position,
                active_buy=active_buy,
                active_sell=active_sell,
                now=ensure_utc(candle.ts),
                sentiment=sentiment,
            )
            decisions.append(
                BacktestDecisionEvent(
                    ts=ensure_utc(candle.ts),
                    action=decision.action.value,
                    regime=decision.regime.value,
                    price=decision.price,
                    qty=decision.qty,
                    confidence=decision.confidence,
                    expected_edge_bps=decision.expected_edge_bps,
                    reason=decision.reason,
                    metadata=decision.metadata,
                )
            )
            active_buy, active_sell = self._apply_decision(decision, active_buy, active_sell)
            equity_curve.append(cash + base_qty * candle.close)

        if self.config.force_close and base_qty > 0:
            cash, base_qty, avg_entry, pending_entry_cost, force_fill = self._force_close(
                candle=candles[-1],
                cash=cash,
                base_qty=base_qty,
                avg_entry=avg_entry,
                pending_entry_cost=pending_entry_cost,
                symbol=backtest_symbol,
            )
            fills.append(force_fill)
            if force_fill.pnl_quote is not None:
                closed_trade_pnls.append(force_fill.pnl_quote)
            position_opened_at = None
            equity_curve.append(cash)

        last_close = candles[-1].close
        final_equity = cash + base_qty * last_close
        realized_quote = cash - self.config.initial_quote
        if base_qty > 0:
            realized_quote += pending_entry_cost
        unrealized_quote = base_qty * (last_close - avg_entry) if base_qty > 0 else 0.0
        wins = [pnl for pnl in closed_trade_pnls if pnl > 0]
        return BacktestResult(
            symbol=backtest_symbol,
            started_at=ensure_utc(candles[start_index].ts),
            finished_at=ensure_utc(candles[-1].ts),
            candles=len(candles),
            decisions=decisions,
            fills=fills,
            initial_quote=self.config.initial_quote,
            final_quote_equity=final_equity,
            realized_quote=realized_quote,
            unrealized_quote=unrealized_quote,
            return_pct=(final_equity / self.config.initial_quote - 1) * 100,
            max_drawdown_pct=_max_drawdown_pct(equity_curve),
            win_rate=len(wins) / len(closed_trade_pnls) if closed_trade_pnls else 0.0,
            closed_round_trips=len(closed_trade_pnls),
            open_base_qty=base_qty,
            open_avg_entry=avg_entry,
            interval=self.config.interval,
            config=self.config,
        )

    def _simulate_fills_for_candle(
        self,
        *,
        candle: Candle,
        active_buy: BacktestIntent | None,
        active_sell: BacktestIntent | None,
        cash: float,
        base_qty: float,
        avg_entry: float,
        pending_entry_cost: float,
    ) -> tuple[
        BacktestIntent | None,
        BacktestIntent | None,
        float,
        float,
        float,
        float,
        list[BacktestFill],
    ]:
        fills: list[BacktestFill] = []
        fee_rate = self.config.maker_fee_bps / 10_000

        if active_buy is not None and _limit_touched(active_buy, candle, self.config.fill_model):
            gross = active_buy.limit_price * active_buy.qty
            fee = gross * fee_rate
            total_cost = gross + fee
            if cash >= total_cost:
                cash -= total_cost
                new_base = base_qty + active_buy.qty
                avg_entry = (
                    ((avg_entry * base_qty) + (active_buy.limit_price * active_buy.qty)) / new_base
                    if new_base > 0
                    else 0.0
                )
                base_qty = new_base
                pending_entry_cost += total_cost
                fills.append(
                    BacktestFill(
                        ts=ensure_utc(candle.ts),
                        intent_id=active_buy.id,
                        symbol=active_buy.symbol,
                        side=Side.BUY.value,
                        price=active_buy.limit_price,
                        qty=active_buy.qty,
                        fee_quote=fee,
                        cash_after=cash,
                        base_after=base_qty,
                        reason="candle_low_touched_buy_limit",
                    )
                )
                active_buy = None

        if (
            active_sell is not None
            and base_qty > 0
            and _limit_touched(active_sell, candle, self.config.fill_model)
        ):
            sell_qty = min(active_sell.qty, base_qty)
            gross = active_sell.limit_price * sell_qty
            fee = gross * fee_rate
            proceeds = gross - fee
            entry_cost_released = (
                pending_entry_cost * (sell_qty / base_qty) if base_qty > 0 else 0.0
            )
            cash += proceeds
            base_qty = max(base_qty - sell_qty, 0.0)
            pending_entry_cost = max(pending_entry_cost - entry_cost_released, 0.0)
            if base_qty <= 1e-12:
                base_qty = 0.0
                avg_entry = 0.0
                pending_entry_cost = 0.0
            fills.append(
                BacktestFill(
                    ts=ensure_utc(candle.ts),
                    intent_id=active_sell.id,
                    symbol=active_sell.symbol,
                    side=Side.SELL.value,
                    price=active_sell.limit_price,
                    qty=sell_qty,
                    fee_quote=fee,
                    cash_after=cash,
                    base_after=base_qty,
                    reason="candle_high_touched_sell_limit",
                    pnl_quote=proceeds - entry_cost_released,
                )
            )
            active_sell = None

        return active_buy, active_sell, cash, base_qty, avg_entry, pending_entry_cost, fills

    def _force_close(
        self,
        *,
        candle: Candle,
        cash: float,
        base_qty: float,
        avg_entry: float,
        pending_entry_cost: float,
        symbol: str,
    ) -> tuple[float, float, float, float, BacktestFill]:
        fee_rate = self.config.maker_fee_bps / 10_000
        price = candle.close
        gross = price * base_qty
        fee = gross * fee_rate
        proceeds = gross - fee
        cash += proceeds
        fill = BacktestFill(
            ts=ensure_utc(candle.ts),
            intent_id="force-close",
            symbol=symbol,
            side=Side.SELL.value,
            price=price,
            qty=base_qty,
            fee_quote=fee,
            cash_after=cash,
            base_after=0.0,
            reason="force_close_end_of_backtest",
            pnl_quote=proceeds - pending_entry_cost,
        )
        return cash, 0.0, 0.0, 0.0, fill

    def _apply_decision(
        self,
        decision: SignalDecision,
        active_buy: BacktestIntent | None,
        active_sell: BacktestIntent | None,
    ) -> tuple[BacktestIntent | None, BacktestIntent | None]:
        if decision.action in {SignalAction.BUY_INTENT, SignalAction.SELL_INTENT}:
            intent = _intent_from_decision(decision)
            if decision.side == Side.BUY:
                return intent, active_sell
            return active_buy, intent

        if decision.action == SignalAction.REPRICE_INTENT:
            intent = _intent_from_decision(decision)
            if decision.side == Side.BUY:
                return intent, active_sell
            return active_buy, intent

        if decision.action == SignalAction.CANCEL_INTENT:
            if decision.side == Side.BUY:
                return None, active_sell
            if decision.side == Side.SELL:
                return active_buy, None
            return None, None

        return active_buy, active_sell

    @staticmethod
    def _expire_if_needed(intent: BacktestIntent | None, now: datetime) -> BacktestIntent | None:
        if intent is None or intent.expires_at is None:
            return intent
        return None if ensure_utc(intent.expires_at) <= ensure_utc(now) else intent

    def _synthetic_book(self, symbol: str, mid: float, ts: datetime) -> OrderBook:
        half_spread = self.config.synthetic_spread_bps / 20_000
        bid = self.instrument.normalize_price(mid * (1 - half_spread), Side.BUY)
        ask = self.instrument.normalize_price(mid * (1 + half_spread), Side.SELL)
        qty = self.config.synthetic_depth_quote / max(mid, 1e-9)
        return OrderBook(
            symbol=symbol,
            ts=ensure_utc(ts),
            bids=[OrderBookLevel(price=bid, qty=qty)],
            asks=[OrderBookLevel(price=ask, qty=qty)],
        )


def _intent_from_decision(decision: SignalDecision) -> BacktestIntent:
    if decision.side is None or decision.price is None or decision.qty is None:
        raise ValueError("decision does not contain a complete limit intent")
    expires_at = (
        decision.ts + timedelta(seconds=decision.ttl_seconds)
        if decision.ttl_seconds
        else None
    )
    return BacktestIntent(
        id=decision.replaces_intent_id or str(uuid4()),
        symbol=decision.symbol,
        side=decision.side.value,
        limit_price=decision.price,
        qty=decision.qty,
        created_at=ensure_utc(decision.ts),
        expires_at=ensure_utc(expires_at) if expires_at else None,
    )


def _limit_touched(intent: BacktestIntent, candle: Candle, fill_model: str) -> bool:
    if ensure_utc(intent.created_at) >= ensure_utc(candle.ts):
        return False
    if intent.side == Side.BUY.value:
        return (
            candle.low < intent.limit_price
            if fill_model == "trade_through"
            else candle.low <= intent.limit_price
        )
    return (
        candle.high > intent.limit_price
        if fill_model == "trade_through"
        else candle.high >= intent.limit_price
    )


def _max_drawdown_pct(equity_curve: list[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, (value / peak - 1) * 100)
    return abs(max_dd)
