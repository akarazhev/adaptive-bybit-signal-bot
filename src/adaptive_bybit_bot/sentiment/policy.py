from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from adaptive_bybit_bot.domain.models import FearGreedContext, FearGreedValue


@dataclass(frozen=True)
class FearGreedPolicyConfig:
    enabled: bool = False
    stale_after_hours: float = 36.0
    btc_weight: float = 1.0
    eth_weight: float = 0.6
    alt_weight: float = 0.5
    extreme_fear_size_multiplier: float = 0.5
    fear_size_multiplier: float = 0.8
    greed_size_multiplier: float = 0.6
    extreme_greed_size_multiplier: float = 0.4
    extreme_fear_extra_edge_bps: float = 5.0
    greed_extra_edge_bps: float = 8.0
    extreme_greed_extra_edge_bps: float = 15.0
    extreme_fear_buy_distance_multiplier: float = 1.25
    fear_buy_distance_multiplier: float = 1.10
    greed_buy_distance_multiplier: float = 1.25
    extreme_greed_buy_distance_multiplier: float = 1.50
    greed_ttl_multiplier: float = 0.75
    extreme_greed_ttl_multiplier: float = 0.50
    extreme_greed_sell_target_multiplier: float = 0.85
    greed_sell_target_multiplier: float = 0.92
    confidence_floor_multiplier: float = 0.65


@dataclass(frozen=True)
class SentimentModifiers:
    active: bool = False
    source: str | None = None
    value: int | None = None
    classification: str | None = None
    age_hours: float | None = None
    stale: bool = False
    symbol_weight: float = 0.0
    size_multiplier: float = 1.0
    extra_edge_bps: float = 0.0
    buy_distance_multiplier: float = 1.0
    ttl_multiplier: float = 1.0
    sell_target_multiplier: float = 1.0
    confidence_multiplier: float = 1.0
    reason: list[str] = field(default_factory=list)
    attribution: str | None = None
    delta_1d: int | None = None
    delta_7d: int | None = None

    def adjusted_ttl(self, ttl_seconds: int) -> int:
        return max(15, int(ttl_seconds * self.ttl_multiplier))

    def as_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "source": self.source,
            "value": self.value,
            "classification": self.classification,
            "age_hours": self.age_hours,
            "stale": self.stale,
            "symbol_weight": self.symbol_weight,
            "size_multiplier": self.size_multiplier,
            "extra_edge_bps": self.extra_edge_bps,
            "buy_distance_multiplier": self.buy_distance_multiplier,
            "ttl_multiplier": self.ttl_multiplier,
            "sell_target_multiplier": self.sell_target_multiplier,
            "confidence_multiplier": self.confidence_multiplier,
            "reason": self.reason,
            "attribution": self.attribution,
            "delta_1d": self.delta_1d,
            "delta_7d": self.delta_7d,
        }


class FearGreedSentimentPolicy:
    """Convert Fear & Greed context into strategy parameter modifiers.

    This class intentionally does not generate buy/sell signals. It only changes
    aggressiveness: required edge, order size, order distance, TTL and sell markup.
    """

    def __init__(self, config: FearGreedPolicyConfig | None = None) -> None:
        self.config = config or FearGreedPolicyConfig()

    def modifiers(
        self,
        *,
        symbol: str,
        sentiment: FearGreedContext | FearGreedValue | None,
        now: datetime | None = None,
    ) -> SentimentModifiers:
        if not self.config.enabled:
            return SentimentModifiers(reason=["fng_disabled"])
        context = _as_context(sentiment)
        if context is None:
            return SentimentModifiers(reason=["fng_unavailable"])

        current = context.current
        age_hours = context.age_hours(now)
        stale = age_hours > self.config.stale_after_hours
        weight = self._symbol_weight(symbol)
        if stale:
            return SentimentModifiers(
                active=False,
                source=current.source,
                value=current.value,
                classification=current.classification,
                age_hours=age_hours,
                stale=True,
                symbol_weight=weight,
                reason=[f"fng_stale:{age_hours:.1f}h"],
                attribution=current.attribution,
                delta_1d=context.delta_1d,
                delta_7d=context.delta_7d,
            )

        state = _state(current)
        size_multiplier = 1.0
        extra_edge_bps = 0.0
        buy_distance_multiplier = 1.0
        ttl_multiplier = 1.0
        sell_target_multiplier = 1.0
        confidence_multiplier = 1.0
        reason = [f"fng_{state}:{current.value}"]

        if state == "extreme_fear":
            size_multiplier = self.config.extreme_fear_size_multiplier
            extra_edge_bps = self.config.extreme_fear_extra_edge_bps
            buy_distance_multiplier = self.config.extreme_fear_buy_distance_multiplier
            confidence_multiplier = 0.90
            reason.append("fng_deeper_smaller_buy")
        elif state == "fear":
            size_multiplier = self.config.fear_size_multiplier
            buy_distance_multiplier = self.config.fear_buy_distance_multiplier
            confidence_multiplier = 0.97
        elif state == "greed":
            size_multiplier = self.config.greed_size_multiplier
            extra_edge_bps = self.config.greed_extra_edge_bps
            buy_distance_multiplier = self.config.greed_buy_distance_multiplier
            ttl_multiplier = self.config.greed_ttl_multiplier
            sell_target_multiplier = self.config.greed_sell_target_multiplier
            confidence_multiplier = 0.86
            reason.append("fng_greed_caution")
        elif state == "extreme_greed":
            size_multiplier = self.config.extreme_greed_size_multiplier
            extra_edge_bps = self.config.extreme_greed_extra_edge_bps
            buy_distance_multiplier = self.config.extreme_greed_buy_distance_multiplier
            ttl_multiplier = self.config.extreme_greed_ttl_multiplier
            sell_target_multiplier = self.config.extreme_greed_sell_target_multiplier
            confidence_multiplier = self.config.confidence_floor_multiplier
            reason.append("fng_extreme_greed_high_caution")

        return SentimentModifiers(
            active=True,
            source=current.source,
            value=current.value,
            classification=current.classification,
            age_hours=age_hours,
            stale=False,
            symbol_weight=weight,
            size_multiplier=_weighted_multiplier(size_multiplier, weight),
            extra_edge_bps=extra_edge_bps * weight,
            buy_distance_multiplier=_weighted_multiplier(buy_distance_multiplier, weight),
            ttl_multiplier=_weighted_multiplier(ttl_multiplier, weight),
            sell_target_multiplier=_weighted_multiplier(sell_target_multiplier, weight),
            confidence_multiplier=_weighted_multiplier(confidence_multiplier, weight),
            reason=reason,
            attribution=current.attribution,
            delta_1d=context.delta_1d,
            delta_7d=context.delta_7d,
        )

    def _symbol_weight(self, symbol: str) -> float:
        normalized = symbol.upper()
        if normalized.startswith("BTC"):
            return _clamp(self.config.btc_weight, 0.0, 1.0)
        if normalized.startswith("ETH"):
            return _clamp(self.config.eth_weight, 0.0, 1.0)
        return _clamp(self.config.alt_weight, 0.0, 1.0)


def _weighted_multiplier(multiplier: float, weight: float) -> float:
    return 1.0 + _clamp(weight, 0.0, 1.0) * (multiplier - 1.0)


def _as_context(value: FearGreedContext | FearGreedValue | None) -> FearGreedContext | None:
    if value is None:
        return None
    if isinstance(value, FearGreedContext):
        return value
    return FearGreedContext(current=value)


def _state(value: FearGreedValue) -> str:
    label = value.normalized_classification
    if label in {"extreme_fear", "fear", "neutral", "greed", "extreme_greed"}:
        return label
    if value.value <= 24:
        return "extreme_fear"
    if value.value <= 44:
        return "fear"
    if value.value <= 54:
        return "neutral"
    if value.value <= 74:
        return "greed"
    return "extreme_greed"


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)
