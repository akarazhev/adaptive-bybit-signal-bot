from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from uuid import uuid4

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bybit_base_url: str = "https://api.bybit.com"
    bybit_public_ws_spot_url: str = "wss://stream.bybit.com/v5/public/spot"
    bybit_api_key: str | None = None
    bybit_api_secret: str | None = None
    bybit_recv_window: int = 5000
    bybit_allow_read_write_key: bool = False

    database_url: str = "sqlite:///data/bot.db"
    db_wait_timeout_seconds: int = 60
    db_wait_interval_seconds: float = 2.0

    app_env: str = "local"
    service_instance_id: str = Field(default_factory=lambda: str(uuid4()))
    service_heartbeat_seconds: int = 15
    service_heartbeat_stale_seconds: int = 120
    strategy_lock_enabled: bool = True
    strategy_lock_ttl_seconds: int = 60
    # "any" preserves standalone CLI behaviour. In compose, set this to
    # "ws-shadow" to make only that service write strategy signals/intents.
    strategy_writer_service: str = "any"

    symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    poll_interval_seconds: int = 10
    kline_interval: str = "1"
    kline_limit: int = 240
    orderbook_limit: int = 50
    recent_trades_limit: int = 60

    ws_orderbook_depth: int = 50
    ws_evaluation_interval_seconds: int = 10
    ws_candle_refresh_seconds: int = 30
    ws_trade_lookback_seconds: int = 120
    ws_max_trades_per_symbol: int = 2000

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

    fng_enabled: bool = False
    fng_base_url: str = "https://api.alternative.me"
    fng_refresh_seconds: int = 21_600
    fng_stale_after_hours: float = 36.0
    fng_history_limit: int = 30
    fng_btc_weight: float = 1.0
    fng_eth_weight: float = 0.6
    fng_alt_weight: float = 0.5
    fng_extreme_fear_size_multiplier: float = 0.5
    fng_fear_size_multiplier: float = 0.8
    fng_greed_size_multiplier: float = 0.6
    fng_extreme_greed_size_multiplier: float = 0.4
    fng_extreme_fear_extra_edge_bps: float = 5.0
    fng_greed_extra_edge_bps: float = 8.0
    fng_extreme_greed_extra_edge_bps: float = 15.0
    fng_extreme_fear_buy_distance_multiplier: float = 1.25
    fng_fear_buy_distance_multiplier: float = 1.10
    fng_greed_buy_distance_multiplier: float = 1.25
    fng_extreme_greed_buy_distance_multiplier: float = 1.50
    fng_greed_ttl_multiplier: float = 0.75
    fng_extreme_greed_ttl_multiplier: float = 0.50
    fng_greed_sell_target_multiplier: float = 0.92
    fng_extreme_greed_sell_target_multiplier: float = 0.85

    instrument_refresh_seconds: int = 43_200

    paper_trading_enabled: bool = False
    paper_fill_mode: Annotated[str, Field(pattern="^(trade_through|touch)$")] = "trade_through"
    paper_min_fill_ratio: float = 1.0
    paper_max_trade_age_seconds: int = 300
    paper_loop_interval_seconds: int = 10

    backtest_starting_quote: float = 10_000.0
    backtest_warmup_candles: int = 240
    backtest_synthetic_spread_bps: float = 2.0
    backtest_force_close: bool = True

    # High-volume market recordings are file-backed; DB stores only metadata.
    market_recording_dir: str = "/data/market-recordings"
    market_recording_orderbook_depth: int = 50
    market_recording_compress: bool = True
    market_recording_flush_every_events: int = 1_000

    # Replay settings for recorded public WS data.
    replay_interval_seconds: int = 60
    replay_evaluation_interval_seconds: int = 10
    replay_warmup_candles: int = 60
    replay_trade_lookback_seconds: int = 120
    replay_fill_model: Annotated[str, Field(pattern="^(trade_through|touch)$")] = "trade_through"
    replay_force_close: bool = True

    log_level: Annotated[str, Field(pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")] = "INFO"

    @field_validator("symbols", mode="before")
    @classmethod
    def parse_symbols(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [item.strip().upper() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip().upper() for item in value]
        raise TypeError("symbols must be a comma-separated string or list")

    @property
    def has_bybit_credentials(self) -> bool:
        return bool(self.bybit_api_key and self.bybit_api_secret)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
