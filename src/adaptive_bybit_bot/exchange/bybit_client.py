from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, cast

import httpx

from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.domain.models import (
    Candle,
    DerivativesContext,
    InstrumentSpec,
    MarketSnapshot,
    OrderBook,
    OrderBookLevel,
    Trade,
)
from adaptive_bybit_bot.exchange.signing import canonical_query, sign_get_request


class BybitApiError(RuntimeError):
    def __init__(self, message: str, ret_code: int | None = None) -> None:
        super().__init__(message)
        self.ret_code = ret_code


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        if isinstance(value, int | float | str):
            return float(value)
        return default
    except (TypeError, ValueError):
        return default


def _ms_to_dt(value: object) -> datetime:
    try:
        return datetime.fromtimestamp(_to_int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return datetime.now(UTC)


def _to_int(value: object) -> int:
    if isinstance(value, int | float | str):
        return int(value)
    raise TypeError("value cannot be converted to int")


def _result_dict(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


def _dt_to_ms(value: datetime | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1000)


class BybitRestClient:
    """Small Bybit V5 REST adapter.

    The class deliberately implements only public market-data and read-only account endpoints.
    It has no place/cancel/amend order method.
    """

    def __init__(
        self,
        *,
        base_url: str = "https://api.bybit.com",
        api_key: str | None = None,
        api_secret: str | None = None,
        recv_window: int = 5000,
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.recv_window = recv_window
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._instrument_cache: dict[tuple[str, str], InstrumentSpec] = {}

    async def __aenter__(self) -> BybitRestClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get(
        self,
        path: str,
        params: dict[str, object] | None = None,
        *,
        signed: bool = False,
    ) -> dict[str, Any]:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        headers: dict[str, str] = {}
        url = f"{self.base_url}{path}"

        if signed:
            if not self.api_key or not self.api_secret:
                raise BybitApiError("Bybit API key/secret are required for signed read-only calls")
            timestamp_ms = int(time.time() * 1000)
            signature = sign_get_request(
                timestamp_ms=timestamp_ms,
                api_key=self.api_key,
                secret=self.api_secret,
                recv_window=self.recv_window,
                params=params,
            )
            headers.update(
                {
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-SIGN-TYPE": "2",
                    "X-BAPI-TIMESTAMP": str(timestamp_ms),
                    "X-BAPI-RECV-WINDOW": str(self.recv_window),
                }
            )

        response = await self._client.get(url, params=canonical_query(params), headers=headers)
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
        ret_code = payload.get("retCode")
        if ret_code not in (0, "0"):
            raise BybitApiError(
                f"Bybit API error {ret_code}: {payload.get('retMsg', 'unknown error')}",
                ret_code=int(ret_code) if isinstance(ret_code, int) else None,
            )
        return payload

    async def get_instruments_info(
        self,
        *,
        category: str = "spot",
        symbol: str | None = None,
        use_cache: bool = True,
    ) -> list[InstrumentSpec]:
        if use_cache and symbol is not None:
            cached = self._instrument_cache.get((category, symbol.upper()))
            if cached is not None:
                return [cached]

        payload = await self._get(
            "/v5/market/instruments-info",
            {"category": category, "symbol": symbol},
        )
        rows = _result_dict(payload).get("list", [])
        instruments: list[InstrumentSpec] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            instrument = self._parse_instrument_spec(
                row,
                category=category,
                requested_symbol=symbol or "",
            )
            instruments.append(instrument)
            self._instrument_cache[(category, instrument.symbol)] = instrument
        return instruments

    async def get_instrument_info(
        self,
        symbol: str,
        *,
        category: str = "spot",
        use_cache: bool = True,
    ) -> InstrumentSpec:
        instruments = await self.get_instruments_info(
            category=category,
            symbol=symbol,
            use_cache=use_cache,
        )
        for instrument in instruments:
            if instrument.symbol == symbol.upper():
                return instrument
        raise BybitApiError(f"instrument not found: {category}/{symbol}")

    async def get_klines(
        self,
        symbol: str,
        *,
        category: str = "spot",
        interval: str = "1",
        limit: int = 240,
        start: datetime | int | None = None,
        end: datetime | int | None = None,
    ) -> list[Candle]:
        limit = min(max(limit, 1), 1000)
        payload = await self._get(
            "/v5/market/kline",
            {
                "category": category,
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "start": _dt_to_ms(start),
                "end": _dt_to_ms(end),
            },
        )
        rows = _result_dict(payload).get("list", [])
        candles = [
            Candle(
                ts=_ms_to_dt(row[0]),
                open=_to_float(row[1]),
                high=_to_float(row[2]),
                low=_to_float(row[3]),
                close=_to_float(row[4]),
                volume=_to_float(row[5]),
            )
            for row in rows
            if isinstance(row, list) and len(row) >= 6
        ]
        return sorted(candles, key=lambda item: item.ts)

    async def get_orderbook(
        self,
        symbol: str,
        *,
        category: str = "spot",
        limit: int = 50,
    ) -> OrderBook:
        payload = await self._get(
            "/v5/market/orderbook",
            {"category": category, "symbol": symbol, "limit": limit},
        )
        result = _result_dict(payload)
        bids = self._parse_levels(result.get("b"))
        asks = self._parse_levels(result.get("a"))
        ts = _ms_to_dt(result.get("ts", payload.get("time")))
        return OrderBook(symbol=symbol, ts=ts, bids=bids, asks=asks)

    async def get_recent_trades(
        self,
        symbol: str,
        *,
        category: str = "spot",
        limit: int = 60,
    ) -> list[Trade]:
        # Bybit V5 limits recent public trades for spot to 1..60.
        # Clamp locally so a permissive user config does not break the whole cycle.
        if category == "spot":
            limit = min(max(limit, 1), 60)
        payload = await self._get(
            "/v5/market/recent-trade",
            {"category": category, "symbol": symbol, "limit": limit},
        )
        rows = _result_dict(payload).get("list", [])
        trades: list[Trade] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            side_raw = str(row.get("side", "")).upper()
            side = Side.BUY if side_raw == "BUY" else Side.SELL if side_raw == "SELL" else None
            trades.append(
                Trade(
                    ts=_ms_to_dt(row.get("time")),
                    price=_to_float(row.get("price")),
                    qty=_to_float(row.get("size")),
                    side=side,
                )
            )
        return sorted(trades, key=lambda item: item.ts)

    async def get_funding_rates(self, linear_symbol: str, *, limit: int = 10) -> list[float]:
        payload = await self._get(
            "/v5/market/funding/history",
            {"category": "linear", "symbol": linear_symbol, "limit": limit},
        )
        rows = _result_dict(payload).get("list", [])
        rates = [_to_float(row.get("fundingRate")) for row in rows if isinstance(row, dict)]
        return list(reversed(rates))

    async def get_open_interest_values(
        self,
        linear_symbol: str,
        *,
        interval_time: str = "5min",
        limit: int = 5,
    ) -> list[float]:
        payload = await self._get(
            "/v5/market/open-interest",
            {
                "category": "linear",
                "symbol": linear_symbol,
                "intervalTime": interval_time,
                "limit": limit,
            },
        )
        rows = _result_dict(payload).get("list", [])
        values = [_to_float(row.get("openInterest")) for row in rows if isinstance(row, dict)]
        return list(reversed(values))

    async def get_market_snapshot(
        self,
        symbol: str,
        *,
        kline_interval: str = "1",
        kline_limit: int = 240,
        orderbook_limit: int = 50,
        recent_trades_limit: int = 60,
        include_derivatives_context: bool = True,
    ) -> MarketSnapshot:
        candles = await self.get_klines(symbol, interval=kline_interval, limit=kline_limit)
        orderbook = await self.get_orderbook(symbol, limit=orderbook_limit)
        trades = await self.get_recent_trades(symbol, limit=recent_trades_limit)
        derivatives = DerivativesContext()
        if include_derivatives_context:
            try:
                derivatives = DerivativesContext(
                    funding_rates=await self.get_funding_rates(symbol),
                    open_interest_values=await self.get_open_interest_values(symbol),
                )
            except (BybitApiError, httpx.HTTPError):
                # Derivatives context is non-critical for spot signalling.
                derivatives = DerivativesContext()
        return MarketSnapshot(
            symbol=symbol,
            ts=datetime.now(UTC),
            candles=candles,
            orderbook=orderbook,
            trades=trades,
            derivatives=derivatives,
        )

    async def query_api_key_info(self) -> dict[str, Any]:
        payload = await self._get("/v5/user/query-api", signed=True)
        return _result_dict(payload)

    async def assert_read_only_key(self, *, allow_read_write_key: bool = False) -> dict[str, Any]:
        info = await self.query_api_key_info()
        read_only_value = info.get("readOnly")
        is_read_only = read_only_value in (1, "1", True, "true", "True")
        if not is_read_only and not allow_read_write_key:
            raise BybitApiError(
                "The configured Bybit API key is not read-only. Refusing to run account sync."
            )
        return info

    async def get_wallet_balance(
        self,
        *,
        account_type: str = "UNIFIED",
        coins: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        coin_param = ",".join(coins) if coins else None
        payload = await self._get(
            "/v5/account/wallet-balance",
            {"accountType": account_type, "coin": coin_param},
            signed=True,
        )
        return _result_dict(payload)

    async def get_open_orders(
        self,
        symbol: str | None = None,
        *,
        category: str = "spot",
    ) -> dict[str, Any]:
        payload = await self._get(
            "/v5/order/realtime",
            {"category": category, "symbol": symbol},
            signed=True,
        )
        return _result_dict(payload)

    async def get_trade_history(
        self,
        symbol: str | None = None,
        *,
        category: str = "spot",
        limit: int = 50,
    ) -> dict[str, Any]:
        payload = await self._get(
            "/v5/execution/list",
            {"category": category, "symbol": symbol, "limit": limit},
            signed=True,
        )
        return _result_dict(payload)

    @staticmethod
    def _parse_instrument_spec(
        row: dict[str, Any],
        *,
        category: str,
        requested_symbol: str,
    ) -> InstrumentSpec:
        raw_lot = row.get("lotSizeFilter")
        raw_price_filter = row.get("priceFilter")
        lot: dict[str, Any] = raw_lot if isinstance(raw_lot, dict) else {}
        price_filter: dict[str, Any] = (
            raw_price_filter if isinstance(raw_price_filter, dict) else {}
        )
        base_precision = _to_float(lot.get("basePrecision"), 0.0) or None
        quote_precision = _to_float(lot.get("quotePrecision"), 0.0) or None
        qty_step = _to_float(lot.get("qtyStep"), 0.0) or base_precision or 0.000001
        min_order_amount = (
            _to_float(lot.get("minOrderAmt"), 0.0)
            or _to_float(lot.get("minNotionalValue"), 0.0)
            or None
        )
        max_limit_order_qty = (
            _to_float(lot.get("maxLimitOrderQty"), 0.0)
            or _to_float(lot.get("maxOrderQty"), 0.0)
            or None
        )
        max_market_order_qty = (
            _to_float(lot.get("maxMarketOrderQty"), 0.0)
            or _to_float(lot.get("maxMktOrderQty"), 0.0)
            or None
        )
        return InstrumentSpec(
            symbol=str(row.get("symbol") or requested_symbol).upper(),
            category=category,
            status=str(row.get("status") or ""),
            base_coin=str(row.get("baseCoin") or "") or None,
            quote_coin=str(row.get("quoteCoin") or "") or None,
            price_tick_size=_to_float(price_filter.get("tickSize"), 0.01) or 0.01,
            qty_step=qty_step,
            min_order_qty=_to_float(lot.get("minOrderQty"), 0.0) or None,
            min_order_amount_quote=min_order_amount,
            max_limit_order_qty=max_limit_order_qty,
            max_market_order_qty=max_market_order_qty,
            base_precision=base_precision,
            quote_precision=quote_precision,
            raw=row,
        )

    @staticmethod
    def _parse_levels(raw_levels: object) -> list[OrderBookLevel]:
        if not isinstance(raw_levels, list):
            return []
        levels: list[OrderBookLevel] = []
        for row in raw_levels:
            if isinstance(row, list) and len(row) >= 2:
                levels.append(OrderBookLevel(price=_to_float(row[0]), qty=_to_float(row[1])))
        return levels
