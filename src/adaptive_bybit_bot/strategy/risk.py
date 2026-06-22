from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    order_quote_usdt: float = 50.0
    max_position_quote_usdt: float = 250.0
    spot_maker_fee_bps: float = 10.0
    spot_taker_fee_bps: float = 10.0
    min_net_profit_bps: float = 12.0
    safety_buffer_bps: float = 5.0
    max_spread_bps: float = 8.0
    max_atr_pct: float = 1.4
    shock_atr_pct: float = 1.2
    max_unrealized_loss_bps: float = 80.0
    max_position_age_seconds: int = 7200
    order_ttl_seconds: int = 120
    reprice_threshold_bps: float = 4.0
    min_expected_edge_bps: float = 30.0

    @property
    def maker_roundtrip_break_even_bps(self) -> float:
        buy_fee = self.spot_maker_fee_bps / 10_000
        sell_fee = self.spot_maker_fee_bps / 10_000
        return (1 / ((1 - buy_fee) * (1 - sell_fee)) - 1) * 10_000

    @property
    def required_buy_edge_bps(self) -> float:
        return max(
            self.min_expected_edge_bps,
            self.maker_roundtrip_break_even_bps
            + self.min_net_profit_bps
            + self.safety_buffer_bps,
        )

    @property
    def target_sell_profit_bps(self) -> float:
        return (
            self.maker_roundtrip_break_even_bps
            + self.min_net_profit_bps
            + self.safety_buffer_bps
        )
