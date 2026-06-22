from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from adaptive_bybit_bot.data.models import Base


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    raw_path = database_url.replace("sqlite:///", "", 1)
    if raw_path == ":memory:":
        return
    Path(raw_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def create_database_engine(database_url: str) -> Engine:
    _ensure_sqlite_parent(database_url)
    kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **kwargs)


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def wait_for_database(
    database_url: str,
    *,
    timeout_seconds: int = 60,
    interval_seconds: float = 2.0,
    create: bool = True,
) -> Engine:
    """Return an engine after the database accepts connections.

    Podman Compose providers differ in how much of advanced ``depends_on``
    semantics they support. This retry loop makes each service resilient even
    when it starts before PostgreSQL is ready.
    """
    deadline = time.monotonic() + max(timeout_seconds, 0)
    last_error: Exception | None = None
    while True:
        engine = create_database_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(text("SELECT 1"))
            if create:
                create_schema(engine)
            return engine
        except SQLAlchemyError as exc:
            last_error = exc
            engine.dispose()
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"database is not ready after {timeout_seconds}s"
                ) from last_error
            time.sleep(max(interval_seconds, 0.1))


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
