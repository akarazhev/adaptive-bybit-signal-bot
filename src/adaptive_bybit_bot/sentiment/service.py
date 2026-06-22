from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.models import FearGreedContext
from adaptive_bybit_bot.sentiment.alternative_me import AlternativeMeFearGreedClient

logger = logging.getLogger(__name__)


async def refresh_fear_greed_cache(
    *,
    settings: Settings,
    repository: BotRepository,
    limit: int | None = None,
) -> FearGreedContext | None:
    """Fetch current/history FNG data and persist it locally."""
    requested_limit = settings.fng_history_limit if limit is None else limit
    async with AlternativeMeFearGreedClient(base_url=settings.fng_base_url) as client:
        values = []
        if requested_limit == 0 or requested_limit > 1:
            values.extend(await client.get_values(limit=requested_limit))
        latest = await client.get_latest()
        values.append(latest)
    repository.save_fear_greed_values(values)
    return repository.get_fear_greed_context(limit=max(requested_limit, 8))


async def get_fear_greed_context_for_strategy(
    *,
    settings: Settings,
    repository: BotRepository,
    now: datetime | None = None,
) -> FearGreedContext | None:
    """Return cached FNG context, refreshing it if the cache is old enough."""
    if not settings.fng_enabled:
        return None
    now = now or datetime.now(UTC)
    context = repository.get_fear_greed_context(limit=max(settings.fng_history_limit, 8))
    if context is not None:
        fetched_at = context.current.fetched_at
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        fetched_age = (now.astimezone(UTC) - fetched_at.astimezone(UTC)).total_seconds()
        if fetched_age < settings.fng_refresh_seconds:
            return context
    try:
        return await refresh_fear_greed_cache(settings=settings, repository=repository)
    except httpx.HTTPError as exc:
        logger.warning("fng_refresh_failed error=%s", exc)
        return context
