from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.data.repositories import BotRepository
from adaptive_bybit_bot.exchange.bybit_client import BybitRestClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccountSyncResult:
    api_key_info: dict[str, Any]
    wallet_snapshot_id: str | None
    open_orders_snapshot_id: str | None
    saved_executions: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "api_key_read_only": self.api_key_info.get("readOnly"),
            "wallet_snapshot_id": self.wallet_snapshot_id,
            "open_orders_snapshot_id": self.open_orders_snapshot_id,
            "saved_executions": self.saved_executions,
        }


async def validate_read_only_key(*, settings: Settings, client: BybitRestClient) -> dict[str, Any]:
    return await client.assert_read_only_key(
        allow_read_write_key=settings.bybit_allow_read_write_key,
    )


async def sync_account_once(
    *,
    settings: Settings,
    repository: BotRepository,
    client: BybitRestClient,
    symbols: list[str] | None = None,
) -> AccountSyncResult:
    if not settings.has_bybit_credentials:
        raise RuntimeError("BYBIT_API_KEY and BYBIT_API_SECRET are required for account sync")

    symbols = symbols or settings.symbols
    api_key_info = await validate_read_only_key(settings=settings, client=client)
    wallet = await client.get_wallet_balance(coins=["BTC", "ETH", "USDT", "USDC"])
    wallet_snapshot_id = repository.save_account_snapshot(kind="wallet", payload=wallet)

    open_orders_by_symbol: dict[str, Any] = {}
    saved_executions = 0
    for symbol in symbols:
        open_orders_by_symbol[symbol] = await client.get_open_orders(symbol=symbol)
        executions = await client.get_trade_history(symbol=symbol, limit=50)
        saved_executions += repository.save_executions(executions)

    open_orders_snapshot_id = repository.save_account_snapshot(
        kind="open_orders",
        payload=open_orders_by_symbol,
    )
    logger.info(
        "account_sync wallet_snapshot_id=%s open_orders_snapshot_id=%s saved_executions=%s",
        wallet_snapshot_id,
        open_orders_snapshot_id,
        saved_executions,
    )
    return AccountSyncResult(
        api_key_info=api_key_info,
        wallet_snapshot_id=wallet_snapshot_id,
        open_orders_snapshot_id=open_orders_snapshot_id,
        saved_executions=saved_executions,
    )
