from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.domain.models import SignalDecision
from adaptive_bybit_bot.exchange.bybit_client import BybitRestClient
from adaptive_bybit_bot.features.engine import FeatureEngine
from adaptive_bybit_bot.services.factory import risk_config_from_settings
from adaptive_bybit_bot.strategy.regime import RegimeAssessment, RegimeClassifier
from adaptive_bybit_bot.strategy.strategy import StrategyEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CycleResult:
    symbol: str
    decision: SignalDecision
    regime: RegimeAssessment
    affected_intent_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.decision.action.value,
            "side": self.decision.side.value if self.decision.side else None,
            "price": self.decision.price,
            "qty": self.decision.qty,
            "regime": self.regime.regime.value,
            "confidence": self.decision.confidence,
            "expected_edge_bps": self.decision.expected_edge_bps,
            "reason": self.decision.reason,
            "affected_intent_id": self.affected_intent_id,
        }


async def run_symbol_once(
    *,
    settings: Settings,
    repository: BotRepository,
    client: BybitRestClient,
    symbol: str,
) -> CycleResult:
    repository.expire_stale_intents()
    risk = risk_config_from_settings(settings)
    features_engine = FeatureEngine()
    regime_classifier = RegimeClassifier(risk)
    strategy = StrategyEngine(risk)

    snapshot = await client.get_market_snapshot(
        symbol,
        kline_interval=settings.kline_interval,
        kline_limit=settings.kline_limit,
        orderbook_limit=settings.orderbook_limit,
        recent_trades_limit=settings.recent_trades_limit,
    )
    features = features_engine.build(snapshot)
    regime = regime_classifier.classify(features)

    repository.save_feature_set(features)
    repository.save_regime(
        symbol=symbol,
        regime=regime.regime.value,
        confidence=regime.confidence,
        explanation=regime.as_dict(),
        ts=features.ts,
    )

    position = repository.get_position_state(symbol)
    active_buy = repository.active_intent(symbol, Side.BUY)
    active_sell = repository.active_intent(symbol, Side.SELL)
    decision = strategy.evaluate(
        features=features,
        regime=regime,
        position=position,
        active_buy=active_buy,
        active_sell=active_sell,
    )
    affected_intent_id = repository.apply_signal(decision)
    logger.info(
        "cycle_result symbol=%s action=%s regime=%s price=%s qty=%s "
        "affected_intent_id=%s reason=%s",
        symbol,
        decision.action.value,
        regime.regime.value,
        decision.price,
        decision.qty,
        affected_intent_id,
        ";".join(decision.reason),
    )
    return CycleResult(
        symbol=symbol, decision=decision, regime=regime, affected_intent_id=affected_intent_id
    )


async def run_forever(
    *,
    settings: Settings,
    repository: BotRepository,
    client: BybitRestClient,
    symbols: list[str] | None = None,
) -> None:
    symbols = symbols or settings.symbols
    while True:
        for symbol in symbols:
            try:
                await run_symbol_once(
                    settings=settings,
                    repository=repository,
                    client=client,
                    symbol=symbol,
                )
            except Exception:
                logger.exception("cycle_failed symbol=%s", symbol)
        await asyncio.sleep(settings.poll_interval_seconds)
