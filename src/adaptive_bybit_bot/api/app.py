from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from adaptive_bybit_bot.config import Settings, get_settings
from adaptive_bybit_bot.data.db import wait_for_database
from adaptive_bybit_bot.data.repositories import BotRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = wait_for_database(
        settings.database_url,
        timeout_seconds=settings.db_wait_timeout_seconds,
        interval_seconds=settings.db_wait_interval_seconds,
        create=True,
    )
    repository = BotRepository(engine)

    app = FastAPI(
        title="Adaptive Bybit Signal Bot",
        version="0.5.0",
        description="Read-only/order-intent API. No trading endpoint is implemented.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/intents")
    def intents(limit: int = 50) -> list[dict[str, Any]]:
        return repository.list_recent_intents(limit=limit)

    @app.get("/signals")
    def signals(limit: int = 50) -> list[dict[str, Any]]:
        return repository.list_recent_signals(limit=limit)

    @app.get("/paper-fills")
    def paper_fills(limit: int = 50) -> list[dict[str, Any]]:
        return repository.list_recent_paper_fills(limit=limit)

    @app.get("/positions")
    def positions(limit: int = 50) -> list[dict[str, Any]]:
        return repository.list_positions(limit=limit)

    @app.get("/instruments")
    def instruments(limit: int = 100) -> list[dict[str, Any]]:
        return repository.list_instrument_specs(limit=limit)

    @app.get("/services")
    def services(limit: int = 50) -> list[dict[str, Any]]:
        return repository.list_service_heartbeats(limit=limit)

    @app.get("/locks")
    def locks(limit: int = 50) -> list[dict[str, Any]]:
        return repository.list_strategy_locks(limit=limit)

    @app.get("/sentiment/fng")
    def sentiment_fng(limit: int = 30) -> dict[str, Any]:
        return {
            "attribution": "Fear & Greed Index data source: Alternative.me",
            "data": repository.list_fear_greed_values(limit=limit),
        }

    @app.get("/backtests")
    def backtests(limit: int = 20) -> list[dict[str, Any]]:
        return repository.list_backtests(limit=limit)

    @app.get("/backtest-fills")
    def backtest_fills(run_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return repository.list_backtest_fills(run_id=run_id, limit=limit)

    return app
