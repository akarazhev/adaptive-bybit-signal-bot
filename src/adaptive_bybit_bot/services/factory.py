from __future__ import annotations

from adaptive_bybit_bot.config import Settings
from adaptive_bybit_bot.sentiment.policy import FearGreedPolicyConfig, FearGreedSentimentPolicy
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


def fear_greed_policy_config_from_settings(settings: Settings) -> FearGreedPolicyConfig:
    return FearGreedPolicyConfig(
        enabled=settings.fng_enabled,
        stale_after_hours=settings.fng_stale_after_hours,
        btc_weight=settings.fng_btc_weight,
        eth_weight=settings.fng_eth_weight,
        alt_weight=settings.fng_alt_weight,
        extreme_fear_size_multiplier=settings.fng_extreme_fear_size_multiplier,
        fear_size_multiplier=settings.fng_fear_size_multiplier,
        greed_size_multiplier=settings.fng_greed_size_multiplier,
        extreme_greed_size_multiplier=settings.fng_extreme_greed_size_multiplier,
        extreme_fear_extra_edge_bps=settings.fng_extreme_fear_extra_edge_bps,
        greed_extra_edge_bps=settings.fng_greed_extra_edge_bps,
        extreme_greed_extra_edge_bps=settings.fng_extreme_greed_extra_edge_bps,
        extreme_fear_buy_distance_multiplier=settings.fng_extreme_fear_buy_distance_multiplier,
        fear_buy_distance_multiplier=settings.fng_fear_buy_distance_multiplier,
        greed_buy_distance_multiplier=settings.fng_greed_buy_distance_multiplier,
        extreme_greed_buy_distance_multiplier=settings.fng_extreme_greed_buy_distance_multiplier,
        greed_ttl_multiplier=settings.fng_greed_ttl_multiplier,
        extreme_greed_ttl_multiplier=settings.fng_extreme_greed_ttl_multiplier,
        greed_sell_target_multiplier=settings.fng_greed_sell_target_multiplier,
        extreme_greed_sell_target_multiplier=settings.fng_extreme_greed_sell_target_multiplier,
    )


def fear_greed_policy_from_settings(settings: Settings) -> FearGreedSentimentPolicy:
    return FearGreedSentimentPolicy(fear_greed_policy_config_from_settings(settings))
