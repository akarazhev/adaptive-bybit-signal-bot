from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from adaptive_bybit_bot.domain.enums import Regime, SignalAction
from adaptive_bybit_bot.domain.models import FeatureSet, PositionState
from adaptive_bybit_bot.strategy.regime import RegimeAssessment, RegimeClassifier
from adaptive_bybit_bot.strategy.risk import RiskConfig
from adaptive_bybit_bot.strategy.strategy import StrategyEngine


@dataclass(frozen=True)
class Intent:
    id: str
    side: str
    limit_price: float
    qty: float


def features(**overrides: object) -> FeatureSet:
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


def assessment(regime: Regime = Regime.RANGE) -> RegimeAssessment:
    return RegimeAssessment(regime=regime, confidence=0.75, reason=["test"])


def test_strategy_cancels_invalid_existing_intents() -> None:
    engine = StrategyEngine(RiskConfig())

    cancel_sell = engine.evaluate(
        features=features(),
        regime=assessment(),
        position=PositionState(symbol="BTCUSDT"),
        active_sell=Intent("sell", "SELL", 100, 1),
    )
    cancel_buy = engine.evaluate(
        features=features(),
        regime=assessment(),
        position=PositionState(symbol="BTCUSDT", qty=1, avg_entry=100),
        active_buy=Intent("buy", "BUY", 99, 1),
    )

    assert cancel_sell.action == SignalAction.CANCEL_INTENT
    assert cancel_buy.action == SignalAction.CANCEL_INTENT


def test_strategy_hold_paths_for_buy_filters_and_active_sell() -> None:
    engine = StrategyEngine(RiskConfig(min_expected_edge_bps=30, reprice_threshold_bps=100))

    assert (
        engine.evaluate(
            features=features(),
            regime=assessment(Regime.UPTREND),
            position=PositionState(symbol="BTCUSDT"),
        ).action
        == SignalAction.HOLD
    )
    assert (
        engine.evaluate(
            features=features(atr_pct=2.0),
            regime=assessment(),
            position=PositionState(symbol="BTCUSDT"),
        ).action
        == SignalAction.HOLD
    )
    assert (
        engine.evaluate(
            features=features(rsi14=75.0),
            regime=assessment(),
            position=PositionState(symbol="BTCUSDT"),
        ).action
        == SignalAction.HOLD
    )
    assert (
        engine.evaluate(
            features=features(funding_zscore=3.0),
            regime=assessment(),
            position=PositionState(symbol="BTCUSDT"),
        ).action
        == SignalAction.HOLD
    )
    assert (
        engine.evaluate(
            features=features(),
            regime=assessment(),
            position=PositionState(symbol="BTCUSDT", qty=1, avg_entry=100),
            active_sell=Intent("sell", "SELL", 101, 1),
        ).action
        == SignalAction.HOLD
    )


def test_strategy_sell_risk_exit_and_reprice_paths() -> None:
    engine = StrategyEngine(RiskConfig(reprice_threshold_bps=2))
    old_position = PositionState(
        symbol="BTCUSDT",
        qty=1,
        avg_entry=100,
        opened_at=datetime.now(UTC) - timedelta(hours=3),
    )

    risk_exit = engine.evaluate(
        features=features(last_price=98, best_bid=97.99),
        regime=assessment(Regime.DOWNTREND),
        position=old_position,
    )
    reprice = engine.evaluate(
        features=features(last_price=101, mid_price=101, best_bid=100.99, best_ask=101.01),
        regime=assessment(),
        position=PositionState(symbol="BTCUSDT", qty=1, avg_entry=100),
        active_sell=Intent("sell", "SELL", 100.0, 1),
    )

    assert risk_exit.action == SignalAction.SELL_INTENT
    assert risk_exit.metadata["risk_exit"] is True
    assert reprice.action == SignalAction.REPRICE_INTENT


def test_regime_classifier_no_trade_downtrend_and_ambiguous_paths() -> None:
    classifier = RegimeClassifier(RiskConfig(max_spread_bps=5))

    assert classifier.classify(features(spread_bps=6)).regime == Regime.NO_TRADE
    assert (
        classifier.classify(
            features(ema20=95, ema50=100, ema20_slope_bps=-20, last_price=94)
        ).regime
        == Regime.DOWNTREND
    )
    assert (
        classifier.classify(features(ema20=None, ema50=None, ema20_slope_bps=None)).regime
        == Regime.NO_TRADE
    )
    assert (
        classifier.classify(features(ema20=100, ema50=100, ema20_slope_bps=40)).regime
        == Regime.NO_TRADE
    )
