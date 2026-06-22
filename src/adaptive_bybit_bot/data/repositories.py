from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, Select, desc, select
from sqlalchemy.orm import Session

from adaptive_bybit_bot.data.db import create_schema, session_scope
from adaptive_bybit_bot.data.models import (
    AccountSnapshotRecord,
    BacktestFillRecord,
    BacktestRunRecord,
    ExecutionRecord,
    FearGreedIndexRecord,
    InstrumentSpecRecord,
    MarketFeatureRecord,
    MarketRegimeRecord,
    OrderEventRecord,
    OrderIntentRecord,
    PaperFillRecord,
    PositionRecord,
    SignalRecord,
)
from adaptive_bybit_bot.domain.enums import OrderIntentStatus, PositionStatus, Side, SignalAction
from adaptive_bybit_bot.domain.models import (
    FearGreedContext,
    FearGreedValue,
    FeatureSet,
    InstrumentSpec,
    PositionState,
    SignalDecision,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "value", str(value))


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


class BotRepository:
    """Repository layer for features, signals, order intents, instruments and positions."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create_schema(self) -> None:
        create_schema(self.engine)

    def save_instrument_spec(self, spec: InstrumentSpec) -> str:
        with session_scope(self.engine) as session:
            record = InstrumentSpecRecord(
                symbol=spec.symbol,
                category=spec.category,
                status=spec.status,
                base_coin=spec.base_coin,
                quote_coin=spec.quote_coin,
                price_tick_size=spec.price_tick_size,
                qty_step=spec.qty_step,
                min_order_qty=spec.min_order_qty,
                min_order_amount_quote=spec.min_order_amount_quote,
                max_limit_order_qty=spec.max_limit_order_qty,
                max_market_order_qty=spec.max_market_order_qty,
                base_precision=spec.base_precision,
                quote_precision=spec.quote_precision,
                raw_json=_json_safe(spec.raw),
            )
            session.add(record)
            session.flush()
            return record.id

    def get_latest_instrument_spec(
        self,
        symbol: str,
        *,
        category: str = "spot",
    ) -> InstrumentSpec | None:
        with session_scope(self.engine) as session:
            record = session.execute(
                select(InstrumentSpecRecord)
                .where(
                    InstrumentSpecRecord.symbol == symbol.upper(),
                    InstrumentSpecRecord.category == category,
                )
                .order_by(desc(InstrumentSpecRecord.ts))
                .limit(1)
            ).scalars().first()
            if record is None:
                return None
            return _instrument_spec_from_record(record)

    def list_recent_instrument_specs(self, limit: int = 20) -> list[dict[str, Any]]:
        with session_scope(self.engine) as session:
            rows = session.execute(
                select(InstrumentSpecRecord).order_by(desc(InstrumentSpecRecord.ts)).limit(limit)
            ).scalars().all()
            return [_instrument_spec_record_to_dict(row) for row in rows]

    def list_instrument_specs(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.list_recent_instrument_specs(limit=limit)

    def save_fear_greed_value(self, value: FearGreedValue) -> str:
        """Upsert a Fear & Greed observation by source/timestamp."""
        with session_scope(self.engine) as session:
            existing = session.execute(
                select(FearGreedIndexRecord)
                .where(
                    FearGreedIndexRecord.source == value.source,
                    FearGreedIndexRecord.timestamp == value.timestamp,
                )
                .limit(1)
            ).scalars().first()
            if existing is not None:
                existing.value = value.value
                existing.classification = value.classification
                existing.time_until_update_seconds = value.time_until_update_seconds
                existing.fetched_at = value.fetched_at
                existing.raw_json = _json_safe(value.raw)
                return existing.id
            record = FearGreedIndexRecord(
                source=value.source,
                value=value.value,
                classification=value.classification,
                timestamp=value.timestamp,
                time_until_update_seconds=value.time_until_update_seconds,
                fetched_at=value.fetched_at,
                raw_json=_json_safe(value.raw),
            )
            session.add(record)
            session.flush()
            return record.id

    def save_fear_greed_values(self, values: list[FearGreedValue]) -> int:
        count = 0
        for value in values:
            self.save_fear_greed_value(value)
            count += 1
        return count

    def get_latest_fear_greed_value(
        self,
        *,
        source: str = "alternative.me",
    ) -> FearGreedValue | None:
        with session_scope(self.engine) as session:
            row = session.execute(
                select(FearGreedIndexRecord)
                .where(FearGreedIndexRecord.source == source)
                .order_by(desc(FearGreedIndexRecord.timestamp))
                .limit(1)
            ).scalars().first()
            return _fear_greed_from_record(row) if row else None

    def get_fear_greed_context(
        self,
        *,
        source: str = "alternative.me",
        limit: int = 30,
    ) -> FearGreedContext | None:
        values = self.get_fear_greed_values(source=source, limit=limit)
        return FearGreedContext.from_values(values)

    def get_fear_greed_at(
        self,
        ts: datetime,
        *,
        source: str = "alternative.me",
        history_limit: int = 8,
    ) -> FearGreedContext | None:
        """Return the latest FNG context known at or before a timestamp."""
        with session_scope(self.engine) as session:
            rows = session.execute(
                select(FearGreedIndexRecord)
                .where(
                    FearGreedIndexRecord.source == source,
                    FearGreedIndexRecord.timestamp <= ts,
                )
                .order_by(desc(FearGreedIndexRecord.timestamp))
                .limit(max(history_limit, 1))
            ).scalars().all()
            return FearGreedContext.from_values([_fear_greed_from_record(row) for row in rows])

    def get_fear_greed_values(
        self,
        *,
        source: str = "alternative.me",
        limit: int = 30,
    ) -> list[FearGreedValue]:
        with session_scope(self.engine) as session:
            rows = session.execute(
                select(FearGreedIndexRecord)
                .where(FearGreedIndexRecord.source == source)
                .order_by(desc(FearGreedIndexRecord.timestamp))
                .limit(limit)
            ).scalars().all()
            return [_fear_greed_from_record(row) for row in rows]

    def list_fear_greed_values(self, limit: int = 30) -> list[dict[str, Any]]:
        with session_scope(self.engine) as session:
            rows = session.execute(
                select(FearGreedIndexRecord)
                .order_by(desc(FearGreedIndexRecord.timestamp))
                .limit(limit)
            ).scalars().all()
            return [_fear_greed_record_to_dict(row) for row in rows]

    def save_backtest_result(self, result: Any) -> str:
        """Persist a backtest summary and fill rows.

        The repository accepts the current candle-level BacktestResult shape and stays
        tolerant to older result objects used during development.
        """
        summary = result.summary_dict() if hasattr(result, "summary_dict") else result.as_dict()
        config = getattr(result, "config", None)
        config_json = config.as_dict() if config is not None and hasattr(config, "as_dict") else {}
        with session_scope(self.engine) as session:
            run = BacktestRunRecord(
                symbol=result.symbol,
                interval=getattr(result, "interval", summary.get("interval", "1")),
                start_ts=getattr(result, "start_ts", result.started_at),
                end_ts=getattr(result, "end_ts", result.finished_at),
                candle_count=getattr(result, "candle_count", getattr(result, "candles", 0)),
                config_json=_json_safe(config_json),
                summary_json=_json_safe(summary),
            )
            session.add(run)
            session.flush()
            for fill in getattr(result, "fills", []):
                side = getattr(fill, "side", None)
                side_value = getattr(side, "value", side)
                session.add(
                    BacktestFillRecord(
                        run_id=run.id,
                        ts=fill.ts,
                        symbol=fill.symbol,
                        side=str(side_value),
                        price=fill.price,
                        qty=fill.qty,
                        fee_quote=fill.fee_quote,
                        realized_pnl_quote=getattr(
                            fill,
                            "realized_pnl_quote",
                            getattr(fill, "pnl_quote", None),
                        ),
                        reason_json={
                            "reason": getattr(fill, "reason", ""),
                            "intent_id": getattr(fill, "intent_id", ""),
                        },
                    )
                )
            return run.id

    def list_backtests(self, limit: int = 20) -> list[dict[str, Any]]:
        with session_scope(self.engine) as session:
            rows = session.execute(
                select(BacktestRunRecord).order_by(desc(BacktestRunRecord.ts)).limit(limit)
            ).scalars().all()
            return [
                {
                    "id": row.id,
                    "ts": row.ts.isoformat() if row.ts else None,
                    "symbol": row.symbol,
                    "interval": row.interval,
                    "start_ts": row.start_ts.isoformat() if row.start_ts else None,
                    "end_ts": row.end_ts.isoformat() if row.end_ts else None,
                    "candle_count": row.candle_count,
                    "summary": row.summary_json,
                }
                for row in rows
            ]

    def list_backtest_fills(
        self,
        *,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with session_scope(self.engine) as session:
            stmt = select(BacktestFillRecord)
            if run_id:
                stmt = stmt.where(BacktestFillRecord.run_id == run_id)
            rows = (
                session.execute(stmt.order_by(desc(BacktestFillRecord.ts)).limit(limit))
                .scalars()
                .all()
            )
            return [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "ts": row.ts.isoformat() if row.ts else None,
                    "symbol": row.symbol,
                    "side": row.side,
                    "price": row.price,
                    "qty": row.qty,
                    "fee_quote": row.fee_quote,
                    "realized_pnl_quote": row.realized_pnl_quote,
                    "reason": row.reason_json,
                }
                for row in rows
            ]

    def save_feature_set(self, features: FeatureSet, *, version: str = "v1") -> str:
        with session_scope(self.engine) as session:
            record = MarketFeatureRecord(
                ts=features.ts,
                symbol=features.symbol,
                feature_set_version=version,
                features_json=_json_safe(features.as_dict()),
            )
            session.add(record)
            session.flush()
            return record.id

    def save_regime(
        self,
        *,
        symbol: str,
        regime: str,
        confidence: float,
        explanation: dict[str, Any],
        ts: datetime | None = None,
    ) -> str:
        with session_scope(self.engine) as session:
            record = MarketRegimeRecord(
                ts=ts or _now(),
                symbol=symbol,
                regime=regime,
                confidence=confidence,
                explanation_json=_json_safe(explanation),
            )
            session.add(record)
            session.flush()
            return record.id

    def save_signal(self, decision: SignalDecision, *, strategy_version: str = "v1") -> str:
        with session_scope(self.engine) as session:
            self._insert_signal(session, decision, strategy_version=strategy_version)
            return decision.id

    def apply_signal(self, decision: SignalDecision, *, strategy_version: str = "v1") -> str | None:
        """Persist a decision and mutate local intent state.

        Returns the affected or created order_intent id for actionable decisions, else None.
        """
        with session_scope(self.engine) as session:
            self._insert_signal(session, decision, strategy_version=strategy_version)

            if decision.action in {SignalAction.BUY_INTENT, SignalAction.SELL_INTENT}:
                if decision.side is None or decision.price is None or decision.qty is None:
                    raise ValueError("actionable signal must include side, price and qty")
                expires_at = (
                    decision.ts + timedelta(seconds=decision.ttl_seconds)
                    if decision.ttl_seconds
                    else None
                )
                intent = OrderIntentRecord(
                    signal_id=decision.id,
                    symbol=decision.symbol,
                    side=decision.side.value,
                    limit_price=decision.price,
                    qty=decision.qty,
                    status=OrderIntentStatus.ACTIVE.value,
                    created_at=decision.ts,
                    expires_at=expires_at,
                )
                session.add(intent)
                session.flush()
                session.add(
                    OrderEventRecord(
                        order_intent_id=intent.id,
                        signal_id=decision.id,
                        event_type="CREATED",
                        new_price=decision.price,
                        reason_json={
                            "reason": decision.reason,
                            "metadata": _json_safe(decision.metadata),
                        },
                    )
                )
                return intent.id

            if decision.action == SignalAction.REPRICE_INTENT:
                if (
                    decision.replaces_intent_id is None
                    or decision.side is None
                    or decision.price is None
                    or decision.qty is None
                ):
                    raise ValueError("reprice signal must include old intent, side, price and qty")
                old_intent = session.get(OrderIntentRecord, decision.replaces_intent_id)
                if old_intent is None:
                    raise ValueError(f"order intent not found: {decision.replaces_intent_id}")
                old_price = old_intent.limit_price
                old_intent.status = OrderIntentStatus.REPLACED.value
                expires_at = (
                    decision.ts + timedelta(seconds=decision.ttl_seconds)
                    if decision.ttl_seconds
                    else None
                )
                new_intent = OrderIntentRecord(
                    signal_id=decision.id,
                    symbol=decision.symbol,
                    side=decision.side.value,
                    limit_price=decision.price,
                    qty=decision.qty,
                    status=OrderIntentStatus.ACTIVE.value,
                    created_at=decision.ts,
                    expires_at=expires_at,
                )
                session.add(new_intent)
                session.flush()
                old_intent.replaced_by_id = new_intent.id
                session.add(
                    OrderEventRecord(
                        order_intent_id=old_intent.id,
                        signal_id=decision.id,
                        event_type="REPLACED",
                        old_price=old_price,
                        new_price=decision.price,
                        reason_json={"reason": decision.reason, "new_intent_id": new_intent.id},
                    )
                )
                session.add(
                    OrderEventRecord(
                        order_intent_id=new_intent.id,
                        signal_id=decision.id,
                        event_type="CREATED_BY_REPRICE",
                        old_price=old_price,
                        new_price=decision.price,
                        reason_json={"reason": decision.reason, "old_intent_id": old_intent.id},
                    )
                )
                return new_intent.id

            if decision.action == SignalAction.CANCEL_INTENT:
                target_id = decision.replaces_intent_id
                if not target_id:
                    active = self._active_intent_query(decision.symbol, decision.side).limit(1)
                    target = session.execute(active).scalars().first()
                else:
                    target = session.get(OrderIntentRecord, target_id)
                if target is None:
                    return None
                target.status = OrderIntentStatus.CANCEL_REQUESTED.value
                session.add(
                    OrderEventRecord(
                        order_intent_id=target.id,
                        signal_id=decision.id,
                        event_type="CANCEL_REQUESTED",
                        old_price=target.limit_price,
                        reason_json={"reason": decision.reason},
                    )
                )
                return target.id

            return None

    def active_intent(self, symbol: str, side: Side | None = None) -> OrderIntentRecord | None:
        with session_scope(self.engine) as session:
            record = session.execute(
                self._active_intent_query(symbol, side).limit(1)
            ).scalars().first()
            if record is not None:
                session.expunge(record)
            return record

    def active_intents(self, symbol: str | None = None) -> list[OrderIntentRecord]:
        with session_scope(self.engine) as session:
            stmt = select(OrderIntentRecord).where(
                OrderIntentRecord.status == OrderIntentStatus.ACTIVE.value
            )
            if symbol:
                stmt = stmt.where(OrderIntentRecord.symbol == symbol)
            stmt = stmt.order_by(desc(OrderIntentRecord.created_at))
            records = list(session.execute(stmt).scalars().all())
            for record in records:
                session.expunge(record)
            return records

    def expire_stale_intents(self, now: datetime | None = None) -> int:
        now = now or _now()
        count = 0
        with session_scope(self.engine) as session:
            stmt = select(OrderIntentRecord).where(
                OrderIntentRecord.status == OrderIntentStatus.ACTIVE.value,
                OrderIntentRecord.expires_at.is_not(None),
                OrderIntentRecord.expires_at <= now,
            )
            for intent in session.execute(stmt).scalars().all():
                intent.status = OrderIntentStatus.EXPIRED.value
                session.add(
                    OrderEventRecord(
                        order_intent_id=intent.id,
                        event_type="EXPIRED",
                        old_price=intent.limit_price,
                        reason_json={"reason": ["ttl_expired"]},
                    )
                )
                count += 1
        return count

    def mark_intent_filled(
        self,
        intent_id: str,
        *,
        fill_price: float,
        fill_qty: float,
        filled_at: datetime | None = None,
        source: str = "manual",
        reason: dict[str, Any] | None = None,
    ) -> None:
        if fill_qty <= 0:
            raise ValueError("fill_qty must be positive")
        filled_at = filled_at or _now()
        reason = reason or {}
        with session_scope(self.engine) as session:
            intent = session.get(OrderIntentRecord, intent_id)
            if intent is None:
                raise ValueError(f"order intent not found: {intent_id}")
            applied_fill_qty = min(fill_qty, intent.qty) if source == "paper" else fill_qty
            remaining_qty = max(intent.qty - applied_fill_qty, 0.0)
            is_partial_paper_fill = source == "paper" and remaining_qty > 1e-12
            if is_partial_paper_fill:
                intent.qty = remaining_qty
            else:
                intent.status = OrderIntentStatus.FILLED.value
                intent.filled_at = filled_at
            intent.fill_price = fill_price
            intent.fill_qty = applied_fill_qty
            if source == "paper":
                event_type = "PAPER_PARTIAL_FILLED" if is_partial_paper_fill else "PAPER_FILLED"
            else:
                event_type = "FILLED_CONFIRMED"
            session.add(
                OrderEventRecord(
                    order_intent_id=intent.id,
                    event_type=event_type,
                    old_price=intent.limit_price,
                    new_price=fill_price,
                    reason_json={
                        "fill_qty": applied_fill_qty,
                        "remaining_qty": remaining_qty,
                        "source": source,
                        **_json_safe(reason),
                    },
                )
            )
            if source == "paper":
                session.add(
                    PaperFillRecord(
                        ts=filled_at,
                        order_intent_id=intent.id,
                        symbol=intent.symbol,
                        side=intent.side,
                        fill_price=fill_price,
                        fill_qty=applied_fill_qty,
                        reason_json=_json_safe(reason),
                    )
                )
            self._apply_fill_to_position(
                session,
                symbol=intent.symbol,
                side=Side(intent.side),
                price=fill_price,
                qty=applied_fill_qty,
                ts=filled_at,
            )

    def get_position_state(self, symbol: str) -> PositionState:
        with session_scope(self.engine) as session:
            record = session.execute(
                select(PositionRecord)
                .where(
                    PositionRecord.symbol == symbol,
                    PositionRecord.status == PositionStatus.OPEN.value,
                )
                .order_by(desc(PositionRecord.opened_at))
                .limit(1)
            ).scalars().first()
            if record is None:
                return PositionState(symbol=symbol)
            return PositionState(
                symbol=record.symbol,
                qty=record.qty,
                avg_entry=record.avg_entry,
                opened_at=record.opened_at,
            )

    def list_positions(self, limit: int = 20) -> list[dict[str, Any]]:
        with session_scope(self.engine) as session:
            rows = session.execute(
                select(PositionRecord).order_by(desc(PositionRecord.updated_at)).limit(limit)
            ).scalars().all()
            return [
                {
                    "id": row.id,
                    "symbol": row.symbol,
                    "qty": row.qty,
                    "avg_entry": row.avg_entry,
                    "status": row.status,
                    "opened_at": row.opened_at.isoformat() if row.opened_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    "closed_at": row.closed_at.isoformat() if row.closed_at else None,
                    "realized_pnl": row.realized_pnl,
                }
                for row in rows
            ]

    def list_recent_intents(self, limit: int = 20) -> list[dict[str, Any]]:
        with session_scope(self.engine) as session:
            rows = session.execute(
                select(OrderIntentRecord).order_by(desc(OrderIntentRecord.created_at)).limit(limit)
            ).scalars().all()
            return [
                {
                    "id": row.id,
                    "signal_id": row.signal_id,
                    "symbol": row.symbol,
                    "side": row.side,
                    "limit_price": row.limit_price,
                    "qty": row.qty,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                    "replaced_by_id": row.replaced_by_id,
                    "fill_price": row.fill_price,
                    "fill_qty": row.fill_qty,
                }
                for row in rows
            ]

    def list_recent_signals(self, limit: int = 20) -> list[dict[str, Any]]:
        with session_scope(self.engine) as session:
            rows = session.execute(
                select(SignalRecord).order_by(desc(SignalRecord.ts)).limit(limit)
            ).scalars().all()
            return [
                {
                    "id": row.id,
                    "ts": row.ts.isoformat() if row.ts else None,
                    "symbol": row.symbol,
                    "action": row.action,
                    "side": row.side,
                    "price": row.price,
                    "qty": row.qty,
                    "confidence": row.confidence,
                    "expected_edge_bps": row.expected_edge_bps,
                    "regime": row.regime,
                    "reason": row.reason_json,
                    "metadata": row.metadata_json,
                }
                for row in rows
            ]

    def list_paper_fills(self, limit: int = 20) -> list[dict[str, Any]]:
        with session_scope(self.engine) as session:
            rows = session.execute(
                select(PaperFillRecord).order_by(desc(PaperFillRecord.ts)).limit(limit)
            ).scalars().all()
            return [
                {
                    "id": row.id,
                    "ts": row.ts.isoformat() if row.ts else None,
                    "order_intent_id": row.order_intent_id,
                    "symbol": row.symbol,
                    "side": row.side,
                    "fill_price": row.fill_price,
                    "fill_qty": row.fill_qty,
                    "reason": row.reason_json,
                }
                for row in rows
            ]

    def list_recent_paper_fills(self, limit: int = 20) -> list[dict[str, Any]]:
        """Backward-compatible alias used by the CLI/API layer."""
        return self.list_paper_fills(limit=limit)

    def save_account_snapshot(self, *, kind: str, payload: dict[str, Any]) -> str:
        with session_scope(self.engine) as session:
            record = AccountSnapshotRecord(kind=kind, payload_json=_json_safe(payload))
            session.add(record)
            session.flush()
            return record.id

    def save_executions(self, payload: dict[str, Any]) -> int:
        rows = payload.get("list", [])
        count = 0
        with session_scope(self.engine) as session:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                exec_id = str(row.get("execId") or row.get("exec_id") or "")
                if not exec_id:
                    continue
                exists = session.execute(
                    select(ExecutionRecord).where(ExecutionRecord.exec_id == exec_id).limit(1)
                ).scalars().first()
                if exists:
                    continue
                record = ExecutionRecord(
                    exec_id=exec_id,
                    ts=_parse_ms(row.get("execTime")),
                    symbol=str(row.get("symbol", "")),
                    side=str(row.get("side", "")),
                    price=float(row.get("execPrice") or 0.0),
                    qty=float(row.get("execQty") or 0.0),
                    fee=float(row.get("execFee") or row.get("execFeeV2") or 0.0),
                    fee_currency=row.get("feeCurrency"),
                    raw_json=_json_safe(row),
                )
                session.add(record)
                count += 1
        return count

    @staticmethod
    def _insert_signal(
        session: Session,
        decision: SignalDecision,
        *,
        strategy_version: str,
    ) -> None:
        record = SignalRecord(
            id=decision.id,
            ts=decision.ts,
            symbol=decision.symbol,
            action=decision.action.value,
            side=_enum_value(decision.side),
            price=decision.price,
            qty=decision.qty,
            confidence=decision.confidence,
            expected_edge_bps=decision.expected_edge_bps,
            regime=decision.regime.value,
            reason_json=_json_safe(decision.reason),
            metadata_json=_json_safe(decision.metadata),
            strategy_version=strategy_version,
        )
        session.add(record)
        session.flush()

    @staticmethod
    def _active_intent_query(
        symbol: str,
        side: Side | None = None,
    ) -> Select[tuple[OrderIntentRecord]]:
        stmt = select(OrderIntentRecord).where(
            OrderIntentRecord.symbol == symbol,
            OrderIntentRecord.status == OrderIntentStatus.ACTIVE.value,
        )
        if side is not None:
            stmt = stmt.where(OrderIntentRecord.side == side.value)
        return stmt.order_by(desc(OrderIntentRecord.created_at))

    @staticmethod
    def _apply_fill_to_position(
        session: Session,
        *,
        symbol: str,
        side: Side,
        price: float,
        qty: float,
        ts: datetime,
    ) -> None:
        position = session.execute(
            select(PositionRecord)
            .where(
                PositionRecord.symbol == symbol,
                PositionRecord.status == PositionStatus.OPEN.value,
            )
            .order_by(desc(PositionRecord.opened_at))
            .limit(1)
        ).scalars().first()

        if side == Side.BUY:
            if position is None:
                session.add(
                    PositionRecord(
                        symbol=symbol,
                        qty=qty,
                        avg_entry=price,
                        status=PositionStatus.OPEN.value,
                        opened_at=ts,
                        updated_at=ts,
                    )
                )
                return
            new_qty = position.qty + qty
            if new_qty <= 0:
                return
            position.avg_entry = ((position.avg_entry * position.qty) + (price * qty)) / new_qty
            position.qty = new_qty
            position.updated_at = ts
            return

        if position is None:
            return
        sell_qty = min(qty, position.qty)
        position.realized_pnl += (price - position.avg_entry) * sell_qty
        position.qty = max(position.qty - sell_qty, 0.0)
        position.updated_at = ts
        if position.qty <= 1e-12:
            position.qty = 0.0
            position.status = PositionStatus.CLOSED.value
            position.closed_at = ts


def _fear_greed_from_record(record: FearGreedIndexRecord) -> FearGreedValue:
    return FearGreedValue(
        source=record.source,
        value=record.value,
        classification=record.classification,
        timestamp=record.timestamp,
        time_until_update_seconds=record.time_until_update_seconds,
        fetched_at=record.fetched_at,
        raw=record.raw_json or {},
    )


def _fear_greed_record_to_dict(row: FearGreedIndexRecord) -> dict[str, Any]:
    value = _fear_greed_from_record(row)
    payload = value.as_dict()
    payload.update({"id": row.id})
    return payload


def _parse_ms(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return _now()


def _instrument_spec_from_record(record: InstrumentSpecRecord) -> InstrumentSpec:
    return InstrumentSpec(
        symbol=record.symbol,
        category=record.category,
        status=record.status,
        base_coin=record.base_coin,
        quote_coin=record.quote_coin,
        price_tick_size=record.price_tick_size,
        qty_step=record.qty_step,
        min_order_qty=record.min_order_qty,
        min_order_amount_quote=record.min_order_amount_quote,
        max_limit_order_qty=record.max_limit_order_qty,
        max_market_order_qty=record.max_market_order_qty,
        base_precision=record.base_precision,
        quote_precision=record.quote_precision,
        raw=record.raw_json or {},
    )


def _instrument_spec_record_to_dict(row: InstrumentSpecRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "ts": row.ts.isoformat() if row.ts else None,
        "updated_at": row.ts.isoformat() if row.ts else None,
        "symbol": row.symbol,
        "category": row.category,
        "status": row.status,
        "base_coin": row.base_coin,
        "quote_coin": row.quote_coin,
        "price_tick_size": row.price_tick_size,
        "qty_step": row.qty_step,
        "min_order_qty": row.min_order_qty,
        "min_order_amount_quote": row.min_order_amount_quote,
        "min_order_amount": row.min_order_amount_quote,
        "max_limit_order_qty": row.max_limit_order_qty,
        "max_market_order_qty": row.max_market_order_qty,
    }
