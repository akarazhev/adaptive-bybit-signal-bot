from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.domain.models import (
    Candle,
    FearGreedContext,
    InstrumentSpec,
    MarketSnapshot,
    SignalDecision,
)
from adaptive_bybit_bot.exchange.bybit_client import BybitRestClient
from adaptive_bybit_bot.exchange.bybit_ws import BybitPublicWebSocketClient
from adaptive_bybit_bot.features.engine import FeatureEngine
from adaptive_bybit_bot.market_data.ws_cache import WebSocketMarketDataCache
from adaptive_bybit_bot.sentiment.service import get_fear_greed_context_for_strategy
from adaptive_bybit_bot.services.factory import (
    fear_greed_policy_from_settings,
    risk_config_from_settings,
)
from adaptive_bybit_bot.services.market_loop import _load_instrument_or_cached_fallback
from adaptive_bybit_bot.services.paper_trading import PaperFillResult, PaperFillSimulator
from adaptive_bybit_bot.strategy.regime import RegimeAssessment, RegimeClassifier
from adaptive_bybit_bot.strategy.strategy import StrategyEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WsShadowCycleResult:
    symbol: str
    decision: SignalDecision
    regime: RegimeAssessment
    affected_intent_id: str | None
    instrument: InstrumentSpec
    paper_fills: list[PaperFillResult] = field(default_factory=list)
    cache_diagnostics: dict[str, Any] = field(default_factory=dict)
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
            "cache": self.cache_diagnostics,
            "sentiment": self.sentiment.as_dict() if self.sentiment else None,
        }


class CandleCache:
    def __init__(self) -> None:
        self._candles: dict[str, list[Candle]] = {}
        self._refreshed_at: dict[str, datetime] = {}

    async def get(
        self,
        *,
        client: BybitRestClient,
        symbol: str,
        interval: str,
        limit: int,
        refresh_seconds: int,
    ) -> list[Candle]:
        now = datetime.now(UTC)
        last = self._refreshed_at.get(symbol)
        if symbol in self._candles and last is not None:
            if (now - last).total_seconds() < refresh_seconds:
                return self._candles[symbol]
        candles = await client.get_klines(symbol, interval=interval, limit=limit)
        self._candles[symbol] = candles
        self._refreshed_at[symbol] = now
        return candles


async def run_ws_shadow_forever(
    *,
    settings: Settings,
    repository: BotRepository,
    rest_client: BybitRestClient,
    symbols: list[str] | None = None,
    seconds: int = 0,
) -> None:
    """Run a live public-WS shadow loop that writes local order intents."""
    symbols = [symbol.upper() for symbol in (symbols or settings.symbols)]
    cache = WebSocketMarketDataCache(
        symbols=symbols,
        orderbook_depth=settings.ws_orderbook_depth,
        max_trades_per_symbol=settings.ws_max_trades_per_symbol,
    )
    candle_cache = CandleCache()
    topics: list[str] = []
    for symbol in symbols:
        topics.extend(
            [
                f"orderbook.{settings.ws_orderbook_depth}.{symbol}",
                f"publicTrade.{symbol}",
                f"tickers.{symbol}",
            ]
        )
    ws_client = BybitPublicWebSocketClient(url=settings.bybit_public_ws_spot_url)
    last_eval: dict[str, datetime] = {
        symbol: datetime.min.replace(tzinfo=UTC) for symbol in symbols
    }
    started_at = datetime.now(UTC)

    async for payload in ws_client.stream(topics):
        cache.handle_message(payload)
        now = datetime.now(UTC)
        if seconds > 0 and (now - started_at).total_seconds() >= seconds:
            logger.info("ws_shadow_stopped_after_seconds seconds=%s", seconds)
            return
        for symbol in symbols:
            if not cache.is_ready(symbol):
                continue
            if (now - last_eval[symbol]).total_seconds() < settings.ws_evaluation_interval_seconds:
                continue
            last_eval[symbol] = now
            try:
                candles = await candle_cache.get(
                    client=rest_client,
                    symbol=symbol,
                    interval=settings.kline_interval,
                    limit=settings.kline_limit,
                    refresh_seconds=settings.ws_candle_refresh_seconds,
                )
                snapshot = cache.build_snapshot(
                    symbol=symbol,
                    candles=candles,
                    trade_lookback_seconds=settings.ws_trade_lookback_seconds,
                )
                if snapshot is None:
                    continue
                result = await evaluate_ws_snapshot_once(
                    settings=settings,
                    repository=repository,
                    client=rest_client,
                    snapshot=snapshot,
                    cache_diagnostics=cache.diagnostics(),
                )
                logger.info(
                    "ws_cycle_result symbol=%s action=%s regime=%s price=%s qty=%s reason=%s",
                    result.symbol,
                    result.decision.action.value,
                    result.regime.regime.value,
                    result.decision.price,
                    result.decision.qty,
                    ";".join(result.decision.reason),
                )
            except Exception:
                logger.exception("ws_cycle_failed symbol=%s", symbol)


async def evaluate_ws_snapshot_once(
    *,
    settings: Settings,
    repository: BotRepository,
    client: BybitRestClient,
    snapshot: MarketSnapshot,
    cache_diagnostics: dict[str, Any] | None = None,
) -> WsShadowCycleResult:
    repository.expire_stale_intents()
    risk = risk_config_from_settings(settings)
    feature_engine = FeatureEngine()
    regime_classifier = RegimeClassifier(risk)

    instrument = await _load_instrument_or_cached_fallback(
        repository=repository,
        client=client,
        symbol=snapshot.symbol,
    )

    paper_fills: list[PaperFillResult] = []
    if settings.paper_trading_enabled:
        paper_fills = PaperFillSimulator(
            repository,
            mode=settings.paper_fill_mode,
            min_fill_ratio=settings.paper_min_fill_ratio,
            max_trade_age_seconds=settings.paper_max_trade_age_seconds,
        ).simulate_snapshot(snapshot)

    features = feature_engine.build(snapshot)
    regime = regime_classifier.classify(features)
    repository.save_feature_set(features, version="v1-ws")
    repository.save_regime(
        symbol=snapshot.symbol,
        regime=regime.regime.value,
        confidence=regime.confidence,
        explanation={**regime.as_dict(), "source": "public_ws"},
        ts=features.ts,
    )

    sentiment = await get_fear_greed_context_for_strategy(
        settings=settings,
        repository=repository,
        now=features.ts,
    )

    position = repository.get_position_state(snapshot.symbol)
    active_buy = repository.active_intent(snapshot.symbol, Side.BUY)
    active_sell = repository.active_intent(snapshot.symbol, Side.SELL)
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
    affected_intent_id = repository.apply_signal(decision, strategy_version="v1-ws")
    return WsShadowCycleResult(
        symbol=snapshot.symbol,
        decision=decision,
        regime=regime,
        affected_intent_id=affected_intent_id,
        instrument=instrument,
        paper_fills=paper_fills,
        cache_diagnostics=cache_diagnostics or {},
        sentiment=sentiment,
    )


async def collect_ws_cache_for_seconds(
    *,
    settings: Settings,
    symbols: list[str],
    seconds: int,
) -> WebSocketMarketDataCache:
    cache = WebSocketMarketDataCache(
        symbols=[symbol.upper() for symbol in symbols],
        orderbook_depth=settings.ws_orderbook_depth,
        max_trades_per_symbol=settings.ws_max_trades_per_symbol,
    )
    topics = []
    for symbol in cache.symbols:
        topics.extend(
            [
                f"orderbook.{settings.ws_orderbook_depth}.{symbol}",
                f"publicTrade.{symbol}",
                f"tickers.{symbol}",
            ]
        )
    client = BybitPublicWebSocketClient(url=settings.bybit_public_ws_spot_url)

    async def _consume() -> None:
        async for payload in client.stream(topics):
            cache.handle_message(payload)

    try:
        async with asyncio.timeout(seconds):
            await _consume()
    except TimeoutError:
        pass
    return cache
