from __future__ import annotations

from datetime import UTC, datetime, timedelta

from adaptive_bybit_bot.backtesting import BacktestConfig, CandleBacktestRunner
from adaptive_bybit_bot.backtesting.csv_io import read_candles_csv, write_candles_csv
from adaptive_bybit_bot.domain.models import Candle, InstrumentSpec
from adaptive_bybit_bot.strategy.risk import RiskConfig


def make_candles(count: int = 300) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles: list[Candle] = []
    for i in range(count):
        # Slow oscillation around 100 creates range/pullback opportunities.
        price = 100.0 + ((i % 20) - 10) * 0.08
        candles.append(
            Candle(
                ts=start + timedelta(minutes=i),
                open=price,
                high=price + 0.35,
                low=price - 0.35,
                close=price,
                volume=10.0 + i % 5,
            )
        )
    return candles


def test_candle_backtest_runner_produces_metrics() -> None:
    risk = RiskConfig(
        order_quote_usdt=10.0,
        spot_maker_fee_bps=0.0,
        min_net_profit_bps=0.0,
        safety_buffer_bps=0.0,
        min_expected_edge_bps=1.0,
        max_spread_bps=50.0,
        max_atr_pct=5.0,
        shock_atr_pct=5.0,
    )
    result = CandleBacktestRunner(
        risk=risk,
        instrument=InstrumentSpec.fallback("BTCUSDT"),
        config=BacktestConfig(
            initial_quote=1000.0,
            lookback_candles=60,
            synthetic_spread_bps=2.0,
            maker_fee_bps=0.0,
        ),
    ).run(symbol="BTCUSDT", candles=make_candles())

    assert result.candles == 300
    assert isinstance(result.final_quote_equity, float)
    assert result.decision_count if hasattr(result, "decision_count") else len(result.decisions) > 0
    assert result.as_dict()["decision_count"] > 0


def test_candle_csv_round_trip(tmp_path) -> None:
    path = tmp_path / "candles.csv"
    candles = make_candles(5)
    write_candles_csv(path, candles)
    loaded = read_candles_csv(path)
    assert len(loaded) == 5
    assert loaded[0].close == candles[0].close


def test_repository_can_persist_backtest_result(tmp_path) -> None:
    from adaptive_bybit_bot.data.db import create_database_engine
    from adaptive_bybit_bot.data.repositories import BotRepository

    risk = RiskConfig(
        order_quote_usdt=10.0,
        spot_maker_fee_bps=0.0,
        min_net_profit_bps=0.0,
        safety_buffer_bps=0.0,
        min_expected_edge_bps=1.0,
        max_spread_bps=50.0,
        max_atr_pct=5.0,
        shock_atr_pct=5.0,
    )
    result = CandleBacktestRunner(
        risk=risk,
        instrument=InstrumentSpec.fallback("BTCUSDT"),
        config=BacktestConfig(
            initial_quote=1000.0,
            lookback_candles=60,
            synthetic_spread_bps=2.0,
            maker_fee_bps=0.0,
            interval="1",
        ),
    ).run(symbol="BTCUSDT", candles=make_candles())

    engine = create_database_engine(f"sqlite:///{tmp_path}/bot.db")
    repo = BotRepository(engine)
    repo.create_schema()
    run_id = repo.save_backtest_result(result)
    assert run_id
    rows = repo.list_backtests(limit=1)
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["summary"]["decision_count"] > 0
