from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from adaptive_bybit_bot.data.db import create_database_engine
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.enums import Regime, Side, SignalAction
from adaptive_bybit_bot.domain.models import (
    Candle,
    MarketSnapshot,
    OrderBook,
    OrderBookLevel,
    SignalDecision,
    Trade,
)
from adaptive_bybit_bot.services.paper_trading import PaperFillSimulator


def _candle(ts: datetime, close: float = 100.0) -> Candle:
    return Candle(ts=ts, open=close, high=close + 1, low=close - 1, close=close, volume=10)


def test_paper_fill_marks_active_intent_and_updates_position(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path}/bot.db")
    repo = BotRepository(engine)
    repo.create_schema()
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    decision = SignalDecision(
        action=SignalAction.BUY_INTENT,
        symbol="BTCUSDT",
        side=Side.BUY,
        price=99.0,
        qty=0.01,
        regime=Regime.RANGE,
        confidence=0.8,
        expected_edge_bps=40,
        reason=["unit_test"],
        ttl_seconds=120,
        ts=created_at,
    )
    intent_id = repo.apply_signal(decision)
    assert intent_id is not None

    snapshot_ts = created_at + timedelta(seconds=10)
    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        ts=snapshot_ts,
        candles=[_candle(created_at), _candle(snapshot_ts, close=99.2)],
        orderbook=OrderBook(
            symbol="BTCUSDT",
            ts=snapshot_ts,
            bids=[OrderBookLevel(price=98.9, qty=1)],
            asks=[OrderBookLevel(price=99.1, qty=1)],
        ),
        trades=[Trade(ts=created_at + timedelta(seconds=5), price=98.95, qty=0.02, side=Side.SELL)],
    )

    fills = PaperFillSimulator(repo, mode="trade_through").simulate_snapshot(snapshot)

    assert len(fills) == 1
    assert fills[0].intent_id == intent_id
    assert repo.active_intent("BTCUSDT", Side.BUY) is None
    position = repo.get_position_state("BTCUSDT")
    assert position.is_open
    assert position.qty == 0.01
    assert repo.list_paper_fills(limit=5)[0]["order_intent_id"] == intent_id


def test_paper_fill_partial_threshold_only_fills_crossed_quantity(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path}/bot.db")
    repo = BotRepository(engine)
    repo.create_schema()
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    intent_id = repo.apply_signal(
        SignalDecision(
            action=SignalAction.BUY_INTENT,
            symbol="BTCUSDT",
            side=Side.BUY,
            price=99.0,
            qty=1.0,
            regime=Regime.RANGE,
            confidence=0.8,
            expected_edge_bps=40,
            reason=["unit_test"],
            ttl_seconds=120,
            ts=created_at,
        )
    )
    assert intent_id is not None

    snapshot_ts = created_at + timedelta(seconds=10)
    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        ts=snapshot_ts,
        candles=[_candle(created_at), _candle(snapshot_ts, close=99.2)],
        orderbook=OrderBook(
            symbol="BTCUSDT",
            ts=snapshot_ts,
            bids=[OrderBookLevel(price=98.9, qty=1)],
            asks=[OrderBookLevel(price=99.1, qty=1)],
        ),
        trades=[Trade(ts=created_at + timedelta(seconds=5), price=98.95, qty=0.6, side=Side.SELL)],
    )

    fills = PaperFillSimulator(
        repo,
        mode="trade_through",
        min_fill_ratio=0.5,
    ).simulate_snapshot(snapshot)

    assert len(fills) == 1
    assert fills[0].fill_qty == pytest.approx(0.6)
    active = repo.active_intent("BTCUSDT", Side.BUY)
    assert active is not None
    assert active.qty == pytest.approx(0.4)
    position = repo.get_position_state("BTCUSDT")
    assert position.qty == pytest.approx(0.6)
    assert repo.list_paper_fills(limit=5)[0]["fill_qty"] == pytest.approx(0.6)
