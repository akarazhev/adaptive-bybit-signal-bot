from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from adaptive_bybit_bot.backtesting.engine import (
    BacktestDecisionEvent,
    BacktestFill,
    _max_drawdown_pct,
    ensure_utc,
)
from adaptive_bybit_bot.domain.enums import OrderIntentStatus, Side, SignalAction
from adaptive_bybit_bot.domain.models import (
    Candle,
    DerivativesContext,
    FearGreedContext,
    FearGreedValue,
    InstrumentSpec,
    MarketSnapshot,
    PositionState,
    SignalDecision,
    Trade,
)
from adaptive_bybit_bot.features.engine import FeatureEngine
from adaptive_bybit_bot.market_data.orderbook import ms_to_utc, to_float
from adaptive_bybit_bot.market_data.ws_cache import WebSocketMarketDataCache
from adaptive_bybit_bot.recording.jsonl import read_market_events
from adaptive_bybit_bot.sentiment.policy import FearGreedSentimentPolicy
from adaptive_bybit_bot.strategy.regime import RegimeClassifier
from adaptive_bybit_bot.strategy.risk import RiskConfig
from adaptive_bybit_bot.strategy.strategy import StrategyEngine


@dataclass(frozen=True)
class MarketReplayConfig:
    initial_quote: float = 10_000.0
    candle_interval_seconds: int = 60
    evaluation_interval_seconds: int = 10
    warmup_candles: int = 60
    trade_lookback_seconds: int = 120
    maker_fee_bps: float = 10.0
    fill_model: str = "trade_through"
    force_close: bool = True
    sentiment_enabled: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "initial_quote": self.initial_quote,
            "candle_interval_seconds": self.candle_interval_seconds,
            "evaluation_interval_seconds": self.evaluation_interval_seconds,
            "warmup_candles": self.warmup_candles,
            "trade_lookback_seconds": self.trade_lookback_seconds,
            "maker_fee_bps": self.maker_fee_bps,
            "fill_model": self.fill_model,
            "force_close": self.force_close,
            "sentiment_enabled": self.sentiment_enabled,
        }


@dataclass
class ReplayIntent:
    id: str
    symbol: str
    side: str
    limit_price: float
    qty: float
    created_at: datetime
    expires_at: datetime | None = None
    status: str = OrderIntentStatus.ACTIVE.value


@dataclass(frozen=True)
class MarketReplayResult:
    symbol: str
    input_path: str
    recording_session_id: str | None
    started_at: datetime
    finished_at: datetime
    event_count: int
    candle_count: int
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
    config: MarketReplayConfig

    @property
    def decision_count(self) -> int:
        return len(self.decisions)

    @property
    def fill_count(self) -> int:
        return len(self.fills)

    def summary_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "input_path": self.input_path,
            "recording_session_id": self.recording_session_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "event_count": self.event_count,
            "candle_count": self.candle_count,
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
        payload = self.summary_dict()
        payload.update(
            {
                "config": self.config.as_dict(),
                "fills": [fill.as_dict() for fill in self.fills],
                "last_decisions": [event.as_dict() for event in self.decisions[-20:]],
            }
        )
        return payload


class MarketReplayRunner:
    """Replay recorded public WebSocket events through the strategy.

    This replay uses real recorded book/trade/ticker sequencing, but it remains a
    local fill approximation: it does not know our queue position on Bybit.
    """

    def __init__(
        self,
        *,
        risk: RiskConfig,
        instrument: InstrumentSpec,
        config: MarketReplayConfig | None = None,
        sentiment_policy: FearGreedSentimentPolicy | None = None,
        sentiment_provider: Callable[[datetime], FearGreedContext | FearGreedValue | None]
        | None = None,
    ) -> None:
        self.risk = risk
        self.instrument = instrument
        self.config = config or MarketReplayConfig(maker_fee_bps=risk.spot_maker_fee_bps)
        self.sentiment_policy = sentiment_policy or FearGreedSentimentPolicy()
        self.sentiment_provider = sentiment_provider
        if self.config.fill_model not in {"touch", "trade_through"}:
            raise ValueError("fill_model must be 'touch' or 'trade_through'")

    def run_file(
        self,
        path: str | Path,
        *,
        symbol: str,
        recording_session_id: str | None = None,
    ) -> MarketReplayResult:
        symbol = symbol.upper()
        input_path = str(path)
        cache = WebSocketMarketDataCache(symbols=[symbol], orderbook_depth=50)
        candles = _TradeCandleBuilder(interval_seconds=self.config.candle_interval_seconds)
        feature_engine = FeatureEngine()
        regime_classifier = RegimeClassifier(self.risk)
        strategy = StrategyEngine(
            self.risk,
            instrument=self.instrument,
            sentiment_policy=self.sentiment_policy,
        )

        cash = self.config.initial_quote
        base_qty = 0.0
        avg_entry = 0.0
        pending_entry_cost = 0.0
        position_opened_at: datetime | None = None
        active_buy: ReplayIntent | None = None
        active_sell: ReplayIntent | None = None
        fills: list[BacktestFill] = []
        decisions: list[BacktestDecisionEvent] = []
        equity_curve: list[float] = []
        closed_trade_pnls: list[float] = []
        last_eval_at: datetime | None = None
        started_at: datetime | None = None
        finished_at: datetime | None = None
        event_count = 0
        last_price = 0.0

        for event in read_market_events(path):
            if event.event_kind == "control":
                continue
            if event.symbol and event.symbol.upper() != symbol:
                continue
            event_count += 1
            event_time = ensure_utc(event.exchange_ts or event.recorded_at)
            started_at = started_at or event_time
            finished_at = event_time
            cache.handle_message(event.payload)

            trades = _trades_from_payload(event.payload, symbol=symbol)
            for trade in trades:
                candles.update_trade(trade)
                last_price = trade.price or last_price
                (
                    active_buy,
                    active_sell,
                    cash,
                    base_qty,
                    avg_entry,
                    pending_entry_cost,
                    new_fills,
                ) = self._simulate_trade_fills(
                    trade=trade,
                    active_buy=active_buy,
                    active_sell=active_sell,
                    cash=cash,
                    base_qty=base_qty,
                    avg_entry=avg_entry,
                    pending_entry_cost=pending_entry_cost,
                )
                for fill in new_fills:
                    if fill.side == Side.BUY.value and position_opened_at is None:
                        position_opened_at = fill.ts
                    if fill.side == Side.SELL.value and base_qty <= 0:
                        position_opened_at = None
                    if fill.pnl_quote is not None:
                        closed_trade_pnls.append(fill.pnl_quote)
                fills.extend(new_fills)

            active_buy = _expire_if_needed(active_buy, event_time)
            active_sell = _expire_if_needed(active_sell, event_time)

            if not cache.is_ready(symbol):
                continue
            candle_rows = candles.candles()
            if len(candle_rows) < max(1, self.config.warmup_candles):
                continue
            if last_eval_at is not None:
                elapsed = (event_time - last_eval_at).total_seconds()
                if elapsed < self.config.evaluation_interval_seconds:
                    continue
            orderbook = cache.orderbook(symbol)
            if orderbook is None:
                continue
            recent_trades = cache.recent_trades(
                symbol,
                since=event_time - timedelta(seconds=self.config.trade_lookback_seconds),
            )
            snapshot = MarketSnapshot(
                symbol=symbol,
                ts=event_time,
                candles=candle_rows,
                orderbook=orderbook,
                trades=recent_trades,
                derivatives=DerivativesContext(),
            )
            features = feature_engine.build(snapshot)
            regime = regime_classifier.classify(features)
            position = PositionState(
                symbol=symbol,
                qty=base_qty,
                avg_entry=avg_entry,
                opened_at=position_opened_at if base_qty > 0 else None,
            )
            sentiment = (
                self.sentiment_provider(event_time)
                if self.sentiment_provider is not None and self.config.sentiment_enabled
                else None
            )
            decision = strategy.evaluate(
                features=features,
                regime=regime,
                position=position,
                active_buy=active_buy,
                active_sell=active_sell,
                now=event_time,
                sentiment=sentiment,
            )
            decisions.append(
                BacktestDecisionEvent(
                    ts=event_time,
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
            active_buy, active_sell = _apply_decision(decision, event_time, active_buy, active_sell)
            mark_price = last_price or orderbook.mid or features.last_price
            equity_curve.append(cash + base_qty * mark_price)
            last_eval_at = event_time

        if started_at is None or finished_at is None:
            raise ValueError("recording contains no replayable market events for symbol")

        final_mark = last_price or avg_entry
        if self.config.force_close and base_qty > 0 and final_mark > 0:
            fee_rate = self.config.maker_fee_bps / 10_000
            gross = final_mark * base_qty
            fee = gross * fee_rate
            proceeds = gross - fee
            cash += proceeds
            force_fill = BacktestFill(
                ts=finished_at,
                intent_id="force-close",
                symbol=symbol,
                side=Side.SELL.value,
                price=final_mark,
                qty=base_qty,
                fee_quote=fee,
                cash_after=cash,
                base_after=0.0,
                reason="force_close_end_of_replay",
                pnl_quote=proceeds - pending_entry_cost,
            )
            fills.append(force_fill)
            if force_fill.pnl_quote is not None:
                closed_trade_pnls.append(force_fill.pnl_quote)
            base_qty = 0.0
            avg_entry = 0.0
            pending_entry_cost = 0.0
            equity_curve.append(cash)

        final_equity = cash + base_qty * final_mark
        realized_quote = cash - self.config.initial_quote
        if base_qty > 0:
            realized_quote += pending_entry_cost
        unrealized_quote = base_qty * (final_mark - avg_entry) if base_qty > 0 else 0.0
        wins = [pnl for pnl in closed_trade_pnls if pnl > 0]
        return MarketReplayResult(
            symbol=symbol,
            input_path=input_path,
            recording_session_id=recording_session_id,
            started_at=started_at,
            finished_at=finished_at,
            event_count=event_count,
            candle_count=len(candles.candles()),
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
            config=self.config,
        )

    def _simulate_trade_fills(
        self,
        *,
        trade: Trade,
        active_buy: ReplayIntent | None,
        active_sell: ReplayIntent | None,
        cash: float,
        base_qty: float,
        avg_entry: float,
        pending_entry_cost: float,
    ) -> tuple[
        ReplayIntent | None,
        ReplayIntent | None,
        float,
        float,
        float,
        float,
        list[BacktestFill],
    ]:
        fills: list[BacktestFill] = []
        fee_rate = self.config.maker_fee_bps / 10_000

        if active_buy is not None and _trade_fills_intent(
            active_buy, trade, self.config.fill_model
        ):
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
                        ts=ensure_utc(trade.ts),
                        intent_id=active_buy.id,
                        symbol=active_buy.symbol,
                        side=Side.BUY.value,
                        price=active_buy.limit_price,
                        qty=active_buy.qty,
                        fee_quote=fee,
                        cash_after=cash,
                        base_after=base_qty,
                        reason="replay_trade_filled_buy_limit",
                    )
                )
                active_buy = None

        if (
            active_sell is not None
            and base_qty > 0
            and _trade_fills_intent(active_sell, trade, self.config.fill_model)
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
                    ts=ensure_utc(trade.ts),
                    intent_id=active_sell.id,
                    symbol=active_sell.symbol,
                    side=Side.SELL.value,
                    price=active_sell.limit_price,
                    qty=sell_qty,
                    fee_quote=fee,
                    cash_after=cash,
                    base_after=base_qty,
                    reason="replay_trade_filled_sell_limit",
                    pnl_quote=proceeds - entry_cost_released,
                )
            )
            active_sell = None
        return active_buy, active_sell, cash, base_qty, avg_entry, pending_entry_cost, fills


class _TradeCandleBuilder:
    def __init__(self, *, interval_seconds: int) -> None:
        self.interval_seconds = max(1, interval_seconds)
        self._completed: list[Candle] = []
        self._current: Candle | None = None

    def update_trade(self, trade: Trade) -> None:
        ts = _floor_time(ensure_utc(trade.ts), self.interval_seconds)
        price = trade.price
        qty = trade.qty
        if price <= 0:
            return
        if self._current is None:
            self._current = Candle(
                ts=ts, open=price, high=price, low=price, close=price, volume=qty
            )
            return
        if ensure_utc(self._current.ts) != ts:
            self._completed.append(self._current)
            self._current = Candle(
                ts=ts, open=price, high=price, low=price, close=price, volume=qty
            )
            return
        self._current = Candle(
            ts=self._current.ts,
            open=self._current.open,
            high=max(self._current.high, price),
            low=min(self._current.low, price),
            close=price,
            volume=self._current.volume + qty,
        )

    def candles(self) -> list[Candle]:
        rows = list(self._completed)
        if self._current is not None:
            rows.append(self._current)
        return rows


def _floor_time(value: datetime, interval_seconds: int) -> datetime:
    value = ensure_utc(value)
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % interval_seconds), tz=UTC)


def _trades_from_payload(payload: dict[str, Any], *, symbol: str) -> list[Trade]:
    topic = str(payload.get("topic") or "")
    if not topic.startswith("publicTrade."):
        return []
    rows = payload.get("data")
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return []
    trades: list[Trade] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        trade_symbol = str(row.get("s") or symbol).upper()
        if trade_symbol != symbol.upper():
            continue
        side_raw = str(row.get("S") or row.get("side") or "").upper()
        side = Side.BUY if side_raw == "BUY" else Side.SELL if side_raw == "SELL" else None
        trades.append(
            Trade(
                ts=ms_to_utc(row.get("T") or payload.get("ts")),
                price=to_float(row.get("p") or row.get("price")),
                qty=to_float(row.get("v") or row.get("size")),
                side=side,
            )
        )
    return trades


def _trade_fills_intent(intent: ReplayIntent, trade: Trade, fill_model: str) -> bool:
    if ensure_utc(intent.created_at) >= ensure_utc(trade.ts):
        return False
    if intent.side == Side.BUY.value:
        if trade.side not in (Side.SELL, None):
            return False
        return (
            trade.price < intent.limit_price
            if fill_model == "trade_through"
            else trade.price <= intent.limit_price
        )
    if trade.side not in (Side.BUY, None):
        return False
    return (
        trade.price > intent.limit_price
        if fill_model == "trade_through"
        else trade.price >= intent.limit_price
    )


def _expire_if_needed(intent: ReplayIntent | None, now: datetime) -> ReplayIntent | None:
    if intent is None or intent.expires_at is None:
        return intent
    return None if ensure_utc(intent.expires_at) <= ensure_utc(now) else intent


def _apply_decision(
    decision: SignalDecision,
    decision_time: datetime,
    active_buy: ReplayIntent | None,
    active_sell: ReplayIntent | None,
) -> tuple[ReplayIntent | None, ReplayIntent | None]:
    if decision.action in {
        SignalAction.BUY_INTENT,
        SignalAction.SELL_INTENT,
        SignalAction.REPRICE_INTENT,
    }:
        intent = _intent_from_decision(decision, decision_time)
        if decision.side == Side.BUY:
            return intent, active_sell
        if decision.side == Side.SELL:
            return active_buy, intent
    if decision.action == SignalAction.CANCEL_INTENT:
        if decision.side == Side.BUY:
            return None, active_sell
        if decision.side == Side.SELL:
            return active_buy, None
        return None, None
    return active_buy, active_sell


def _intent_from_decision(decision: SignalDecision, decision_time: datetime) -> ReplayIntent:
    if decision.side is None or decision.price is None or decision.qty is None:
        raise ValueError("decision does not contain a complete limit intent")
    expires_at = (
        ensure_utc(decision_time) + timedelta(seconds=decision.ttl_seconds)
        if decision.ttl_seconds
        else None
    )
    return ReplayIntent(
        id=decision.replaces_intent_id or str(uuid4()),
        symbol=decision.symbol,
        side=decision.side.value,
        limit_price=decision.price,
        qty=decision.qty,
        created_at=ensure_utc(decision_time),
        expires_at=expires_at,
    )
