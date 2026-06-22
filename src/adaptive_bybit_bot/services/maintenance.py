from __future__ import annotations

import asyncio
import logging

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.exchange.bybit_client import BybitRestClient
from adaptive_bybit_bot.sentiment.service import refresh_fear_greed_cache
from adaptive_bybit_bot.services.market_loop import refresh_instruments_once, run_paper_fill_once
from adaptive_bybit_bot.services.runtime import HeartbeatEmitter, ServiceIdentity

logger = logging.getLogger(__name__)


async def _sleep_with_heartbeat(
    *,
    seconds: int,
    settings: Settings,
    heartbeat: HeartbeatEmitter,
    status: str,
    details: dict[str, object],
) -> None:
    remaining = max(seconds, 0)
    while remaining > 0:
        step = min(remaining, max(settings.service_heartbeat_seconds, 1))
        await asyncio.sleep(step)
        remaining -= step
        heartbeat.emit(status=status, details=details, force=True)


async def run_fng_loop(
    *,
    settings: Settings,
    repository: BotRepository,
    service_name: str = "fng-sync",
    once: bool = False,
) -> None:
    identity = ServiceIdentity.from_settings(settings, service_name)
    heartbeat = HeartbeatEmitter(repository, settings, identity)
    while True:
        try:
            if not settings.fng_enabled:
                heartbeat.emit(
                    status="disabled", details={"reason": "FNG_ENABLED=false"}, force=True
                )
            else:
                context = await refresh_fear_greed_cache(settings=settings, repository=repository)
                heartbeat.emit(
                    status="running",
                    details={"value": context.value if context else None},
                    force=True,
                )
                logger.info("fng_refreshed value=%s", context.value if context else None)
        except Exception:
            heartbeat.emit(status="error", details={"loop": "fng"}, force=True)
            logger.exception("fng_loop_failed")
        if once:
            return
        await _sleep_with_heartbeat(
            seconds=settings.fng_refresh_seconds,
            settings=settings,
            heartbeat=heartbeat,
            status="sleeping" if settings.fng_enabled else "disabled",
            details={"next_refresh_seconds": settings.fng_refresh_seconds},
        )


async def run_instrument_loop(
    *,
    settings: Settings,
    repository: BotRepository,
    client: BybitRestClient,
    symbols: list[str],
    service_name: str = "instrument-sync",
    once: bool = False,
) -> None:
    identity = ServiceIdentity.from_settings(settings, service_name)
    heartbeat = HeartbeatEmitter(repository, settings, identity)
    selected_symbols = [symbol.upper() for symbol in symbols]
    while True:
        try:
            specs = await refresh_instruments_once(
                repository=repository,
                client=client,
                symbols=selected_symbols,
            )
            heartbeat.emit(
                status="running",
                details={"symbols": selected_symbols, "count": len(specs)},
                force=True,
            )
            logger.info(
                "instrument_specs_refreshed symbols=%s count=%d", selected_symbols, len(specs)
            )
        except Exception:
            heartbeat.emit(status="error", details={"symbols": selected_symbols}, force=True)
            logger.exception("instrument_loop_failed symbols=%s", selected_symbols)
        if once:
            return
        await _sleep_with_heartbeat(
            seconds=settings.instrument_refresh_seconds,
            settings=settings,
            heartbeat=heartbeat,
            status="sleeping",
            details={
                "symbols": selected_symbols,
                "next_refresh_seconds": settings.instrument_refresh_seconds,
            },
        )


async def run_paper_loop(
    *,
    settings: Settings,
    repository: BotRepository,
    client: BybitRestClient,
    symbols: list[str],
    service_name: str = "paper-runner",
    once: bool = False,
) -> None:
    identity = ServiceIdentity.from_settings(settings, service_name)
    heartbeat = HeartbeatEmitter(repository, settings, identity)
    selected_symbols = [symbol.upper() for symbol in symbols]
    while True:
        total_fills = 0
        try:
            if not settings.paper_trading_enabled:
                heartbeat.emit(
                    status="disabled",
                    details={"reason": "PAPER_TRADING_ENABLED=false", "symbols": selected_symbols},
                    force=True,
                )
                if once:
                    return
                await _sleep_with_heartbeat(
                    seconds=settings.paper_loop_interval_seconds,
                    settings=settings,
                    heartbeat=heartbeat,
                    status="disabled",
                    details={"reason": "PAPER_TRADING_ENABLED=false", "symbols": selected_symbols},
                )
                continue
            for symbol in selected_symbols:
                fills = await run_paper_fill_once(
                    settings=settings,
                    repository=repository,
                    client=client,
                    symbol=symbol,
                )
                total_fills += len(fills)
            heartbeat.emit(
                status="running",
                details={"symbols": selected_symbols, "fills": total_fills},
                force=True,
            )
            if total_fills:
                logger.info("paper_loop_fills symbols=%s fills=%d", selected_symbols, total_fills)
        except Exception:
            heartbeat.emit(status="error", details={"symbols": selected_symbols}, force=True)
            logger.exception("paper_loop_failed symbols=%s", selected_symbols)
        if once:
            return
        await _sleep_with_heartbeat(
            seconds=settings.paper_loop_interval_seconds,
            settings=settings,
            heartbeat=heartbeat,
            status="sleeping",
            details={
                "symbols": selected_symbols,
                "next_step_seconds": settings.paper_loop_interval_seconds,
            },
        )
