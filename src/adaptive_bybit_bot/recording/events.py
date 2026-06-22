from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from adaptive_bybit_bot.market_data.orderbook import ms_to_utc


@dataclass(frozen=True)
class RecordedMarketEvent:
    """Single raw public-market event recorded from a WebSocket stream.

    The payload is intentionally stored unchanged. The normalized columns make
    sessions searchable and replayable without losing the exact exchange message.
    """

    recorded_at: datetime
    event_kind: str
    topic: str
    symbol: str | None
    payload: dict[str, Any]
    source: str = "bybit_public_ws"
    exchange_ts: datetime | None = None
    schema_version: str = "v1"
    sequence: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_ws_payload(
        cls,
        payload: dict[str, Any],
        *,
        recorded_at: datetime | None = None,
        sequence: int | None = None,
        source: str = "bybit_public_ws",
        metadata: dict[str, Any] | None = None,
    ) -> RecordedMarketEvent:
        topic = str(payload.get("topic") or "")
        return cls(
            recorded_at=_ensure_utc(recorded_at or datetime.now(UTC)),
            event_kind=_event_kind(topic, payload),
            topic=topic,
            symbol=_symbol_from_payload(topic, payload),
            payload=payload,
            source=source,
            exchange_ts=_exchange_ts(payload),
            sequence=sequence,
            metadata=metadata or {},
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "recorded_at": self.recorded_at.isoformat(),
            "exchange_ts": self.exchange_ts.isoformat() if self.exchange_ts else None,
            "event_kind": self.event_kind,
            "topic": self.topic,
            "symbol": self.symbol,
            "sequence": self.sequence,
            "metadata": self.metadata,
            "payload": self.payload,
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> RecordedMarketEvent:
        symbol = value.get("symbol")
        metadata = value.get("metadata")
        payload = value.get("payload")
        return cls(
            schema_version=str(value.get("schema_version") or "v1"),
            source=str(value.get("source") or "bybit_public_ws"),
            recorded_at=_parse_datetime(value.get("recorded_at")),
            exchange_ts=_parse_optional_datetime(value.get("exchange_ts")),
            event_kind=str(value.get("event_kind") or "other"),
            topic=str(value.get("topic") or ""),
            symbol=str(symbol).upper() if symbol else None,
            sequence=_optional_int(value.get("sequence")),
            metadata=metadata if isinstance(metadata, dict) else {},
            payload=payload if isinstance(payload, dict) else {},
        )


def _event_kind(topic: str, payload: dict[str, Any]) -> str:
    if topic.startswith("orderbook."):
        return "orderbook"
    if topic.startswith("publicTrade."):
        return "trade"
    if topic.startswith("tickers."):
        return "ticker"
    if payload.get("op"):
        return "control"
    return "other"


def _symbol_from_payload(topic: str, payload: dict[str, Any]) -> str | None:
    if topic:
        parts = topic.split(".")
        if len(parts) >= 2:
            return parts[-1].upper()
    data = payload.get("data")
    if isinstance(data, dict):
        symbol = data.get("s") or data.get("symbol")
        if symbol:
            return str(symbol).upper()
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and (row.get("s") or row.get("symbol")):
                return str(row.get("s") or row.get("symbol")).upper()
    return None


def _exchange_ts(payload: dict[str, Any]) -> datetime | None:
    for candidate in (payload.get("ts"), payload.get("creationTime")):
        if candidate not in (None, ""):
            return ms_to_utc(candidate)
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("ts", "T", "time"):
            if data.get(key) not in (None, ""):
                return ms_to_utc(data.get(key))
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                for key in ("T", "ts", "time"):
                    if row.get(key) not in (None, ""):
                        return ms_to_utc(row.get(key))
    return None


def _parse_datetime(value: object) -> datetime:
    return _parse_optional_datetime(value) or datetime.now(UTC)


def _parse_optional_datetime(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    try:
        return _ensure_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_int(value: object) -> int | None:
    try:
        if value in (None, ""):
            return None
        return _to_int(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"value cannot be converted to int: {value!r}")
