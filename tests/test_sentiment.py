from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from adaptive_bybit_bot.data.db import create_database_engine
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.enums import Regime, SignalAction
from adaptive_bybit_bot.domain.models import (
    FearGreedContext,
    FearGreedValue,
    FeatureSet,
    PositionState,
)
from adaptive_bybit_bot.sentiment.alternative_me import AlternativeMeFearGreedClient
from adaptive_bybit_bot.sentiment.policy import FearGreedPolicyConfig, FearGreedSentimentPolicy
from adaptive_bybit_bot.strategy.regime import RegimeAssessment
from adaptive_bybit_bot.strategy.risk import RiskConfig
from adaptive_bybit_bot.strategy.strategy import StrategyEngine


def make_features(**overrides: object) -> FeatureSet:
    base: dict[str, Any] = dict(
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
    return FeatureSet(**base)


def test_alternative_me_client_parses_fng_response() -> None:
    payload = {
        "name": "Fear and Greed Index",
        "data": [
            {
                "value": "20",
                "value_classification": "Extreme Fear",
                "timestamp": "1760000000",
                "time_until_update": "12345",
            },
            {
                "value": "23",
                "value_classification": "Extreme Fear",
                "timestamp": "1759913600",
            },
        ],
        "metadata": {"error": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fng/"
        assert request.url.params.get("format") == "json"
        return httpx.Response(200, json=payload)

    async def _run() -> None:
        async_client = httpx.AsyncClient(
            base_url="https://api.alternative.me",
            transport=httpx.MockTransport(handler),
        )
        client = AlternativeMeFearGreedClient(client=async_client)
        values = await client.get_values(limit=2)
        await async_client.aclose()
        assert len(values) == 2
        assert values[0].value == 20
        assert values[0].classification == "Extreme Fear"
        assert values[0].time_until_update_seconds == 12345
        assert values[0].timestamp.tzinfo is not None

    asyncio.run(_run())


def test_repository_persists_fear_greed_context(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path}/bot.db")
    repo = BotRepository(engine)
    repo.create_schema()
    now = datetime(2026, 6, 22, tzinfo=UTC)
    repo.save_fear_greed_values(
        [
            FearGreedValue(value=20, classification="Extreme Fear", timestamp=now),
            FearGreedValue(
                value=23, classification="Extreme Fear", timestamp=now - timedelta(days=1)
            ),
        ]
    )

    context = repo.get_fear_greed_context(limit=2)
    assert context is not None
    assert context.value == 20
    assert context.delta_1d == -3
    assert repo.list_fear_greed_values(limit=1)[0]["attribution"].endswith("Alternative.me")


def test_fear_greed_policy_weights_extreme_greed_for_eth() -> None:
    policy = FearGreedSentimentPolicy(
        FearGreedPolicyConfig(enabled=True, eth_weight=0.5, extreme_greed_size_multiplier=0.4)
    )
    context = FearGreedContext(
        current=FearGreedValue(
            value=82,
            classification="Extreme Greed",
            timestamp=datetime.now(UTC),
        )
    )
    modifiers = policy.modifiers(symbol="ETHUSDT", sentiment=context)
    assert modifiers.active
    assert modifiers.size_multiplier == 0.7
    assert modifiers.extra_edge_bps == 7.5
    assert modifiers.ttl_multiplier == 0.75


def test_strategy_applies_fear_greed_to_buy_intent_size_and_metadata() -> None:
    features = make_features()
    regime = RegimeAssessment(Regime.RANGE, 0.75, ["test_range"])
    position = PositionState(symbol="BTCUSDT")
    risk = RiskConfig(min_expected_edge_bps=30)
    baseline = StrategyEngine(risk).evaluate(features=features, regime=regime, position=position)

    policy = FearGreedSentimentPolicy(FearGreedPolicyConfig(enabled=True))
    sentiment = FearGreedContext(
        current=FearGreedValue(
            value=82,
            classification="Extreme Greed",
            timestamp=datetime.now(UTC),
        )
    )
    adjusted = StrategyEngine(risk, sentiment_policy=policy).evaluate(
        features=features,
        regime=regime,
        position=position,
        sentiment=sentiment,
    )

    assert baseline.action == SignalAction.BUY_INTENT
    assert adjusted.action == SignalAction.BUY_INTENT
    assert adjusted.qty is not None and baseline.qty is not None
    assert adjusted.qty < baseline.qty
    assert adjusted.metadata["sentiment"]["classification"] == "Extreme Greed"
    assert "fng_extreme_greed:82" in adjusted.reason
