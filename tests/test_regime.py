from __future__ import annotations

from datetime import UTC, datetime

from adaptive_bybit_bot.domain.enums import Regime
from adaptive_bybit_bot.domain.models import FeatureSet
from adaptive_bybit_bot.strategy.regime import RegimeClassifier
from adaptive_bybit_bot.strategy.risk import RiskConfig


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
        vwap=100.4,
        vwap_deviation_bps=-40.0,
        orderbook_imbalance=0.1,
        microprice=100.0,
        trade_imbalance=0.0,
        funding_rate=0.0001,
        funding_zscore=0.0,
        open_interest_change_pct=0.0,
    )
    base.update(overrides)
    return FeatureSet(**base)  # type: ignore[arg-type]


def test_range_regime() -> None:
    classifier = RegimeClassifier(RiskConfig())
    assessment = classifier.classify(make_features())
    assert assessment.regime == Regime.RANGE


def test_shock_regime_has_priority_over_trend() -> None:
    classifier = RegimeClassifier(RiskConfig(shock_atr_pct=1.0))
    assessment = classifier.classify(
        make_features(atr_pct=1.2, ema20=110, ema50=100, ema20_slope_bps=30)
    )
    assert assessment.regime == Regime.SHOCK


def test_uptrend_pullback_regime() -> None:
    classifier = RegimeClassifier(RiskConfig())
    assessment = classifier.classify(
        make_features(ema20=105, ema50=100, ema20_slope_bps=20, vwap_deviation_bps=-20, rsi14=50)
    )
    assert assessment.regime == Regime.UPTREND_PULLBACK
