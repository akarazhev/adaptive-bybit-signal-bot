from __future__ import annotations

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.strategy.risk import RiskConfig


def risk_config_from_settings(settings: Settings) -> RiskConfig:
    return RiskConfig(
        order_quote_usdt=settings.order_quote_usdt,
        max_position_quote_usdt=settings.max_position_quote_usdt,
        spot_maker_fee_bps=settings.spot_maker_fee_bps,
        spot_taker_fee_bps=settings.spot_taker_fee_bps,
        min_net_profit_bps=settings.min_net_profit_bps,
        safety_buffer_bps=settings.safety_buffer_bps,
        max_spread_bps=settings.max_spread_bps,
        max_atr_pct=settings.max_atr_pct,
        shock_atr_pct=settings.shock_atr_pct,
        max_unrealized_loss_bps=settings.max_unrealized_loss_bps,
        max_position_age_seconds=settings.max_position_age_seconds,
        order_ttl_seconds=settings.order_ttl_seconds,
        reprice_threshold_bps=settings.reprice_threshold_bps,
        min_expected_edge_bps=settings.min_expected_edge_bps,
    )
