from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.db import create_database_engine
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.services.runtime import (
    ServiceIdentity,
    service_can_write_strategy,
    signal_writer_lock_name,
    try_signal_writer_lock,
)


def _repo(tmp_path: Path) -> BotRepository:
    engine = create_database_engine(f"sqlite:///{tmp_path}/bot.db")
    repo = BotRepository(engine)
    repo.create_schema()
    return repo


def test_service_heartbeat_upsert_and_staleness(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.upsert_service_heartbeat(
        service_name="ws-shadow",
        instance_id="instance-1",
        details={"symbols": ["BTCUSDT"]},
        stale_after_seconds=5,
        now=datetime.now(UTC) - timedelta(seconds=10),
    )

    rows = repo.list_service_heartbeats(limit=10)
    assert len(rows) == 1
    assert rows[0]["service_name"] == "ws-shadow"
    assert rows[0]["details"]["symbols"] == ["BTCUSDT"]
    assert rows[0]["is_stale"] is True

    repo.upsert_service_heartbeat(
        service_name="ws-shadow",
        instance_id="instance-1",
        details={"symbols": ["ETHUSDT"]},
        stale_after_seconds=120,
    )
    rows = repo.list_service_heartbeats(limit=10)
    assert len(rows) == 1
    assert rows[0]["details"]["symbols"] == ["ETHUSDT"]
    assert rows[0]["is_stale"] is False


def test_strategy_lock_lease_and_takeover(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    now = datetime.now(UTC)
    assert repo.acquire_strategy_lock(
        lock_name="signal-writer:BTCUSDT",
        owner="ws-shadow:a",
        ttl_seconds=30,
        now=now,
    )
    assert not repo.acquire_strategy_lock(
        lock_name="signal-writer:BTCUSDT",
        owner="bot-rest:b",
        ttl_seconds=30,
        now=now + timedelta(seconds=5),
    )
    assert repo.acquire_strategy_lock(
        lock_name="signal-writer:BTCUSDT",
        owner="bot-rest:b",
        ttl_seconds=30,
        now=now + timedelta(seconds=31),
    )

    locks = repo.list_strategy_locks(limit=10)
    assert locks[0]["owner"] == "bot-rest:b"
    assert locks[0]["is_effectively_active"] is True


def test_runtime_writer_filter_and_lock_helper(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/bot.db",
        strategy_writer_service="ws-shadow",
        service_instance_id="instance-1",
    )
    assert service_can_write_strategy(settings, "ws-shadow")
    assert not service_can_write_strategy(settings, "bot-rest")
    assert signal_writer_lock_name("btcusdt") == "signal-writer:BTCUSDT"

    identity = ServiceIdentity.from_settings(settings, "ws-shadow")
    assert try_signal_writer_lock(repo, settings, identity, symbol="BTCUSDT")
