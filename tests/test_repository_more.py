from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from adaptive_bybit_bot.data.db import create_database_engine
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.enums import Regime, Side, SignalAction
from adaptive_bybit_bot.domain.models import FeatureSet, SignalDecision


def repository_for(tmp_path: Path) -> BotRepository:
    repository = BotRepository(create_database_engine(f"sqlite:///{tmp_path}/bot.db"))
    repository.create_schema()
    return repository


def decision(
    action: SignalAction,
    *,
    side: Side | None,
    price: float | None,
    qty: float | None,
    replaces_intent_id: str | None = None,
    ttl_seconds: int | None = 60,
) -> SignalDecision:
    return SignalDecision(
        action=action,
        symbol="BTCUSDT",
        side=side,
        price=price,
        qty=qty,
        regime=Regime.RANGE,
        confidence=0.8,
        expected_edge_bps=40.0,
        reason=["test"],
        ttl_seconds=ttl_seconds,
        replaces_intent_id=replaces_intent_id,
        ts=datetime.now(UTC),
    )


def feature_set() -> FeatureSet:
    return FeatureSet(
        symbol="BTCUSDT",
        ts=datetime.now(UTC),
        last_price=100,
        mid_price=100,
        best_bid=99.9,
        best_ask=100.1,
        spread_bps=2,
        ema20=100,
        ema50=100,
        ema200=100,
        ema20_slope_bps=0,
        atr_pct=0.2,
        rsi14=50,
        vwap=100,
        vwap_deviation_bps=0,
        orderbook_imbalance=0,
        microprice=100,
        trade_imbalance=0,
        funding_rate=0.0,
        funding_zscore=0.0,
        open_interest_change_pct=0.0,
    )


def test_repository_reprices_cancels_expires_and_lists_intents(tmp_path: Path) -> None:
    repository = repository_for(tmp_path)
    old_id = repository.apply_signal(
        decision(SignalAction.BUY_INTENT, side=Side.BUY, price=100, qty=0.5)
    )
    assert old_id is not None

    new_id = repository.apply_signal(
        decision(
            SignalAction.REPRICE_INTENT,
            side=Side.BUY,
            price=99,
            qty=0.5,
            replaces_intent_id=old_id,
        )
    )
    assert new_id is not None
    active = repository.active_intent("BTCUSDT", Side.BUY)
    assert active is not None
    assert active.id == new_id

    cancelled_id = repository.apply_signal(
        decision(
            SignalAction.CANCEL_INTENT,
            side=Side.BUY,
            price=None,
            qty=None,
            replaces_intent_id=new_id,
        )
    )
    assert cancelled_id == new_id

    stale_id = repository.apply_signal(
        decision(
            SignalAction.BUY_INTENT,
            side=Side.BUY,
            price=98,
            qty=0.5,
            ttl_seconds=-1,
        )
    )
    assert stale_id is not None
    assert repository.expire_stale_intents(datetime.now(UTC)) == 1
    assert len(repository.list_recent_intents(limit=10)) >= 3
    assert repository.active_intents("BTCUSDT") == []


def test_repository_features_regimes_executions_and_positions(tmp_path: Path) -> None:
    repository = repository_for(tmp_path)

    assert repository.save_feature_set(feature_set())
    assert repository.save_regime(
        symbol="BTCUSDT",
        regime=Regime.RANGE.value,
        confidence=0.75,
        explanation={"reason": ["flat"]},
    )
    assert repository.save_account_snapshot(kind="wallet", payload={"balance": 100})
    assert (
        repository.save_executions(
            {
                "list": [
                    {
                        "execId": "exec-1",
                        "execTime": "1700000000000",
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "execPrice": "100",
                        "execQty": "0.2",
                        "execFee": "0.01",
                        "feeCurrency": "USDT",
                    },
                    {"execId": ""},
                    "bad-row",
                ]
            }
        )
        == 1
    )
    assert repository.save_executions({"list": [{"execId": "exec-1"}]}) == 0

    buy_id = repository.apply_signal(
        decision(SignalAction.BUY_INTENT, side=Side.BUY, price=100, qty=0.5)
    )
    assert buy_id is not None
    repository.mark_intent_filled(buy_id, fill_price=100, fill_qty=0.5)

    sell_id = repository.apply_signal(
        decision(SignalAction.SELL_INTENT, side=Side.SELL, price=101, qty=0.5)
    )
    assert sell_id is not None
    repository.mark_intent_filled(
        sell_id,
        fill_price=101,
        fill_qty=0.5,
        filled_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    assert not repository.get_position_state("BTCUSDT").is_open
