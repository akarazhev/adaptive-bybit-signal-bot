from __future__ import annotations

from dataclasses import dataclass

from adaptive_bybit_bot.domain.enums import Regime
from adaptive_bybit_bot.domain.models import FeatureSet
from adaptive_bybit_bot.strategy.risk import RiskConfig


@dataclass(frozen=True)
class RegimeAssessment:
    regime: Regime
    confidence: float
    reason: list[str]

    def as_dict(self) -> dict[str, object]:
        return {"regime": self.regime.value, "confidence": self.confidence, "reason": self.reason}


class RegimeClassifier:
    """Rule-based market-regime classifier.

    It intentionally uses conservative no-trade states. A missed trade is cheaper than an
    unbounded stuck position in a micro-profit strategy.
    """

    def __init__(self, risk: RiskConfig) -> None:
        self.risk = risk

    def classify(self, features: FeatureSet) -> RegimeAssessment:
        if features.spread_bps > self.risk.max_spread_bps:
            return RegimeAssessment(
                Regime.NO_TRADE,
                0.90,
                [f"spread_too_wide:{features.spread_bps:.2f}bps"],
            )

        if features.atr_pct is not None and features.atr_pct >= self.risk.shock_atr_pct:
            return RegimeAssessment(
                Regime.SHOCK,
                min(0.95, 0.60 + features.atr_pct / max(self.risk.shock_atr_pct, 0.01) * 0.20),
                [f"atr_shock:{features.atr_pct:.3f}%"],
            )

        if not self._has_trend_inputs(features):
            return RegimeAssessment(Regime.NO_TRADE, 0.50, ["insufficient_trend_inputs"])

        assert features.ema20 is not None
        assert features.ema50 is not None
        assert features.ema20_slope_bps is not None

        vwap_dev = features.vwap_deviation_bps or 0.0
        rsi = features.rsi14 or 50.0
        slope = features.ema20_slope_bps

        if features.ema20 < features.ema50 and slope < -5 and features.last_price < features.ema50:
            return RegimeAssessment(
                Regime.DOWNTREND,
                min(0.90, 0.55 + abs(slope) / 100),
                ["ema20_below_ema50", f"ema20_slope:{slope:.2f}bps"],
            )

        if features.ema20 > features.ema50 and slope > 5:
            if vwap_dev <= -8 and rsi <= 62:
                return RegimeAssessment(
                    Regime.UPTREND_PULLBACK,
                    min(0.90, 0.60 + abs(vwap_dev) / 200 + slope / 300),
                    [
                        "ema20_above_ema50",
                        f"pullback_to_vwap:{vwap_dev:.2f}bps",
                        f"rsi:{rsi:.1f}",
                    ],
                )
            return RegimeAssessment(
                Regime.UPTREND,
                min(0.85, 0.55 + slope / 250),
                ["ema20_above_ema50", f"ema20_slope:{slope:.2f}bps"],
            )

        if abs(slope) <= 12 and abs(vwap_dev) <= 80:
            confidence = 0.60
            if features.atr_pct is not None and features.atr_pct < self.risk.max_atr_pct:
                confidence += 0.10
            if (
                features.orderbook_imbalance is not None
                and abs(features.orderbook_imbalance) < 0.35
            ):
                confidence += 0.05
            return RegimeAssessment(
                Regime.RANGE,
                min(confidence, 0.80),
                ["flat_ema20", f"vwap_deviation:{vwap_dev:.2f}bps"],
            )

        return RegimeAssessment(Regime.NO_TRADE, 0.50, ["ambiguous_market_structure"])

    @staticmethod
    def _has_trend_inputs(features: FeatureSet) -> bool:
        return all(
            value is not None
            for value in [features.ema20, features.ema50, features.ema20_slope_bps]
        )
