from __future__ import annotations

from pathlib import Path

from sqlalchemy.pool import NullPool

from adaptive_bybit_bot.data.db import create_database_engine


def test_sqlite_engine_uses_null_pool_to_release_connections(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path}/bot.db")

    try:
        assert isinstance(engine.pool, NullPool)
    finally:
        engine.dispose()
