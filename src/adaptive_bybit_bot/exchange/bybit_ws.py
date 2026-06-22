from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterable
from typing import Any
from uuid import uuid4

import websockets

from adaptive_bybit_bot.domain.models import OrderBook
from adaptive_bybit_bot.market_data.orderbook import LocalOrderBookStore

logger = logging.getLogger(__name__)


class BybitPublicWebSocketClient:
    """Minimal public WebSocket client for Bybit spot market data.

    This client intentionally supports public subscriptions only. It has no private auth and
    no order-entry WebSocket path.
    """

    def __init__(
        self,
        *,
        url: str = "wss://stream.bybit.com/v5/public/spot",
        ping_interval_seconds: int = 20,
    ) -> None:
        self.url = url
        self.ping_interval_seconds = ping_interval_seconds

    async def stream(self, topics: Iterable[str]) -> AsyncIterator[dict[str, Any]]:
        topic_list = list(topics)
        if not topic_list:
            raise ValueError("at least one topic is required")
        async with websockets.connect(self.url, ping_interval=None) as websocket:
            await self._subscribe(websocket, topic_list)
            ping_task = asyncio.create_task(self._ping_loop(websocket))
            try:
                async for raw in websocket:
                    try:
                        payload: dict[str, Any] = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("ws_non_json_message raw=%r", raw)
                        continue
                    yield payload
            finally:
                ping_task.cancel()
                await asyncio.gather(ping_task, return_exceptions=True)

    async def stream_orderbooks(
        self,
        *,
        symbols: Iterable[str],
        depth: int = 50,
    ) -> AsyncIterator[OrderBook]:
        """Yield local orderbook snapshots maintained from public snapshot/delta messages."""
        symbol_list = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
        if not symbol_list:
            raise ValueError("at least one symbol is required")
        topics = [f"orderbook.{depth}.{symbol}" for symbol in symbol_list]
        store = LocalOrderBookStore(symbol_list, depth=depth)
        async for payload in self.stream(topics):
            orderbook = store.apply_message(payload)
            if orderbook is not None:
                yield orderbook

    @staticmethod
    async def _subscribe(websocket: Any, topics: list[str]) -> None:
        await websocket.send(
            json.dumps({"req_id": str(uuid4()), "op": "subscribe", "args": topics})
        )

    async def _ping_loop(self, websocket: Any) -> None:
        while True:
            await asyncio.sleep(self.ping_interval_seconds)
            await websocket.send(json.dumps({"req_id": str(uuid4()), "op": "ping"}))
