from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class MarketFeatureRecord(Base):
    __tablename__ = "market_features"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    feature_set_version: Mapped[str] = mapped_column(String(32), default="v1")
    features_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class MarketRegimeRecord(Base):
    __tablename__ = "market_regimes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    regime: Mapped[str] = mapped_column(String(64), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    explanation_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class BacktestRunRecord(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(16), index=True)
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    candle_count: Mapped[int] = mapped_column(Integer, default=0)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class BacktestFillRecord(Base):
    __tablename__ = "backtest_fills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(16), index=True)
    price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    fee_quote: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl_quote: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class InstrumentSpecRecord(Base):
    __tablename__ = "instrument_specs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(32), default="spot", index=True)
    status: Mapped[str] = mapped_column(String(32), default="")
    base_coin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quote_coin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    price_tick_size: Mapped[float] = mapped_column(Float, default=0.01)
    qty_step: Mapped[float] = mapped_column(Float, default=0.000001)
    min_order_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_order_amount_quote: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_limit_order_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_market_order_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SignalRecord(Base):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    side: Mapped[str | None] = mapped_column(String(16), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    expected_edge_bps: Mapped[float] = mapped_column(Float, default=0.0)
    regime: Mapped[str] = mapped_column(String(64), index=True)
    reason_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    strategy_version: Mapped[str] = mapped_column(String(32), default="v1")

    intents: Mapped[list[OrderIntentRecord]] = relationship(back_populates="signal")


class OrderIntentRecord(Base):
    __tablename__ = "order_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    signal_id: Mapped[str | None] = mapped_column(
        ForeignKey("signals.id"),
        nullable=True,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(16), index=True)
    limit_price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    replaced_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fill_qty: Mapped[float | None] = mapped_column(Float, nullable=True)

    signal: Mapped[SignalRecord | None] = relationship(back_populates="intents")
    events: Mapped[list[OrderEventRecord]] = relationship(back_populates="intent")


class OrderEventRecord(Base):
    __tablename__ = "order_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_intent_id: Mapped[str] = mapped_column(ForeignKey("order_intents.id"), index=True)
    signal_id: Mapped[str | None] = mapped_column(
        ForeignKey("signals.id"),
        nullable=True,
        index=True,
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    old_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    intent: Mapped[OrderIntentRecord] = relationship(back_populates="events")


class PaperFillRecord(Base):
    __tablename__ = "paper_fills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    order_intent_id: Mapped[str] = mapped_column(ForeignKey("order_intents.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(16), index=True)
    fill_price: Mapped[float] = mapped_column(Float)
    fill_qty: Mapped[float] = mapped_column(Float)
    reason_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PositionRecord(Base):
    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    avg_entry: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), index=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)


class AccountSnapshotRecord(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class ExecutionRecord(Base):
    __tablename__ = "executions"
    __table_args__ = (UniqueConstraint("exec_id", name="uq_executions_exec_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exec_id: Mapped[str] = mapped_column(String(128), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(16), index=True)
    price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    fee_currency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
