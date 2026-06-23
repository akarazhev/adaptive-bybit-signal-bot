from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from adaptive_bybit_bot.domain.enums import Regime, SignalAction
from adaptive_bybit_bot.domain.models import FeatureSet, InstrumentSpec, PositionState
from adaptive_bybit_bot.strategy.regime import RegimeAssessment
from adaptive_bybit_bot.strategy.risk import RiskConfig
from adaptive_bybit_bot.strategy.strategy import StrategyEngine


@dataclass(frozen=True)
class DummyIntent:
    id: str
    side: str
    limit_price: float
    qty: float


def make_features(**overrides: object) -> FeatureSet:
    base = dict(
        symbol="BTCUSDT",
        ts=datetime.now(UTC),
        last_price=100.0,
        mid_price=100.0,
        best_bid=99.99,
        best_ask=100.01,
        spread_bps=2.0,
        ema20=100.0,
        ema50=100.0,
        ema200=100.0,
        ema20_slope_bps=0.0,
        atr_pct=0.2,
        rsi14=45.0,
        vwap=100.5,
        vwap_deviation_bps=-50.0,
        orderbook_imbalance=0.2,
        microprice=100.0,
        trade_imbalance=0.1,
        funding_rate=0.0001,
        funding_zscore=0.0,
        open_interest_change_pct=0.0,
    )
    base.update(overrides)
    return FeatureSet(**base)  # type: ignore[arg-type]


def test_strategy_creates_buy_intent_when_edge_covers_costs() -> None:
    engine = StrategyEngine(RiskConfig(min_expected_edge_bps=30))
    decision = engine.evaluate(
        features=make_features(),
        regime=RegimeAssessment(Regime.RANGE, 0.75, ["test_range"]),
        position=PositionState(symbol="BTCUSDT"),
    )
    assert decision.action == SignalAction.BUY_INTENT
    assert decision.price is not None and decision.price <= 99.99
    assert decision.qty is not None and decision.qty > 0


def test_strategy_caps_buy_intent_quote_to_max_position_quote() -> None:
    max_position_quote = 250.0
    engine = StrategyEngine(
        RiskConfig(
            order_quote_usdt=1_000.0,
            max_position_quote_usdt=max_position_quote,
            min_expected_edge_bps=30,
        )
    )

    decision = engine.evaluate(
        features=make_features(),
        regime=RegimeAssessment(Regime.RANGE, 0.75, ["test_range"]),
        position=PositionState(symbol="BTCUSDT"),
    )

    assert decision.action == SignalAction.BUY_INTENT
    assert decision.price is not None
    assert decision.qty is not None
    assert decision.price * decision.qty <= max_position_quote
    assert decision.metadata["max_position_quote_usdt"] == max_position_quote


def test_strategy_holds_when_edge_too_small() -> None:
    engine = StrategyEngine(RiskConfig(min_expected_edge_bps=60))
    decision = engine.evaluate(
        features=make_features(vwap_deviation_bps=-5.0),
        regime=RegimeAssessment(Regime.RANGE, 0.75, ["test_range"]),
        position=PositionState(symbol="BTCUSDT"),
    )
    assert decision.action == SignalAction.HOLD


def test_strategy_reprices_active_buy_when_desired_price_moves() -> None:
    engine = StrategyEngine(RiskConfig(reprice_threshold_bps=2, min_expected_edge_bps=30))
    decision = engine.evaluate(
        features=make_features(),
        regime=RegimeAssessment(Regime.RANGE, 0.75, ["test_range"]),
        position=PositionState(symbol="BTCUSDT"),
        active_buy=DummyIntent(id="old", side="BUY", limit_price=99.0, qty=0.5),
    )
    assert decision.action == SignalAction.REPRICE_INTENT
    assert decision.replaces_intent_id == "old"


def test_strategy_creates_sell_intent_for_open_position() -> None:
    engine = StrategyEngine(RiskConfig())
    decision = engine.evaluate(
        features=make_features(last_price=101.0, mid_price=101.0, best_bid=100.99, best_ask=101.01),
        regime=RegimeAssessment(Regime.RANGE, 0.70, ["test_range"]),
        position=PositionState(symbol="BTCUSDT", qty=0.1, avg_entry=100.0),
    )
    assert decision.action == SignalAction.SELL_INTENT
    assert decision.price is not None and decision.price >= 100.0


def test_strategy_allows_small_reduce_only_exit_with_filter_warnings() -> None:
    engine = StrategyEngine(
        RiskConfig(),
        instrument=InstrumentSpec(
            symbol="BTCUSDT",
            price_tick_size=0.01,
            qty_step=0.001,
            min_order_qty=0.001,
            min_order_amount_quote=5.0,
        ),
    )

    decision = engine.evaluate(
        features=make_features(last_price=101.0, mid_price=101.0, best_bid=100.99, best_ask=101.01),
        regime=RegimeAssessment(Regime.RANGE, 0.70, ["test_range"]),
        position=PositionState(symbol="BTCUSDT", qty=0.0001, avg_entry=100.0),
    )

    assert decision.action == SignalAction.SELL_INTENT
    assert "reduce_only_exit_below_instrument_minimum" in decision.reason
    assert decision.metadata["instrument_filter_warnings"]
