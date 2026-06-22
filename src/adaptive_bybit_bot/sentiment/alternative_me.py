from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from adaptive_bybit_bot.domain.models import FearGreedValue, utc_now


class AlternativeMeApiError(RuntimeError):
    """Raised when Alternative.me returns an invalid or error response."""


class AlternativeMeFearGreedClient:
    """Async client for Alternative.me Crypto Fear & Greed Index API.

    API documentation: GET /fng/ with optional limit/format/date_format.
    This client intentionally fetches only sentiment data and has no exchange access.
    """

    def __init__(
        self,
        *,
        base_url: str = "https://api.alternative.me",
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._own_client = client is None
        self._client = client or httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def __aenter__(self) -> AlternativeMeFearGreedClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()

    async def get_latest(self) -> FearGreedValue:
        values = await self.get_values(limit=1)
        if not values:
            raise AlternativeMeApiError("Alternative.me returned no Fear & Greed values")
        return values[0]

    async def get_values(self, *, limit: int = 1) -> list[FearGreedValue]:
        if limit < 0:
            raise ValueError("limit must be >= 0")
        response = await self._client.get("/fng/", params={"limit": limit, "format": "json"})
        response.raise_for_status()
        payload = response.json()
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        if isinstance(metadata, dict) and metadata.get("error"):
            raise AlternativeMeApiError(str(metadata["error"]))
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise AlternativeMeApiError("Alternative.me response does not contain data list")
        fetched_at = utc_now()
        return [_parse_fng_row(row, fetched_at=fetched_at) for row in data if isinstance(row, dict)]


def _parse_fng_row(row: dict[str, Any], *, fetched_at: datetime) -> FearGreedValue:
    try:
        value = int(str(row["value"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AlternativeMeApiError(f"invalid Fear & Greed value: {row!r}") from exc
    classification = str(row.get("value_classification") or "Unknown")
    try:
        timestamp = datetime.fromtimestamp(int(str(row["timestamp"])), tz=UTC)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise AlternativeMeApiError(f"invalid Fear & Greed timestamp: {row!r}") from exc
    time_until_update: int | None = None
    if row.get("time_until_update") not in (None, ""):
        try:
            time_until_update = int(str(row["time_until_update"]))
        except (TypeError, ValueError):
            time_until_update = None
    return FearGreedValue(
        source="alternative.me",
        value=max(0, min(100, value)),
        classification=classification,
        timestamp=timestamp,
        time_until_update_seconds=time_until_update,
        fetched_at=fetched_at,
        raw=row,
    )
