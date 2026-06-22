from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.domain.models import (
    Candle,
    DerivativesContext,
    MarketSnapshot,
    OrderBook,
    Trade,
)
from adaptive_bybit_bot.market_data.orderbook import LocalOrderBook, ms_to_utc, to_float


@dataclass(frozen=True)
class TickerState:
    symbol: str
    ts: datetime
    last_price: float | None = None
    bid1_price: float | None = None
    ask1_price: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class WebSocketMarketDataCache:
    """In-memory cache for public Bybit spot streams."""

    def __init__(
        self,
        *,
        symbols: list[str],
        orderbook_depth: int = 50,
        max_trades_per_symbol: int = 2_000,
    ) -> None:
        if not symbols:
            raise ValueError("at least one symbol is required")
        self.symbols = [symbol.upper() for symbol in symbols]
        self.orderbooks = {
            symbol: LocalOrderBook(symbol=symbol, depth=orderbook_depth) for symbol in self.symbols
        }
        self.trades: dict[str, deque[Trade]] = {
            symbol: deque(maxlen=max_trades_per_symbol) for symbol in self.symbols
        }
        self.tickers: dict[str, TickerState] = {}
        self.message_count = 0
        self.last_message_at: datetime | None = None

    def handle_message(self, payload: dict[str, Any]) -> bool:
        self.message_count += 1
        self.last_message_at = datetime.now(UTC)
        topic = str(payload.get("topic") or "")
        if topic.startswith("orderbook."):
            symbol = _topic_symbol(topic)
            book = self.orderbooks.get(symbol)
            return book.apply_message(payload) if book else False
        if topic.startswith("publicTrade."):
            return self._handle_trades(payload)
        if topic.startswith("tickers."):
            return self._handle_ticker(payload)
        return False

    def ready_symbols(self) -> list[str]:
        return [symbol for symbol, book in self.orderbooks.items() if book.ready]

    def is_ready(self, symbol: str) -> bool:
        book = self.orderbooks.get(symbol.upper())
        return bool(book and book.ready)

    def orderbook(self, symbol: str) -> OrderBook | None:
        book = self.orderbooks.get(symbol.upper())
        if book is None or not book.ready:
            return None
        return book.as_orderbook()

    def recent_trades(
        self,
        symbol: str,
        *,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[Trade]:
        rows = list(self.trades.get(symbol.upper(), []))
        if since is not None:
            since = _aware(since)
            rows = [trade for trade in rows if _aware(trade.ts) >= since]
        if limit is not None and limit > 0:
            rows = rows[-limit:]
        return rows

    def build_snapshot(
        self,
        *,
        symbol: str,
        candles: list[Candle],
        derivatives: DerivativesContext | None = None,
        trade_lookback_seconds: int = 120,
    ) -> MarketSnapshot | None:
        symbol = symbol.upper()
        book = self.orderbook(symbol)
        if book is None:
            return None
        now = datetime.now(UTC)
        since = now - timedelta(seconds=trade_lookback_seconds)
        return MarketSnapshot(
            symbol=symbol,
            ts=now,
            candles=candles,
            orderbook=book,
            trades=self.recent_trades(symbol, since=since),
            derivatives=derivatives or DerivativesContext(),
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "symbols": self.symbols,
            "ready_symbols": self.ready_symbols(),
            "message_count": self.message_count,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "books": {
                symbol: {
                    "ready": book.ready,
                    "best_bid": book.as_orderbook().best_bid if book.ready else None,
                    "best_ask": book.as_orderbook().best_ask if book.ready else None,
                    "spread_bps": book.spread_bps() if book.ready else None,
                    "last_update_id": book.last_update_id,
                    "last_seq": book.last_seq,
                    "last_ts": book.last_ts.isoformat() if book.last_ts else None,
                }
                for symbol, book in self.orderbooks.items()
            },
            "trades": {symbol: len(rows) for symbol, rows in self.trades.items()},
        }

    def _handle_trades(self, payload: dict[str, Any]) -> bool:
        topic = str(payload.get("topic") or "")
        symbol = _topic_symbol(topic)
        if symbol not in self.trades:
            return False
        rows = payload.get("data")
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return False
        changed = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            trade_symbol = str(row.get("s") or symbol).upper()
            if trade_symbol != symbol:
                continue
            side_raw = str(row.get("S") or row.get("side") or "").upper()
            side = Side.BUY if side_raw == "BUY" else Side.SELL if side_raw == "SELL" else None
            self.trades[symbol].append(
                Trade(
                    ts=ms_to_utc(row.get("T") or payload.get("ts")),
                    price=to_float(row.get("p") or row.get("price")),
                    qty=to_float(row.get("v") or row.get("size")),
                    side=side,
                )
            )
            changed = True
        return changed

    def _handle_ticker(self, payload: dict[str, Any]) -> bool:
        topic = str(payload.get("topic") or "")
        symbol = _topic_symbol(topic)
        if symbol not in self.symbols:
            return False
        data = payload.get("data")
        if not isinstance(data, dict):
            return False
        self.tickers[symbol] = TickerState(
            symbol=symbol,
            ts=ms_to_utc(payload.get("ts")),
            last_price=_optional_float(data.get("lastPrice")),
            bid1_price=_optional_float(data.get("bid1Price")),
            ask1_price=_optional_float(data.get("ask1Price")),
            raw=data,
        )
        return True


def _topic_symbol(topic: str) -> str:
    return topic.split(".")[-1].upper()


def _optional_float(value: object) -> float | None:
    result = to_float(value, default=0.0)
    return result if result > 0 else None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
