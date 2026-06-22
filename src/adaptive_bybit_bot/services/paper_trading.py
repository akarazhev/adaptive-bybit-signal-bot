from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.domain.models import MarketSnapshot, Trade


class ActiveIntentLike(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def symbol(self) -> str: ...

    @property
    def side(self) -> str: ...

    @property
    def limit_price(self) -> float: ...

    @property
    def qty(self) -> float: ...

    @property
    def created_at(self) -> datetime: ...


@dataclass(frozen=True)
class PaperFillResult:
    intent_id: str
    symbol: str
    side: str
    limit_price: float
    fill_price: float
    fill_qty: float
    reason: str
    crossing_qty: float

    def as_dict(self) -> dict[str, object]:
        return {
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "side": self.side,
            "limit_price": self.limit_price,
            "fill_price": self.fill_price,
            "fill_qty": self.fill_qty,
            "reason": self.reason,
            "crossing_qty": self.crossing_qty,
        }


class PaperFillSimulator:
    """Conservative fill model for paper trading order intents.

    The simulator is intentionally separate from the strategy. It reads active local intents,
    checks whether later market data traded through the limit, and then marks the intent as
    filled in the local ledger. It never calls a Bybit order endpoint.
    """

    def __init__(
        self,
        repository: BotRepository,
        *,
        mode: str = "trade_through",
        min_fill_ratio: float = 1.0,
        max_trade_age_seconds: int = 300,
    ) -> None:
        if mode not in {"trade_through", "touch"}:
            raise ValueError("paper fill mode must be 'trade_through' or 'touch'")
        if min_fill_ratio <= 0 or min_fill_ratio > 1:
            raise ValueError("paper min fill ratio must be in (0, 1]")
        self.repository = repository
        self.mode = mode
        self.min_fill_ratio = min_fill_ratio
        self.max_trade_age_seconds = max_trade_age_seconds

    def simulate_snapshot(self, snapshot: MarketSnapshot) -> list[PaperFillResult]:
        results: list[PaperFillResult] = []
        for intent in self.repository.active_intents(snapshot.symbol):
            result = self._simulate_intent(intent, snapshot)
            if result is None:
                continue
            self.repository.mark_intent_filled(
                result.intent_id,
                fill_price=result.fill_price,
                fill_qty=result.fill_qty,
                filled_at=snapshot.ts,
                source="paper",
                reason={
                    "paper_reason": result.reason,
                    "crossing_qty": result.crossing_qty,
                    "mode": self.mode,
                },
            )
            results.append(result)
        return results

    def _simulate_intent(
        self,
        intent: ActiveIntentLike,
        snapshot: MarketSnapshot,
    ) -> PaperFillResult | None:
        side = Side(intent.side)
        crossing_trades = self._crossing_trades(intent, snapshot, side)
        crossing_qty = sum(trade.qty for trade in crossing_trades)
        required_qty = intent.qty * self.min_fill_ratio

        if crossing_qty >= required_qty:
            fill_qty = min(intent.qty, crossing_qty)
            return PaperFillResult(
                intent_id=intent.id,
                symbol=intent.symbol,
                side=side.value,
                limit_price=intent.limit_price,
                fill_price=intent.limit_price,
                fill_qty=fill_qty,
                reason="trade_through_limit",
                crossing_qty=crossing_qty,
            )

        book_qty = self._book_crossing_qty(intent, snapshot, side)
        if self.mode == "touch" and book_qty >= required_qty:
            fill_qty = min(intent.qty, book_qty)
            return PaperFillResult(
                intent_id=intent.id,
                symbol=intent.symbol,
                side=side.value,
                limit_price=intent.limit_price,
                fill_price=intent.limit_price,
                fill_qty=fill_qty,
                reason="book_touched_or_crossed_limit",
                crossing_qty=book_qty,
            )

        return None

    def _crossing_trades(
        self,
        intent: ActiveIntentLike,
        snapshot: MarketSnapshot,
        side: Side,
    ) -> list[Trade]:
        created_at = _aware(intent.created_at)
        snapshot_ts = _aware(snapshot.ts)
        trades: list[Trade] = []
        for trade in snapshot.trades:
            trade_ts = _aware(trade.ts)
            if trade_ts < created_at:
                continue
            if self.max_trade_age_seconds > 0:
                if (snapshot_ts - trade_ts).total_seconds() > self.max_trade_age_seconds:
                    continue
            if side == Side.BUY and trade.price <= intent.limit_price:
                trades.append(trade)
            elif side == Side.SELL and trade.price >= intent.limit_price:
                trades.append(trade)
        return trades

    @staticmethod
    def _book_crossing_qty(
        intent: ActiveIntentLike,
        snapshot: MarketSnapshot,
        side: Side,
    ) -> float:
        if side == Side.BUY:
            return sum(
                level.qty for level in snapshot.orderbook.asks if level.price <= intent.limit_price
            )
        return sum(
            level.qty for level in snapshot.orderbook.bids if level.price >= intent.limit_price
        )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
