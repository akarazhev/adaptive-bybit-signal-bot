from __future__ import annotations

from datetime import UTC, datetime

from adaptive_bybit_bot.backtesting.engine import ensure_utc, interval_to_timedelta
from adaptive_bybit_bot.domain.models import Candle
from adaptive_bybit_bot.exchange.bybit_client import BybitRestClient


def parse_datetime(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("datetime value cannot be empty")
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return datetime.fromisoformat(raw).replace(tzinfo=UTC)
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    return ensure_utc(datetime.fromisoformat(raw))


async def fetch_historical_klines(
    *,
    client: BybitRestClient,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    category: str = "spot",
    page_limit: int = 1000,
) -> list[Candle]:
    start_utc = ensure_utc(start)
    end_utc = ensure_utc(end)
    if end_utc <= start_utc:
        raise ValueError("end must be after start")
    if page_limit <= 0:
        raise ValueError("page_limit must be positive")

    step = interval_to_timedelta(interval)
    cursor_end = end_utc
    seen: set[datetime] = set()
    candles: list[Candle] = []
    while cursor_end > start_utc:
        page = await client.get_klines(
            symbol=symbol,
            category=category,
            interval=interval,
            limit=page_limit,
            start=start_utc,
            end=cursor_end,
        )
        if not page:
            break
        for candle in page:
            ts = ensure_utc(candle.ts)
            if start_utc <= ts <= end_utc and ts not in seen:
                seen.add(ts)
                candles.append(candle)
        first_ts = min(ensure_utc(item.ts) for item in page)
        next_cursor = first_ts - step
        if next_cursor >= cursor_end:
            break
        cursor_end = next_cursor
        if len(page) < page_limit:
            break
    return sorted(candles, key=lambda item: item.ts)
