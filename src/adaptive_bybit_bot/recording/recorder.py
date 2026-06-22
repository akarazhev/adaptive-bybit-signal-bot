from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.exchange.bybit_ws import BybitPublicWebSocketClient
from adaptive_bybit_bot.recording.events import RecordedMarketEvent
from adaptive_bybit_bot.recording.jsonl import JsonlMarketEventWriter

logger = logging.getLogger(__name__)


def recording_topics(symbols: list[str], *, depth: int = 50) -> list[str]:
    topics: list[str] = []
    for symbol in [item.strip().upper() for item in symbols if item.strip()]:
        topics.extend([f"tickers.{symbol}", f"publicTrade.{symbol}", f"orderbook.{depth}.{symbol}"])
    return topics


def recording_file_path(
    *,
    output_dir: str | Path,
    symbols: list[str],
    depth: int,
    compress: bool = True,
    started_at: datetime | None = None,
) -> Path:
    started_at = started_at or datetime.now(UTC)
    safe_symbols = "-".join(symbol.upper() for symbol in symbols) or "symbols"
    suffix = ".jsonl.gz" if compress else ".jsonl"
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    return Path(output_dir) / f"{stamp}-{safe_symbols}-depth{depth}{suffix}"


async def record_market_forever(
    *,
    settings: Settings,
    repository: BotRepository,
    symbols: list[str],
    seconds: int = 0,
    depth: int | None = None,
    output_dir: str | Path | None = None,
    service_name: str = "market-recorder",
) -> dict[str, Any]:
    """Record public Bybit spot WebSocket events to a JSONL(.gz) file.

    The repository stores only the session metadata. The high-volume raw payloads
    are file-backed to avoid turning PostgreSQL into a tick-data sink.
    """

    selected_symbols = [item.strip().upper() for item in symbols if item.strip()]
    if not selected_symbols:
        raise ValueError("at least one symbol is required")
    depth = depth or settings.market_recording_orderbook_depth
    output_dir = output_dir or settings.market_recording_dir
    topics = recording_topics(selected_symbols, depth=depth)
    started_at = datetime.now(UTC)
    path = recording_file_path(
        output_dir=output_dir,
        symbols=selected_symbols,
        depth=depth,
        compress=settings.market_recording_compress,
        started_at=started_at,
    )
    config = {
        "symbols": selected_symbols,
        "depth": depth,
        "seconds": seconds,
        "topics": topics,
        "url": settings.bybit_public_ws_spot_url,
        "schema_version": "v1",
        "format": "jsonl.gz" if settings.market_recording_compress else "jsonl",
    }
    session_id = repository.start_market_recording_session(
        symbols=selected_symbols,
        topics=topics,
        depth=depth,
        output_dir=str(Path(output_dir)),
        file_path=str(path),
        config=config,
        started_at=started_at,
    )
    client = BybitPublicWebSocketClient(url=settings.bybit_public_ws_spot_url)
    event_count = 0
    bytes_written = 0
    status = "finished"
    last_heartbeat = 0.0
    last_update = 0
    loop_started = time.monotonic()
    logger.info("market_recording_start session_id=%s path=%s topics=%s", session_id, path, topics)

    try:
        with JsonlMarketEventWriter(path) as writer:
            async for payload in client.stream(topics):
                event = RecordedMarketEvent.from_ws_payload(
                    payload,
                    recorded_at=datetime.now(UTC),
                    sequence=event_count + 1,
                    metadata={"session_id": session_id},
                )
                writer.write(event)
                event_count = writer.event_count

                now_monotonic = time.monotonic()
                if event_count - last_update >= settings.market_recording_flush_every_events:
                    writer.flush()
                    bytes_written = writer.bytes_written
                    repository.update_market_recording_session(
                        session_id,
                        event_count=event_count,
                        bytes_written=bytes_written,
                        status="running",
                    )
                    last_update = event_count
                if now_monotonic - last_heartbeat >= settings.service_heartbeat_seconds:
                    writer.flush()
                    bytes_written = writer.bytes_written
                    repository.upsert_service_heartbeat(
                        service_name=service_name,
                        instance_id=settings.service_instance_id,
                        status="running",
                        stale_after_seconds=settings.service_heartbeat_stale_seconds,
                        details={
                            "session_id": session_id,
                            "symbols": selected_symbols,
                            "event_count": event_count,
                            "bytes_written": bytes_written,
                            "path": str(path),
                        },
                    )
                    last_heartbeat = now_monotonic
                if seconds > 0 and now_monotonic - loop_started >= seconds:
                    break
            writer.flush()
            bytes_written = writer.bytes_written
    except Exception:
        status = "failed"
        logger.exception("market_recording_failed session_id=%s", session_id)
        raise
    finally:
        repository.finish_market_recording_session(
            session_id,
            status=status,
            event_count=event_count,
            bytes_written=bytes_written or (path.stat().st_size if path.exists() else 0),
            ended_at=datetime.now(UTC),
        )
        repository.upsert_service_heartbeat(
            service_name=service_name,
            instance_id=settings.service_instance_id,
            status=status,
            stale_after_seconds=settings.service_heartbeat_stale_seconds,
            details={
                "session_id": session_id,
                "symbols": selected_symbols,
                "event_count": event_count,
                "bytes_written": bytes_written,
                "path": str(path),
            },
        )
    return repository.get_market_recording_session(session_id) or {
        "id": session_id,
        "status": status,
        "file_path": str(path),
        "event_count": event_count,
        "bytes_written": bytes_written,
    }
