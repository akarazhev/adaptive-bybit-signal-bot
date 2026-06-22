from __future__ import annotations

from enum import StrEnum


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class Regime(StrEnum):
    RANGE = "range"
    UPTREND = "uptrend"
    UPTREND_PULLBACK = "uptrend_pullback"
    DOWNTREND = "downtrend"
    SHOCK = "shock"
    NO_TRADE = "no_trade"


class SignalAction(StrEnum):
    HOLD = "HOLD"
    BUY_INTENT = "BUY_INTENT"
    SELL_INTENT = "SELL_INTENT"
    CANCEL_INTENT = "CANCEL_INTENT"
    REPRICE_INTENT = "REPRICE_INTENT"


class OrderIntentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    FILLED = "FILLED"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"
    CLOSED = "CLOSED"


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
