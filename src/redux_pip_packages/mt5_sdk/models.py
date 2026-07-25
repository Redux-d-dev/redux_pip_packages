"""
Typed response models. Pydantic gives us real attribute access and
validation instead of raw dict[key] guessing, while `extra="allow"`
tolerates any additional fields MT5 returns that aren't explicitly
listed below - these objects (especially SymbolInfo) have 80+ fields,
and hand-enumerating every one isn't worth the maintenance cost. The
fields listed are the ones callers actually reach for.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


class TerminalInfo(_Base):
    connected: bool
    trade_allowed: bool
    build: int
    name: str
    company: str
    language: str
    path: Optional[str] = None


class AccountInfo(_Base):
    login: int
    name: str
    server: str
    currency: str
    balance: float
    equity: float
    profit: float
    margin: float
    margin_free: float
    leverage: int
    trade_allowed: bool


class SymbolInfo(_Base):
    name: str
    visible: bool
    bid: float
    ask: float
    digits: int
    point: float
    volume_min: float
    volume_max: float
    volume_step: float
    trade_contract_size: float
    currency_base: str
    currency_profit: str
    description: str


class Tick(_Base):
    time: int
    bid: float
    ask: float
    last: float
    volume: int


class Rate(_Base):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: int


class Position(_Base):
    ticket: int
    symbol: str
    volume: float
    type: int  # 0 = buy, 1 = sell (matches MT5's ORDER_TYPE_BUY/SELL)
    price_open: float
    price_current: float
    sl: float
    tp: float
    profit: float
    swap: float
    magic: int
    comment: str


class PendingOrder(_Base):
    ticket: int
    symbol: str
    volume_initial: float
    volume_current: float
    price_open: float
    sl: float
    tp: float
    type: int
    magic: int
    comment: str


class HistoryDeal(_Base):
    ticket: int
    order: int
    time: int
    type: int
    entry: int
    volume: float
    price: float
    profit: float
    commission: float
    swap: float
    symbol: str
    comment: str


class HistoryOrder(_Base):
    ticket: int
    time_setup: int
    time_done: int
    type: int
    state: int
    volume_initial: float
    volume_current: float
    price_open: float
    sl: float
    tp: float
    symbol: str
    comment: str


class TradeResult(_Base):
    """
    The response shape for every trading operation (market order,
    modify, close, pending order place/modify/cancel). `retcode` is
    the field to check for success - see constants.TradeRetcode.
    """
    retcode: int
    deal: int
    order: int
    volume: float
    price: float
    comment: str
    request: dict[str, Any]

    @property
    def is_success(self) -> bool:
        from .constants import TradeRetcode
        try:
            return TradeRetcode(self.retcode).is_success
        except ValueError:
            # An unrecognized retcode - be conservative, treat as failure
            # rather than silently assume success for an unknown code.
            return False


class HealthStatus(_Base):
    status: str
    mt5_connected: Optional[bool] = None


class TerminalStartResult(_Base):
    status: str
    account_id: str
    health: Optional[dict[str, Any]] = None
    start_up_dur: Optional[str] = None
