from __future__ import annotations

from adaptive_bybit_bot.domain.enums import Side
from adaptive_bybit_bot.domain.models import FeatureSet, MarketSnapshot, OrderBook, Trade
from adaptive_bybit_bot.features.indicators import atr, ema, ema_series, rsi, vwap, zscore


class FeatureEngine:
    """Transforms raw market snapshots into compact strategy features."""

    def build(self, snapshot: MarketSnapshot) -> FeatureSet:
        if not snapshot.candles:
            raise ValueError("snapshot must contain candles")
        last_price = snapshot.candles[-1].close
        mid_price = snapshot.orderbook.mid or last_price
        spread_bps = self._spread_bps(snapshot.orderbook, mid_price)
        closes = [candle.close for candle in snapshot.candles]
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        ema200 = ema(closes, 200)
        ema20_slope = self._ema_slope_bps(closes, 20)
        atr_value = atr(snapshot.candles, 14)
        atr_pct = (atr_value / last_price * 100) if atr_value and last_price > 0 else None
        vwap_value = vwap(snapshot.candles, 50)
        vwap_dev = ((last_price / vwap_value - 1) * 10_000) if vwap_value else None
        return FeatureSet(
            symbol=snapshot.symbol,
            ts=snapshot.ts,
            last_price=last_price,
            mid_price=mid_price,
            best_bid=snapshot.orderbook.best_bid,
            best_ask=snapshot.orderbook.best_ask,
            spread_bps=spread_bps,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            ema20_slope_bps=ema20_slope,
            atr_pct=atr_pct,
            rsi14=rsi(closes, 14),
            vwap=vwap_value,
            vwap_deviation_bps=vwap_dev,
            orderbook_imbalance=self._orderbook_imbalance(
                snapshot.orderbook, mid_price, window_bps=10
            ),
            microprice=self._microprice(snapshot.orderbook),
            trade_imbalance=self._trade_imbalance(snapshot.trades),
            funding_rate=snapshot.derivatives.funding_rates[-1]
            if snapshot.derivatives.funding_rates
            else None,
            funding_zscore=zscore(snapshot.derivatives.funding_rates),
            open_interest_change_pct=self._oi_change_pct(snapshot.derivatives.open_interest_values),
        )

    @staticmethod
    def _spread_bps(orderbook: OrderBook, fallback_mid: float) -> float:
        if orderbook.best_bid is None or orderbook.best_ask is None or fallback_mid <= 0:
            return 10_000.0
        return (orderbook.best_ask - orderbook.best_bid) / fallback_mid * 10_000

    @staticmethod
    def _ema_slope_bps(closes: list[float], period: int) -> float | None:
        series = ema_series(closes, period)
        if len(series) < 6 or series[-6] == 0:
            return None
        return (series[-1] / series[-6] - 1) * 10_000

    @staticmethod
    def _orderbook_imbalance(
        orderbook: OrderBook, mid_price: float, window_bps: float
    ) -> float | None:
        if mid_price <= 0:
            return None
        low = mid_price * (1 - window_bps / 10_000)
        high = mid_price * (1 + window_bps / 10_000)
        bid_qty = sum(level.qty for level in orderbook.bids if low <= level.price <= mid_price)
        ask_qty = sum(level.qty for level in orderbook.asks if mid_price <= level.price <= high)
        total = bid_qty + ask_qty
        if total <= 0:
            return None
        return (bid_qty - ask_qty) / total

    @staticmethod
    def _microprice(orderbook: OrderBook) -> float | None:
        if not orderbook.bids or not orderbook.asks:
            return None
        bid = orderbook.bids[0]
        ask = orderbook.asks[0]
        total_qty = bid.qty + ask.qty
        if total_qty <= 0:
            return None
        return (ask.price * bid.qty + bid.price * ask.qty) / total_qty

    @staticmethod
    def _trade_imbalance(trades: list[Trade]) -> float | None:
        buy_qty = sum(trade.qty for trade in trades if trade.side == Side.BUY)
        sell_qty = sum(trade.qty for trade in trades if trade.side == Side.SELL)
        total = buy_qty + sell_qty
        if total <= 0:
            return None
        return (buy_qty - sell_qty) / total

    @staticmethod
    def _oi_change_pct(values: list[float]) -> float | None:
        if len(values) < 2 or values[0] <= 0:
            return None
        return (values[-1] / values[0] - 1) * 100
