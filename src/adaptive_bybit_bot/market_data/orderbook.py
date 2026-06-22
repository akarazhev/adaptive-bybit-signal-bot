from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from adaptive_bybit_bot.domain.models import OrderBook, OrderBookLevel


def ms_to_utc(value: object) -> datetime:
    try:
        return datetime.fromtimestamp(_to_int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return datetime.now(UTC)


def to_float(value: object, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        if isinstance(value, int | float | str):
            return float(value)
        return default
    except (TypeError, ValueError):
        return default


def _to_int(value: object) -> int:
    if isinstance(value, int | float | str):
        return int(value)
    raise TypeError("value cannot be converted to int")


@dataclass
class LocalOrderBook:
    """Bybit public orderbook snapshot/delta accumulator."""

    symbol: str
    depth: int = 50
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    last_update_id: int | None = None
    last_seq: int | None = None
    last_ts: datetime | None = None
    ready: bool = False

    def apply_message(self, payload: dict[str, Any]) -> bool:
        topic = str(payload.get("topic") or "")
        if not topic.startswith("orderbook."):
            return False
        data = payload.get("data")
        if not isinstance(data, dict):
            return False
        symbol = str(data.get("s") or topic.split(".")[-1]).upper()
        if symbol != self.symbol.upper():
            return False

        message_type = str(payload.get("type") or "").lower()
        update_id = _optional_int(data.get("u"))
        if message_type == "snapshot" or update_id == 1:
            self.reset(
                bids=_parse_levels(data.get("b")),
                asks=_parse_levels(data.get("a")),
                update_id=update_id,
                seq=_optional_int(data.get("seq")),
                ts=ms_to_utc(payload.get("ts") or data.get("ts")),
            )
            return True

        if message_type == "delta":
            if not self.ready:
                return False
            self._apply_delta(self.bids, data.get("b"))
            self._apply_delta(self.asks, data.get("a"))
            self._trim_depth()
            self.last_update_id = update_id if update_id is not None else self.last_update_id
            self.last_seq = _optional_int(data.get("seq")) or self.last_seq
            self.last_ts = ms_to_utc(payload.get("ts") or data.get("ts"))
            return True

        return False

    def reset(
        self,
        *,
        bids: list[OrderBookLevel],
        asks: list[OrderBookLevel],
        update_id: int | None = None,
        seq: int | None = None,
        ts: datetime | None = None,
    ) -> None:
        self.bids = {level.price: level.qty for level in bids if level.price > 0 and level.qty > 0}
        self.asks = {level.price: level.qty for level in asks if level.price > 0 and level.qty > 0}
        self._trim_depth()
        self.last_update_id = update_id
        self.last_seq = seq
        self.last_ts = ts or datetime.now(UTC)
        self.ready = bool(self.bids or self.asks)

    def as_orderbook(self) -> OrderBook:
        return OrderBook(
            symbol=self.symbol.upper(),
            ts=self.last_ts or datetime.now(UTC),
            bids=[OrderBookLevel(price=price, qty=qty) for price, qty in self.sorted_bids()],
            asks=[OrderBookLevel(price=price, qty=qty) for price, qty in self.sorted_asks()],
        )

    def sorted_bids(self) -> list[tuple[float, float]]:
        return sorted(self.bids.items(), key=lambda item: item[0], reverse=True)[: self.depth]

    def sorted_asks(self) -> list[tuple[float, float]]:
        return sorted(self.asks.items(), key=lambda item: item[0])[: self.depth]

    def spread_bps(self) -> float | None:
        book = self.as_orderbook()
        if book.mid is None or book.best_bid is None or book.best_ask is None or book.mid <= 0:
            return None
        return (book.best_ask - book.best_bid) / book.mid * 10_000

    def is_crossed(self) -> bool:
        book = self.as_orderbook()
        return bool(
            book.best_bid is not None
            and book.best_ask is not None
            and book.best_bid >= book.best_ask
        )

    def _apply_delta(self, side: dict[float, float], raw_levels: object) -> None:
        for level in _parse_levels(raw_levels):
            if level.qty <= 0:
                side.pop(level.price, None)
            else:
                side[level.price] = level.qty

    def _trim_depth(self) -> None:
        if self.depth <= 0:
            return
        self.bids = dict(self.sorted_bids())
        self.asks = dict(self.sorted_asks())


def _parse_levels(raw_levels: object) -> list[OrderBookLevel]:
    if not isinstance(raw_levels, list):
        return []
    levels: list[OrderBookLevel] = []
    for row in raw_levels:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            price = to_float(row[0])
            qty = to_float(row[1])
            if price > 0:
                levels.append(OrderBookLevel(price=price, qty=qty))
    return levels


def _optional_int(value: object) -> int | None:
    try:
        if value in (None, ""):
            return None
        return _to_int(value)
    except (TypeError, ValueError):
        return None


class LocalOrderBookStore:
    """Manage multiple local orderbooks keyed by symbol."""

    def __init__(self, symbols: list[str] | tuple[str, ...], depth: int = 50) -> None:
        if not symbols:
            raise ValueError("at least one symbol is required")
        self.books = {
            symbol.upper(): LocalOrderBook(symbol=symbol.upper(), depth=depth) for symbol in symbols
        }

    def apply_message(self, payload: dict[str, Any]) -> OrderBook | None:
        topic = str(payload.get("topic") or "")
        if not topic.startswith("orderbook."):
            return None
        symbol = topic.split(".")[-1].upper()
        book = self.books.get(symbol)
        if book is None:
            return None
        if not book.apply_message(payload):
            return None
        return book.as_orderbook() if book.ready else None

    def get(self, symbol: str) -> LocalOrderBook | None:
        return self.books.get(symbol.upper())
