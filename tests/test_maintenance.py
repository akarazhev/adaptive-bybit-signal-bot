from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.db import create_database_engine
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.models import InstrumentSpec
from adaptive_bybit_bot.services import maintenance
from adaptive_bybit_bot.services.runtime import HeartbeatEmitter, ServiceIdentity


def repository_for(tmp_path: Path) -> BotRepository:
    repository = BotRepository(create_database_engine(f"sqlite:///{tmp_path}/bot.db"))
    repository.create_schema()
    return repository


def settings_for(tmp_path: Path, **overrides: Any) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path}/bot.db", **overrides)


def test_sleep_with_heartbeat_emits_during_wait(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for(tmp_path, service_heartbeat_seconds=1)
    repository = repository_for(tmp_path)
    heartbeat = HeartbeatEmitter(
        repository=repository,
        settings=settings,
        identity=ServiceIdentity(service_name="sleeper", instance_id="instance-1"),
    )
    sleeps: list[int] = []

    async def fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("adaptive_bybit_bot.services.maintenance.asyncio.sleep", fake_sleep)

    asyncio.run(
        maintenance._sleep_with_heartbeat(
            seconds=3,
            settings=settings,
            heartbeat=heartbeat,
            status="sleeping",
            details={"loop": "test"},
        )
    )

    assert sleeps == [1, 1, 1]
    row = repository.list_service_heartbeats(limit=1)[0]
    assert row["service_name"] == "sleeper"
    assert row["status"] == "sleeping"


def test_fng_loop_records_disabled_running_and_error_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = repository_for(tmp_path)

    asyncio.run(
        maintenance.run_fng_loop(
            settings=settings_for(tmp_path, fng_enabled=False),
            repository=repository,
            service_name="fng-disabled",
            once=True,
        )
    )

    async def fake_refresh(**_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(value=42)

    monkeypatch.setattr(maintenance, "refresh_fear_greed_cache", fake_refresh)
    asyncio.run(
        maintenance.run_fng_loop(
            settings=settings_for(tmp_path, fng_enabled=True),
            repository=repository,
            service_name="fng-running",
            once=True,
        )
    )

    async def failing_refresh(**_kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(maintenance, "refresh_fear_greed_cache", failing_refresh)
    asyncio.run(
        maintenance.run_fng_loop(
            settings=settings_for(tmp_path, fng_enabled=True),
            repository=repository,
            service_name="fng-error",
            once=True,
        )
    )

    rows = {row["service_name"]: row for row in repository.list_service_heartbeats(limit=10)}
    assert rows["fng-disabled"]["status"] == "disabled"
    assert rows["fng-running"]["status"] == "running"
    assert rows["fng-running"]["details"]["value"] == 42
    assert rows["fng-error"]["status"] == "error"


def test_instrument_and_paper_loops_record_heartbeats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = repository_for(tmp_path)

    async def fake_refresh_instruments_once(**kwargs: Any) -> list[InstrumentSpec]:
        return [InstrumentSpec.fallback(symbol) for symbol in kwargs["symbols"]]

    async def fake_run_paper_fill_once(**_kwargs: Any) -> list[object]:
        return [object(), object()]

    monkeypatch.setattr(maintenance, "refresh_instruments_once", fake_refresh_instruments_once)
    monkeypatch.setattr(maintenance, "run_paper_fill_once", fake_run_paper_fill_once)

    asyncio.run(
        maintenance.run_instrument_loop(
            settings=settings_for(tmp_path),
            repository=repository,
            client=object(),  # type: ignore[arg-type]
            symbols=["btcusdt", "ethusdt"],
            service_name="instrument-test",
            once=True,
        )
    )
    asyncio.run(
        maintenance.run_paper_loop(
            settings=settings_for(tmp_path, paper_trading_enabled=False),
            repository=repository,
            client=object(),  # type: ignore[arg-type]
            symbols=["btcusdt"],
            service_name="paper-disabled",
            once=True,
        )
    )
    asyncio.run(
        maintenance.run_paper_loop(
            settings=settings_for(tmp_path, paper_trading_enabled=True),
            repository=repository,
            client=object(),  # type: ignore[arg-type]
            symbols=["btcusdt"],
            service_name="paper-running",
            once=True,
        )
    )

    rows = {row["service_name"]: row for row in repository.list_service_heartbeats(limit=10)}
    assert rows["instrument-test"]["status"] == "running"
    assert rows["instrument-test"]["details"]["count"] == 2
    assert rows["paper-disabled"]["status"] == "disabled"
    assert rows["paper-running"]["details"]["fills"] == 2
