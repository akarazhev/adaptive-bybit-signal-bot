from __future__ import annotations

from functools import lru_cache
from typing import Annotated

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

    symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    poll_interval_seconds: int = 10
    kline_interval: str = "1"
    kline_limit: int = 240
    orderbook_limit: int = 50
    recent_trades_limit: int = 60

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

    paper_trading_enabled: bool = False
    paper_fill_mode: Annotated[str, Field(pattern="^(trade_through|touch)$")] = "trade_through"
    paper_min_fill_ratio: float = 1.0
    paper_max_trade_age_seconds: int = 300

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
