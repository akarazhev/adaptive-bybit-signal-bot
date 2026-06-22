from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.domain.models import FearGreedContext, InstrumentSpec, SignalDecision
from adaptive_bybit_bot.exchange.bybit_client import BybitApiError, BybitRestClient
from adaptive_bybit_bot.features.engine import FeatureEngine
from adaptive_bybit_bot.sentiment.service import get_fear_greed_context_for_strategy
from adaptive_bybit_bot.services.factory import (
    fear_greed_policy_from_settings,
    risk_config_from_settings,
)
from adaptive_bybit_bot.services.paper_trading import PaperFillResult, PaperFillSimulator
from adaptive_bybit_bot.strategy.regime import RegimeAssessment, RegimeClassifier
from adaptive_bybit_bot.strategy.strategy import StrategyEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CycleResult:
    symbol: str
    decision: SignalDecision
    regime: RegimeAssessment
    affected_intent_id: str | None
    instrument: InstrumentSpec = field(default_factory=lambda: InstrumentSpec.fallback(""))
    paper_fills: list[PaperFillResult] = field(default_factory=list)
    sentiment: FearGreedContext | None = None

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
            "instrument": self.instrument.as_dict(),
            "paper_fills": [fill.as_dict() for fill in self.paper_fills],
            "sentiment": self.sentiment.as_dict() if self.sentiment else None,
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

    snapshot = await client.get_market_snapshot(
        symbol,
        kline_interval=settings.kline_interval,
        kline_limit=settings.kline_limit,
        orderbook_limit=settings.orderbook_limit,
        recent_trades_limit=settings.recent_trades_limit,
    )

    instrument = await _load_instrument_or_cached_fallback(
        repository=repository,
        client=client,
        symbol=symbol,
    )

    paper_fills: list[PaperFillResult] = []
    if settings.paper_trading_enabled:
        paper_fills = PaperFillSimulator(
            repository,
            mode=settings.paper_fill_mode,
            min_fill_ratio=settings.paper_min_fill_ratio,
            max_trade_age_seconds=settings.paper_max_trade_age_seconds,
        ).simulate_snapshot(snapshot)

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

    sentiment = await get_fear_greed_context_for_strategy(
        settings=settings,
        repository=repository,
        now=features.ts,
    )

    position = repository.get_position_state(symbol)
    active_buy = repository.active_intent(symbol, Side.BUY)
    active_sell = repository.active_intent(symbol, Side.SELL)
    decision = StrategyEngine(
        risk,
        instrument=instrument,
        sentiment_policy=fear_greed_policy_from_settings(settings),
    ).evaluate(
        features=features,
        regime=regime,
        position=position,
        active_buy=active_buy,
        active_sell=active_sell,
        sentiment=sentiment,
    )
    affected_intent_id = repository.apply_signal(decision)
    logger.info(
        "cycle_result symbol=%s action=%s regime=%s price=%s qty=%s "
        "affected_intent_id=%s paper_fills=%d reason=%s",
        symbol,
        decision.action.value,
        regime.regime.value,
        decision.price,
        decision.qty,
        affected_intent_id,
        len(paper_fills),
        ";".join(decision.reason),
    )
    return CycleResult(
        symbol=symbol,
        decision=decision,
        regime=regime,
        affected_intent_id=affected_intent_id,
        instrument=instrument,
        paper_fills=paper_fills,
        sentiment=sentiment,
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


async def _load_instrument_or_cached_fallback(
    *,
    repository: BotRepository,
    client: BybitRestClient,
    symbol: str,
) -> InstrumentSpec:
    try:
        spec = await client.get_instrument_info(symbol, category="spot")
        repository.save_instrument_spec(spec)
        return spec
    except (BybitApiError, httpx.HTTPError) as exc:
        logger.warning("instrument_info_failed symbol=%s error=%s", symbol, exc)
        return repository.get_latest_instrument_spec(symbol) or InstrumentSpec.fallback(symbol)


async def refresh_instruments_once(
    *,
    repository: BotRepository,
    client: BybitRestClient,
    symbols: list[str],
) -> list[InstrumentSpec]:
    specs: list[InstrumentSpec] = []
    for symbol in symbols:
        spec = await client.get_instrument_info(symbol, category="spot", use_cache=False)
        repository.save_instrument_spec(spec)
        specs.append(spec)
    return specs


async def run_paper_fill_once(
    *,
    settings: Settings,
    repository: BotRepository,
    client: BybitRestClient,
    symbol: str,
) -> list[PaperFillResult]:
    snapshot = await client.get_market_snapshot(
        symbol,
        kline_interval=settings.kline_interval,
        kline_limit=settings.kline_limit,
        orderbook_limit=settings.orderbook_limit,
        recent_trades_limit=settings.recent_trades_limit,
    )
    return PaperFillSimulator(
        repository,
        mode=settings.paper_fill_mode,
        min_fill_ratio=settings.paper_min_fill_ratio,
        max_trade_age_seconds=settings.paper_max_trade_age_seconds,
    ).simulate_snapshot(snapshot)
