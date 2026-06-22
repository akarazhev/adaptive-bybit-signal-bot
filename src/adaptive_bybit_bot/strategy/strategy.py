from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from adaptive_bybit_bot.domain.enums import Regime, Side, SignalAction
from adaptive_bybit_bot.domain.models import FeatureSet, PositionState, SignalDecision
from adaptive_bybit_bot.strategy.order_pricing import bps_diff, clamp, round_price, round_qty
from adaptive_bybit_bot.strategy.regime import RegimeAssessment
from adaptive_bybit_bot.strategy.risk import RiskConfig


class ActiveIntentLike(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def side(self) -> str: ...

    @property
    def limit_price(self) -> float: ...

    @property
    def qty(self) -> float: ...


class StrategyEngine:
    """Strategy selector and order-intent decision engine.

    The engine never places orders. It returns decisions that repositories persist as
    order intents/events.
    """

    def __init__(self, risk: RiskConfig, *, price_tick_size: float = 0.01) -> None:
        self.risk = risk
        self.price_tick_size = price_tick_size

    def evaluate(
        self,
        *,
        features: FeatureSet,
        regime: RegimeAssessment,
        position: PositionState,
        active_buy: ActiveIntentLike | None = None,
        active_sell: ActiveIntentLike | None = None,
    ) -> SignalDecision:
        if position.is_open:
            if active_buy is not None:
                return SignalDecision(
                    action=SignalAction.CANCEL_INTENT,
                    symbol=features.symbol,
                    side=Side.BUY,
                    price=None,
                    qty=None,
                    regime=regime.regime,
                    confidence=0.85,
                    expected_edge_bps=0.0,
                    reason=["position_open_cancel_extra_buy_intent"],
                    replaces_intent_id=active_buy.id,
                )
            return self._evaluate_sell_side(features, regime, position, active_sell)

        if active_sell is not None:
            return SignalDecision(
                action=SignalAction.CANCEL_INTENT,
                symbol=features.symbol,
                side=Side.SELL,
                price=None,
                qty=None,
                regime=regime.regime,
                confidence=0.85,
                expected_edge_bps=0.0,
                reason=["no_open_position_cancel_sell_intent"],
                replaces_intent_id=active_sell.id,
            )

        return self._evaluate_buy_side(features, regime, active_buy)

    def _evaluate_buy_side(
        self,
        features: FeatureSet,
        regime: RegimeAssessment,
        active_buy: ActiveIntentLike | None,
    ) -> SignalDecision:
        draft = self._build_buy_intent(features, regime)
        if active_buy is None:
            return draft

        if draft.action != SignalAction.BUY_INTENT:
            return SignalDecision(
                action=SignalAction.CANCEL_INTENT,
                symbol=features.symbol,
                side=Side.BUY,
                price=None,
                qty=None,
                regime=regime.regime,
                confidence=max(0.70, draft.confidence),
                expected_edge_bps=draft.expected_edge_bps,
                reason=["buy_intent_no_longer_valid", *draft.reason],
                replaces_intent_id=active_buy.id,
                metadata=draft.metadata,
            )

        diff = abs(bps_diff(draft.price or 0.0, active_buy.limit_price))
        if diff >= self.risk.reprice_threshold_bps:
            return SignalDecision(
                action=SignalAction.REPRICE_INTENT,
                symbol=features.symbol,
                side=Side.BUY,
                price=draft.price,
                qty=draft.qty,
                regime=regime.regime,
                confidence=draft.confidence,
                expected_edge_bps=draft.expected_edge_bps,
                reason=[f"buy_reprice_threshold:{diff:.2f}bps", *draft.reason],
                ttl_seconds=self.risk.order_ttl_seconds,
                replaces_intent_id=active_buy.id,
                metadata=draft.metadata,
            )

        return SignalDecision.hold(
            features.symbol,
            regime.regime,
            ["active_buy_intent_still_valid"],
            confidence=draft.confidence,
            expected_edge_bps=draft.expected_edge_bps,
        )

    def _build_buy_intent(self, features: FeatureSet, regime: RegimeAssessment) -> SignalDecision:
        reasons: list[str] = [*regime.reason]
        expected_edge_bps = self._expected_buy_edge_bps(features, regime.regime)
        required_edge_bps = self.risk.required_buy_edge_bps

        allowed_regimes = {Regime.RANGE, Regime.UPTREND_PULLBACK}
        if regime.regime not in allowed_regimes:
            return SignalDecision.hold(
                features.symbol,
                regime.regime,
                [f"regime_not_buyable:{regime.regime.value}", *reasons],
                confidence=regime.confidence,
                expected_edge_bps=expected_edge_bps,
            )

        if features.atr_pct is not None and features.atr_pct > self.risk.max_atr_pct:
            return SignalDecision.hold(
                features.symbol,
                regime.regime,
                [f"atr_too_high:{features.atr_pct:.3f}%", *reasons],
                confidence=regime.confidence,
                expected_edge_bps=expected_edge_bps,
            )

        if features.rsi14 is not None and features.rsi14 >= 70:
            return SignalDecision.hold(
                features.symbol,
                regime.regime,
                [f"rsi_overbought:{features.rsi14:.1f}", *reasons],
                confidence=regime.confidence,
                expected_edge_bps=expected_edge_bps,
            )

        if features.funding_zscore is not None and features.funding_zscore > 2.5:
            return SignalDecision.hold(
                features.symbol,
                regime.regime,
                [f"crowded_long_funding_zscore:{features.funding_zscore:.2f}", *reasons],
                confidence=regime.confidence,
                expected_edge_bps=expected_edge_bps,
            )

        if expected_edge_bps < required_edge_bps:
            return SignalDecision.hold(
                features.symbol,
                regime.regime,
                [
                    f"edge_too_small:{expected_edge_bps:.2f}bps",
                    f"required:{required_edge_bps:.2f}bps",
                    *reasons,
                ],
                confidence=regime.confidence,
                expected_edge_bps=expected_edge_bps,
            )

        price = self._desired_buy_price(features)
        if price <= 0:
            return SignalDecision.hold(
                features.symbol,
                regime.regime,
                ["invalid_buy_price", *reasons],
                confidence=regime.confidence,
                expected_edge_bps=expected_edge_bps,
            )

        qty = round_qty(self.risk.order_quote_usdt / price)
        if qty <= 0:
            return SignalDecision.hold(
                features.symbol,
                regime.regime,
                ["invalid_buy_qty", *reasons],
                confidence=regime.confidence,
                expected_edge_bps=expected_edge_bps,
            )

        confidence = clamp(
            (expected_edge_bps / max(required_edge_bps * 1.8, 1)) * regime.confidence, 0.25, 0.92
        )
        reasons.extend(
            [
                f"expected_edge:{expected_edge_bps:.2f}bps",
                f"required_edge:{required_edge_bps:.2f}bps",
                f"spread:{features.spread_bps:.2f}bps",
            ]
        )
        return SignalDecision(
            action=SignalAction.BUY_INTENT,
            symbol=features.symbol,
            side=Side.BUY,
            price=price,
            qty=qty,
            regime=regime.regime,
            confidence=confidence,
            expected_edge_bps=expected_edge_bps,
            reason=reasons,
            ttl_seconds=self.risk.order_ttl_seconds,
            metadata={
                "break_even_bps": self.risk.maker_roundtrip_break_even_bps,
                "required_edge_bps": required_edge_bps,
                "vwap_deviation_bps": features.vwap_deviation_bps,
                "orderbook_imbalance": features.orderbook_imbalance,
                "trade_imbalance": features.trade_imbalance,
            },
        )

    def _evaluate_sell_side(
        self,
        features: FeatureSet,
        regime: RegimeAssessment,
        position: PositionState,
        active_sell: ActiveIntentLike | None,
    ) -> SignalDecision:
        draft = self._build_sell_intent(features, regime, position)
        if active_sell is None:
            return draft

        if draft.action != SignalAction.SELL_INTENT:
            return SignalDecision.hold(
                features.symbol,
                regime.regime,
                ["active_sell_intent_present"],
                confidence=draft.confidence,
                expected_edge_bps=draft.expected_edge_bps,
            )

        diff = abs(bps_diff(draft.price or 0.0, active_sell.limit_price))
        if diff >= self.risk.reprice_threshold_bps:
            return SignalDecision(
                action=SignalAction.REPRICE_INTENT,
                symbol=features.symbol,
                side=Side.SELL,
                price=draft.price,
                qty=draft.qty,
                regime=regime.regime,
                confidence=draft.confidence,
                expected_edge_bps=draft.expected_edge_bps,
                reason=[f"sell_reprice_threshold:{diff:.2f}bps", *draft.reason],
                ttl_seconds=self.risk.order_ttl_seconds,
                replaces_intent_id=active_sell.id,
                metadata=draft.metadata,
            )

        return SignalDecision.hold(
            features.symbol,
            regime.regime,
            ["active_sell_intent_still_valid"],
            confidence=draft.confidence,
            expected_edge_bps=draft.expected_edge_bps,
        )

    def _build_sell_intent(
        self,
        features: FeatureSet,
        regime: RegimeAssessment,
        position: PositionState,
    ) -> SignalDecision:
        if not position.is_open:
            return SignalDecision.hold(
                features.symbol,
                regime.regime,
                ["no_open_position"],
                confidence=0.8,
                expected_edge_bps=0.0,
            )

        pnl_bps = position.unrealized_pnl_bps(features.last_price)
        age_seconds = self._position_age_seconds(position)
        target_bps = self.risk.target_sell_profit_bps
        reasons = [*regime.reason, f"unrealized_pnl:{pnl_bps:.2f}bps"]

        risk_exit = False
        if pnl_bps <= -self.risk.max_unrealized_loss_bps:
            risk_exit = True
            reasons.append(f"risk_exit_max_loss:{pnl_bps:.2f}bps")
        if age_seconds is not None and age_seconds >= self.risk.max_position_age_seconds:
            risk_exit = True
            reasons.append(f"risk_exit_position_age:{age_seconds}s")
        if regime.regime in {Regime.SHOCK, Regime.DOWNTREND} and pnl_bps < 0:
            risk_exit = True
            reasons.append(f"risk_exit_regime:{regime.regime.value}")

        if risk_exit:
            raw_price = features.best_bid or features.last_price
            price = round_price(raw_price, tick_size=self.price_tick_size, side="SELL")
            confidence = clamp(0.70 + abs(min(pnl_bps, 0.0)) / 500, 0.70, 0.95)
            return SignalDecision(
                action=SignalAction.SELL_INTENT,
                symbol=features.symbol,
                side=Side.SELL,
                price=price,
                qty=round_qty(position.qty),
                regime=regime.regime,
                confidence=confidence,
                expected_edge_bps=pnl_bps,
                reason=reasons,
                ttl_seconds=self.risk.order_ttl_seconds,
                metadata={"risk_exit": True, "target_sell_profit_bps": target_bps},
            )

        if regime.regime == Regime.UPTREND:
            target_bps += 5
            reasons.append("uptrend_sell_target_extension")
        if (
            regime.regime in {Regime.DOWNTREND, Regime.SHOCK}
            and pnl_bps > self.risk.maker_roundtrip_break_even_bps
        ):
            target_bps = self.risk.maker_roundtrip_break_even_bps + 2
            reasons.append("defensive_profitable_exit")

        target_price = position.avg_entry * (1 + target_bps / 10_000)
        if regime.regime == Regime.RANGE and features.vwap is not None:
            target_price = max(target_price, features.vwap)
            reasons.append("range_sell_near_vwap_or_better")
        if features.best_ask is not None:
            target_price = max(target_price, features.best_ask)

        price = round_price(target_price, tick_size=self.price_tick_size, side="SELL")
        expected_net_bps = (
            price / position.avg_entry - 1
        ) * 10_000 - self.risk.maker_roundtrip_break_even_bps
        confidence = clamp(0.55 + max(expected_net_bps, 0) / 120, 0.55, 0.90)
        reasons.extend(
            [
                f"target_sell_profit:{target_bps:.2f}bps",
                f"expected_net:{expected_net_bps:.2f}bps",
            ]
        )
        return SignalDecision(
            action=SignalAction.SELL_INTENT,
            symbol=features.symbol,
            side=Side.SELL,
            price=price,
            qty=round_qty(position.qty),
            regime=regime.regime,
            confidence=confidence,
            expected_edge_bps=expected_net_bps,
            reason=reasons,
            ttl_seconds=self.risk.order_ttl_seconds,
            metadata={
                "risk_exit": False,
                "avg_entry": position.avg_entry,
                "target_sell_profit_bps": target_bps,
                "break_even_bps": self.risk.maker_roundtrip_break_even_bps,
            },
        )

    def _desired_buy_price(self, features: FeatureSet) -> float:
        atr_bps = (features.atr_pct or 0.0) * 100
        offset_bps = clamp(max(features.spread_bps * 0.75, atr_bps * 0.08, 4.0), 4.0, 35.0)
        raw_price = features.mid_price * (1 - offset_bps / 10_000)
        if features.best_bid is not None:
            raw_price = min(raw_price, features.best_bid)
        return round_price(raw_price, tick_size=self.price_tick_size, side="BUY")

    def _expected_buy_edge_bps(self, features: FeatureSet, regime: Regime) -> float:
        vwap_discount = -(features.vwap_deviation_bps or 0.0)
        edge = max(vwap_discount, 0.0)
        if regime == Regime.UPTREND_PULLBACK:
            edge += 10.0
        elif regime == Regime.RANGE:
            edge += 5.0
        if features.orderbook_imbalance is not None:
            edge += clamp(features.orderbook_imbalance, -1.0, 1.0) * 8.0
        if features.trade_imbalance is not None:
            edge += clamp(features.trade_imbalance, -1.0, 1.0) * 5.0
        if features.funding_zscore is not None:
            if features.funding_zscore > 2.0:
                edge -= min(10.0, features.funding_zscore * 3)
            elif features.funding_zscore < -2.0:
                edge += min(6.0, abs(features.funding_zscore) * 2)
        if features.open_interest_change_pct is not None and features.open_interest_change_pct > 5:
            edge -= 3.0
        return edge

    @staticmethod
    def _position_age_seconds(position: PositionState) -> int | None:
        if position.opened_at is None:
            return None
        opened_at = position.opened_at
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=UTC)
        return int((datetime.now(UTC) - opened_at).total_seconds())
