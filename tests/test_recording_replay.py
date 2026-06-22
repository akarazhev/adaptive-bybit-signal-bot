from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from adaptive_bybit_bot.backtesting.engine import BacktestFill
from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.db import create_database_engine
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.enums import Regime, Side, SignalAction
from adaptive_bybit_bot.domain.models import InstrumentSpec, SignalDecision, Trade
from adaptive_bybit_bot.recording import recorder as recorder_module
from adaptive_bybit_bot.recording import replay as replay_module
from adaptive_bybit_bot.recording.events import RecordedMarketEvent
from adaptive_bybit_bot.recording.jsonl import JsonlMarketEventWriter, read_market_events
from adaptive_bybit_bot.recording.recorder import recording_file_path, recording_topics
from adaptive_bybit_bot.recording.replay import (
    MarketReplayConfig,
    MarketReplayResult,
    MarketReplayRunner,
)
from adaptive_bybit_bot.strategy.risk import RiskConfig


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _orderbook_payload(ts: datetime) -> dict:
    return {
        "topic": "orderbook.50.BTCUSDT",
        "type": "snapshot",
        "ts": _ms(ts),
        "data": {
            "s": "BTCUSDT",
            "b": [["100.0", "1.0"]],
            "a": [["100.1", "1.0"]],
            "u": 1,
            "seq": 1,
        },
    }


def _trade_payload(ts: datetime, price: float = 100.0) -> dict:
    return {
        "topic": "publicTrade.BTCUSDT",
        "type": "snapshot",
        "ts": _ms(ts),
        "data": [
            {
                "T": _ms(ts),
                "s": "BTCUSDT",
                "S": "Sell",
                "v": "0.01",
                "p": f"{price:.2f}",
                "i": f"trade-{_ms(ts)}",
                "seq": _ms(ts),
            }
        ],
    }


def _decision(
    *,
    action: SignalAction,
    side: Side | None,
    price: float | None = 100.0,
    qty: float | None = 1.0,
) -> SignalDecision:
    return SignalDecision(
        action=action,
        symbol="BTCUSDT",
        side=side,
        price=price,
        qty=qty,
        regime=Regime.RANGE,
        confidence=0.8,
        expected_edge_bps=25.0,
        reason=["unit_test"],
        ttl_seconds=30,
    )


def test_recorded_market_event_jsonl_roundtrip(tmp_path) -> None:
    path = tmp_path / "session.jsonl.gz"
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    event = RecordedMarketEvent.from_ws_payload(_trade_payload(ts), recorded_at=ts, sequence=1)

    with JsonlMarketEventWriter(path) as writer:
        writer.write(event)

    rows = list(read_market_events(path))
    assert len(rows) == 1
    assert rows[0].symbol == "BTCUSDT"
    assert rows[0].event_kind == "trade"
    assert rows[0].payload["topic"] == "publicTrade.BTCUSDT"


def test_recorded_market_event_normalizes_payload_variants() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    assert RecordedMarketEvent.from_ws_payload(_orderbook_payload(ts)).event_kind == "orderbook"
    assert (
        RecordedMarketEvent.from_ws_payload({"topic": "tickers.ETHUSDT", "ts": _ms(ts)}).symbol
        == "ETHUSDT"
    )
    assert RecordedMarketEvent.from_ws_payload({"op": "subscribe"}).event_kind == "control"
    assert (
        RecordedMarketEvent.from_ws_payload(
            {"data": [{"symbol": "SOLUSDT", "T": _ms(ts)}]},
        ).symbol
        == "SOLUSDT"
    )

    parsed = RecordedMarketEvent.from_json(
        {
            "recorded_at": "not-a-date",
            "exchange_ts": "not-a-date",
            "event_kind": "",
            "topic": "",
            "symbol": "",
            "sequence": "not-an-int",
            "metadata": "bad",
            "payload": "bad",
        }
    )
    assert parsed.event_kind == "other"
    assert parsed.exchange_ts is None
    assert parsed.sequence is None
    assert parsed.metadata == {}
    assert parsed.payload == {}


def test_recording_helpers_build_topics_and_paths(tmp_path) -> None:
    started_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    assert recording_topics([" btcusdt ", "", "ethusdt"], depth=1) == [
        "tickers.BTCUSDT",
        "publicTrade.BTCUSDT",
        "orderbook.1.BTCUSDT",
        "tickers.ETHUSDT",
        "publicTrade.ETHUSDT",
        "orderbook.1.ETHUSDT",
    ]
    assert (
        recording_file_path(
            output_dir=tmp_path,
            symbols=["btcusdt", "ethusdt"],
            depth=50,
            compress=False,
            started_at=started_at,
        ).name
        == "20260101T120000Z-BTCUSDT-ETHUSDT-depth50.jsonl"
    )


def test_record_market_forever_persists_finite_stream(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWsClient:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        async def stream(self, topics: list[str]):
            assert "publicTrade.BTCUSDT" in topics
            ts = datetime(2026, 1, 1, tzinfo=UTC)
            yield _orderbook_payload(ts)
            yield _trade_payload(ts + timedelta(seconds=1), price=100.2)

    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/bot.db",
        market_recording_dir=str(tmp_path),
        market_recording_compress=False,
        market_recording_flush_every_events=1,
        service_heartbeat_seconds=0,
    )
    repository = BotRepository(create_database_engine(settings.database_url))
    repository.create_schema()
    monkeypatch.setattr(recorder_module, "BybitPublicWebSocketClient", FakeWsClient)

    result = asyncio.run(
        recorder_module.record_market_forever(
            settings=settings,
            repository=repository,
            symbols=["btcusdt"],
            depth=50,
            output_dir=tmp_path,
            service_name="unit-recorder",
        )
    )

    assert result["status"] == "finished"
    assert result["event_count"] == 2
    assert len(list(read_market_events(result["file_path"]))) == 2
    assert repository.list_service_heartbeats(limit=1)[0]["status"] == "finished"


def test_repository_persists_market_recording_and_replay(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path}/bot.db")
    repo = BotRepository(engine)
    repo.create_schema()
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    session_id = repo.start_market_recording_session(
        symbols=["BTCUSDT"],
        topics=["publicTrade.BTCUSDT"],
        depth=50,
        output_dir=str(tmp_path),
        file_path=str(tmp_path / "session.jsonl.gz"),
        config={"unit": True},
        started_at=started_at,
    )
    repo.finish_market_recording_session(
        session_id,
        status="finished",
        event_count=3,
        bytes_written=123,
        ended_at=started_at + timedelta(seconds=5),
    )
    recording = repo.get_market_recording_session(session_id)
    assert recording is not None
    assert recording["event_count"] == 3

    result = MarketReplayResult(
        symbol="BTCUSDT",
        input_path=str(tmp_path / "session.jsonl.gz"),
        recording_session_id=session_id,
        started_at=started_at,
        finished_at=started_at + timedelta(minutes=1),
        event_count=3,
        candle_count=1,
        decisions=[],
        fills=[
            BacktestFill(
                ts=started_at + timedelta(seconds=30),
                intent_id="intent-1",
                symbol="BTCUSDT",
                side=Side.BUY.value,
                price=100.0,
                qty=0.1,
                fee_quote=0.01,
                cash_after=989.99,
                base_after=0.1,
                reason="unit_test",
            )
        ],
        initial_quote=1000.0,
        final_quote_equity=1000.0,
        realized_quote=0.0,
        unrealized_quote=0.0,
        return_pct=0.0,
        max_drawdown_pct=0.0,
        win_rate=0.0,
        closed_round_trips=0,
        open_base_qty=0.1,
        open_avg_entry=100.0,
        config=MarketReplayConfig(),
    )
    run_id = repo.save_market_replay_result(result)
    assert repo.list_market_replays(limit=1)[0]["id"] == run_id
    assert repo.list_market_replay_fills(run_id=run_id, limit=10)[0]["symbol"] == "BTCUSDT"


def test_replay_helpers_parse_trade_payloads_and_apply_decisions() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    assert replay_module._trades_from_payload({"topic": "tickers.BTCUSDT"}, symbol="BTCUSDT") == []
    trades = replay_module._trades_from_payload(
        {
            "topic": "publicTrade.BTCUSDT",
            "ts": _ms(ts),
            "data": [
                {"s": "BTCUSDT", "S": "Buy", "p": "101.0", "v": "0.2"},
                {"s": "ETHUSDT", "S": "Sell", "p": "1", "v": "1"},
            ],
        },
        symbol="BTCUSDT",
    )
    assert len(trades) == 1
    assert trades[0].side == Side.BUY

    builder = replay_module._TradeCandleBuilder(interval_seconds=60)
    builder.update_trade(Trade(ts=ts, price=0.0, qty=1.0))
    builder.update_trade(Trade(ts=ts, price=100.0, qty=0.1, side=Side.BUY))
    builder.update_trade(Trade(ts=ts + timedelta(seconds=30), price=101.0, qty=0.2))
    builder.update_trade(Trade(ts=ts + timedelta(seconds=60), price=99.0, qty=0.3))
    candles = builder.candles()
    assert len(candles) == 2
    assert candles[0].high == 101.0
    assert candles[0].volume == pytest.approx(0.3)

    buy_intent, sell_intent = replay_module._apply_decision(
        _decision(action=SignalAction.BUY_INTENT, side=Side.BUY),
        ts,
        None,
        None,
    )
    assert buy_intent is not None
    assert sell_intent is None
    buy_intent, sell_intent = replay_module._apply_decision(
        _decision(action=SignalAction.SELL_INTENT, side=Side.SELL, price=101.0),
        ts,
        buy_intent,
        sell_intent,
    )
    assert buy_intent is not None
    assert sell_intent is not None
    assert replay_module._expire_if_needed(buy_intent, ts + timedelta(seconds=31)) is None
    buy_intent, sell_intent = replay_module._apply_decision(
        _decision(action=SignalAction.CANCEL_INTENT, side=Side.SELL),
        ts,
        buy_intent,
        sell_intent,
    )
    assert buy_intent is not None
    assert sell_intent is None

    with pytest.raises(ValueError, match="complete limit intent"):
        replay_module._apply_decision(
            _decision(action=SignalAction.BUY_INTENT, side=None, price=None, qty=None),
            ts,
            None,
            None,
        )


def test_replay_fill_model_buys_and_sells_against_recorded_trades() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    runner = MarketReplayRunner(
        risk=RiskConfig(),
        instrument=InstrumentSpec(symbol="BTCUSDT", price_tick_size=0.01, qty_step=0.000001),
        config=MarketReplayConfig(initial_quote=1000.0, maker_fee_bps=10.0, fill_model="touch"),
    )
    buy_intent = replay_module.ReplayIntent(
        id="buy",
        symbol="BTCUSDT",
        side=Side.BUY.value,
        limit_price=100.0,
        qty=1.0,
        created_at=ts,
    )
    trade = Trade(ts=ts + timedelta(seconds=1), price=100.0, qty=1.0, side=Side.SELL)

    active_buy, active_sell, cash, base_qty, avg_entry, pending_cost, fills = (
        runner._simulate_trade_fills(
            trade=trade,
            active_buy=buy_intent,
            active_sell=None,
            cash=1000.0,
            base_qty=0.0,
            avg_entry=0.0,
            pending_entry_cost=0.0,
        )
    )

    assert active_buy is None
    assert cash == pytest.approx(899.9)
    assert base_qty == pytest.approx(1.0)
    assert avg_entry == pytest.approx(100.0)
    assert pending_cost == pytest.approx(100.1)
    assert fills[0].side == Side.BUY.value

    sell_intent = replay_module.ReplayIntent(
        id="sell",
        symbol="BTCUSDT",
        side=Side.SELL.value,
        limit_price=101.0,
        qty=1.0,
        created_at=ts,
    )
    sell_trade = Trade(ts=ts + timedelta(seconds=2), price=101.0, qty=1.0, side=Side.BUY)
    _, active_sell, cash, base_qty, avg_entry, pending_cost, fills = runner._simulate_trade_fills(
        trade=sell_trade,
        active_buy=None,
        active_sell=sell_intent,
        cash=cash,
        base_qty=base_qty,
        avg_entry=avg_entry,
        pending_entry_cost=pending_cost,
    )

    assert active_sell is None
    assert base_qty == 0.0
    assert avg_entry == 0.0
    assert pending_cost == 0.0
    assert cash > 1000.0
    assert fills[0].side == Side.SELL.value
    assert fills[0].pnl_quote is not None

    expensive_buy = replay_module.ReplayIntent(
        id="too-expensive",
        symbol="BTCUSDT",
        side=Side.BUY.value,
        limit_price=100.0,
        qty=10.0,
        created_at=ts,
    )
    active_buy, *_rest, fills = runner._simulate_trade_fills(
        trade=trade,
        active_buy=expensive_buy,
        active_sell=None,
        cash=1.0,
        base_qty=0.0,
        avg_entry=0.0,
        pending_entry_cost=0.0,
    )
    assert active_buy is expensive_buy
    assert fills == []

    with pytest.raises(ValueError, match="fill_model"):
        MarketReplayRunner(
            risk=RiskConfig(),
            instrument=InstrumentSpec(symbol="BTCUSDT"),
            config=MarketReplayConfig(fill_model="bad"),
        )


def test_market_replay_runner_processes_synthetic_ws_recording(tmp_path) -> None:
    path = tmp_path / "synthetic.jsonl.gz"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with JsonlMarketEventWriter(path) as writer:
        writer.write(
            RecordedMarketEvent.from_ws_payload(
                _orderbook_payload(start), recorded_at=start, sequence=1
            )
        )
        for index in range(70):
            ts = start + timedelta(minutes=index)
            writer.write(
                RecordedMarketEvent.from_ws_payload(
                    _trade_payload(ts, price=100.0 + index * 0.01),
                    recorded_at=ts,
                    sequence=index + 2,
                )
            )

    runner = MarketReplayRunner(
        risk=RiskConfig(max_spread_bps=20.0),
        instrument=InstrumentSpec(symbol="BTCUSDT", price_tick_size=0.01, qty_step=0.000001),
        config=MarketReplayConfig(
            initial_quote=1000.0,
            warmup_candles=60,
            evaluation_interval_seconds=60,
            candle_interval_seconds=60,
            force_close=True,
        ),
    )
    result = runner.run_file(path, symbol="BTCUSDT")
    assert result.event_count >= 70
    assert result.candle_count >= 60
    assert result.decision_count > 0
    assert result.final_quote_equity > 0
