from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from adaptive_bybit_bot.domain.models import Candle

FIELDNAMES = ["ts", "open", "high", "low", "close", "volume"]


def write_candles_csv(path: str | Path, candles: list[Candle]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for candle in sorted(candles, key=lambda item: item.ts):
            writer.writerow(
                {
                    "ts": candle.ts.isoformat(),
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
            )


def read_candles_csv(path: str | Path) -> list[Candle]:
    source = Path(path)
    candles: list[Candle] = []
    with source.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            candles.append(
                Candle(
                    ts=_parse_ts(row.get("ts") or row.get("startTime") or row.get("timestamp")),
                    open=float(row.get("open") or row.get("openPrice") or 0.0),
                    high=float(row.get("high") or row.get("highPrice") or 0.0),
                    low=float(row.get("low") or row.get("lowPrice") or 0.0),
                    close=float(row.get("close") or row.get("closePrice") or 0.0),
                    volume=float(row.get("volume") or 0.0),
                )
            )
    return sorted(candles, key=lambda candle: candle.ts)


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    value = value.strip()
    if value.isdigit():
        raw = int(value)
        if raw > 10_000_000_000:
            return datetime.fromtimestamp(raw / 1000, tz=UTC)
        return datetime.fromtimestamp(raw, tz=UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
