from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from adaptive_bybit_bot.config import Settings, get_settings
from adaptive_bybit_bot.data.db import create_database_engine, create_schema
from adaptive_bybit_bot.data.repositories import BotRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = create_database_engine(settings.database_url)
    create_schema(engine)
    repository = BotRepository(engine)

    app = FastAPI(
        title="Adaptive Bybit Signal Bot",
        version="0.2.0",
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

    return app
