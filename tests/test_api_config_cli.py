from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import typer
from fastapi.testclient import TestClient

from adaptive_bybit_bot import cli as cli_module
from adaptive_bybit_bot.api.app import create_app
from adaptive_bybit_bot.backtesting.engine import BacktestFill
from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.db import create_database_engine
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.enums import Regime, Side, SignalAction
from adaptive_bybit_bot.domain.models import SignalDecision
from adaptive_bybit_bot.recording.replay import MarketReplayConfig, MarketReplayResult


@dataclass(frozen=True)
class DictResult:
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return self.payload


class FakeBybitRestClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def __aenter__(self) -> FakeBybitRestClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


def settings_for(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path}/bot.db")


def create_buy_decision(symbol: str = "BTCUSDT") -> SignalDecision:
    return SignalDecision(
        action=SignalAction.BUY_INTENT,
        symbol=symbol,
        side=Side.BUY,
        price=100.0,
        qty=0.5,
        regime=Regime.RANGE,
        confidence=0.8,
        expected_edge_bps=40.0,
        reason=["test"],
        ttl_seconds=60,
    )


def test_settings_parse_symbols_and_credentials() -> None:
    settings = Settings(
        symbols=cast(Any, "btcusdt, ethusdt"),
        bybit_api_key="key",
        bybit_api_secret="secret",
        log_level="DEBUG",
    )

    assert settings.symbols == ["BTCUSDT", "ETHUSDT"]
    assert settings.has_bybit_credentials


def test_settings_parse_symbols_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SYMBOLS=btcusdt, ethusdt\n", encoding="utf-8")

    settings = Settings(**cast(Any, {"_env_file": env_file}))

    assert settings.symbols == ["BTCUSDT", "ETHUSDT"]


def test_settings_parse_symbols_from_json_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text('SYMBOLS=["btcusdt", "ethusdt"]\n', encoding="utf-8")

    settings = Settings(**cast(Any, {"_env_file": env_file}))

    assert settings.symbols == ["BTCUSDT", "ETHUSDT"]


def test_api_lists_health_signals_and_intents(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings)
    repository = BotRepository(create_database_engine(settings.database_url))
    repository.create_schema()
    repository.apply_signal(create_buy_decision())

    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/intents").json()[0]["symbol"] == "BTCUSDT"
    assert client.get("/signals").json()[0]["action"] == "BUY_INTENT"
    for path in [
        "/paper-fills",
        "/positions",
        "/instruments",
        "/services",
        "/locks",
        "/sentiment/fng",
        "/backtests",
        "/backtest-fills",
        "/market-recordings",
        "/market-replays",
        "/market-replay-fills",
    ]:
        assert client.get(path).status_code == 200


def test_cli_database_and_listing_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)

    cli_module.init_db()
    repository = BotRepository(create_database_engine(settings.database_url))
    intent_id = repository.apply_signal(create_buy_decision())

    cli_module.list_intents(limit=5)
    cli_module.list_signals(limit=5)

    assert intent_id is not None
    cli_module.mark_filled(intent_id=intent_id, price=101.0, qty=0.5)
    assert repository.get_position_state("BTCUSDT").is_open


def test_cli_async_commands_use_configured_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for(tmp_path)
    settings.bybit_api_key = "key"
    settings.bybit_api_secret = "secret"
    calls: list[tuple[str, object]] = []

    async def fake_run_symbol_once(**kwargs: Any) -> DictResult:
        calls.append(("run_once", kwargs["symbol"]))
        return DictResult({"ok": True})

    async def fake_run_forever(**kwargs: Any) -> None:
        calls.append(("run_forever", kwargs["symbols"]))

    async def fake_validate_read_only_key(**kwargs: Any) -> dict[str, Any]:
        calls.append(("validate", kwargs["settings"]))
        return {"readOnly": 1}

    async def fake_sync_account_once(**kwargs: Any) -> DictResult:
        calls.append(("sync", kwargs["symbols"]))
        return DictResult({"saved_executions": 0})

    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setattr(cli_module, "BybitRestClient", FakeBybitRestClient)
    monkeypatch.setattr(cli_module, "run_symbol_once", fake_run_symbol_once)
    monkeypatch.setattr(cli_module, "run_forever", fake_run_forever)
    monkeypatch.setattr(cli_module, "validate_read_only_key", fake_validate_read_only_key)
    monkeypatch.setattr(cli_module, "sync_account_once", fake_sync_account_once)

    cli_module.run_once(symbol="ethusdt")
    cli_module.run(symbols="btcusdt,ethusdt")
    cli_module.validate_key()
    cli_module.sync_account(symbols="BTCUSDT")

    assert calls == [
        ("run_once", "ETHUSDT"),
        ("run_forever", ["BTCUSDT", "ETHUSDT"]),
        ("validate", settings),
        ("sync", ["BTCUSDT"]),
    ]


def test_cli_market_recording_and_replay_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for(tmp_path)
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    cli_module.init_db()
    repository = BotRepository(create_database_engine(settings.database_url))
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    session_id = repository.start_market_recording_session(
        symbols=["BTCUSDT"],
        topics=["publicTrade.BTCUSDT"],
        depth=50,
        output_dir=str(tmp_path),
        file_path=str(tmp_path / "session.jsonl"),
        started_at=started_at,
    )
    repository.finish_market_recording_session(
        session_id,
        status="completed",
        event_count=1,
        bytes_written=10,
        ended_at=started_at + timedelta(seconds=1),
    )
    calls: list[tuple[str, object]] = []

    async def fake_record_market_forever(**kwargs: Any) -> dict[str, Any]:
        calls.append(("record", kwargs["symbols"]))
        return {"id": "recording", "status": "completed"}

    class FakeMarketReplayRunner:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(("runner", kwargs["instrument"].symbol))

        def run_file(
            self,
            input_path: Path,
            *,
            symbol: str,
            recording_session_id: str | None = None,
        ) -> MarketReplayResult:
            calls.append(("replay", str(input_path)))
            return MarketReplayResult(
                symbol=symbol,
                input_path=str(input_path),
                recording_session_id=recording_session_id,
                started_at=started_at,
                finished_at=started_at + timedelta(minutes=1),
                event_count=2,
                candle_count=1,
                decisions=[],
                fills=[
                    BacktestFill(
                        ts=started_at + timedelta(seconds=30),
                        intent_id="intent",
                        symbol=symbol,
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
                final_quote_equity=1001.0,
                realized_quote=1.0,
                unrealized_quote=0.0,
                return_pct=0.1,
                max_drawdown_pct=0.0,
                win_rate=0.0,
                closed_round_trips=0,
                open_base_qty=0.1,
                open_avg_entry=100.0,
                config=MarketReplayConfig(),
            )

    monkeypatch.setattr(cli_module, "record_market_forever", fake_record_market_forever)
    monkeypatch.setattr(cli_module, "MarketReplayRunner", FakeMarketReplayRunner)

    cli_module.record_market(
        symbols="BTCUSDT",
        seconds=5,
        depth=50,
        output_dir=tmp_path,
        service_name="unit-recorder",
    )
    cli_module.list_market_recordings(limit=5)
    cli_module.replay_market(symbol="btcusdt", recording_id=session_id, save=True)
    cli_module.list_market_replays(limit=5)
    cli_module.list_market_replay_fills(limit=5)

    with pytest.raises(typer.BadParameter, match="provide --input or --recording-id"):
        cli_module.replay_market(symbol="BTCUSDT", save=False)

    assert ("record", ["BTCUSDT"]) in calls
    assert ("runner", "BTCUSDT") in calls


def test_cli_api_command_invokes_uvicorn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for(tmp_path)
    calls: list[dict[str, Any]] = []

    def fake_run(app: object, *, host: str, port: int) -> None:
        calls.append({"app": app, "host": host, "port": port})

    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=fake_run))

    cli_module.api(host="127.0.0.1", port=9999)

    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == 9999
