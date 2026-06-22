from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from adaptive_bybit_bot.data.db import create_database_engine
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.enums import Regime, Side, SignalAction
from adaptive_bybit_bot.domain.models import SignalDecision


def test_repository_order_intent_lifecycle(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path}/bot.db")
    repo = BotRepository(engine)
    repo.create_schema()
    decision = SignalDecision(
        action=SignalAction.BUY_INTENT,
        symbol="BTCUSDT",
        side=Side.BUY,
        price=100.0,
        qty=0.5,
        regime=Regime.RANGE,
        confidence=0.8,
        expected_edge_bps=40.0,
        reason=["unit_test"],
        ttl_seconds=60,
        ts=datetime.now(UTC),
    )
    intent_id = repo.apply_signal(decision)
    assert intent_id is not None
    assert repo.active_intent("BTCUSDT", Side.BUY) is not None

    repo.mark_intent_filled(intent_id, fill_price=100.0, fill_qty=0.5)
    assert repo.active_intent("BTCUSDT", Side.BUY) is None
    position = repo.get_position_state("BTCUSDT")
    assert position.is_open
    assert position.qty == 0.5
