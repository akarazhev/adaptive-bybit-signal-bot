from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.repositories import BotRepository


@dataclass(frozen=True)
class ServiceIdentity:
    service_name: str
    instance_id: str

    @classmethod
    def from_settings(cls, settings: Settings, service_name: str) -> ServiceIdentity:
        instance = settings.service_instance_id or f"{socket.gethostname()}-{os.getpid()}"
        return cls(service_name=service_name, instance_id=instance)

    @property
    def owner(self) -> str:
        return f"{self.service_name}:{self.instance_id}"


@dataclass
class HeartbeatEmitter:
    repository: BotRepository
    settings: Settings
    identity: ServiceIdentity
    _last_emit_ts: datetime | None = field(default=None, init=False)

    def emit(
        self,
        *,
        status: str = "running",
        details: dict[str, Any] | None = None,
        force: bool = False,
    ) -> str | None:
        now = datetime.now(UTC)
        if not force and self._last_emit_ts is not None:
            elapsed = (now - self._last_emit_ts).total_seconds()
            if elapsed < self.settings.service_heartbeat_seconds:
                return None
        self._last_emit_ts = now
        payload = {"pid": os.getpid(), "hostname": socket.gethostname(), **(details or {})}
        return self.repository.upsert_service_heartbeat(
            service_name=self.identity.service_name,
            instance_id=self.identity.instance_id,
            status=status,
            details=payload,
            stale_after_seconds=self.settings.service_heartbeat_stale_seconds,
            now=now,
        )


def service_can_write_strategy(settings: Settings, service_name: str) -> bool:
    configured = (settings.strategy_writer_service or "any").strip().lower()
    return configured in {"", "*", "any", "all", service_name.lower()}


def signal_writer_lock_name(symbol: str) -> str:
    return f"signal-writer:{symbol.upper()}"


def try_signal_writer_lock(
    repository: BotRepository,
    settings: Settings,
    identity: ServiceIdentity,
    *,
    symbol: str,
    metadata: dict[str, Any] | None = None,
) -> bool:
    if not settings.strategy_lock_enabled:
        return True
    if not service_can_write_strategy(settings, identity.service_name):
        return False
    return repository.acquire_strategy_lock(
        lock_name=signal_writer_lock_name(symbol),
        owner=identity.owner,
        ttl_seconds=settings.strategy_lock_ttl_seconds,
        metadata={
            "symbol": symbol.upper(),
            "service_name": identity.service_name,
            "instance_id": identity.instance_id,
            **(metadata or {}),
        },
    )
