"""
Constants mirroring MT5's own values.

Deliberately NOT imported from the `MetaTrader5` package - that package
is Windows-only, and this SDK must run anywhere (Linux bots, other
servers, anywhere HTTP works) regardless of what platform the gateway
itself happens to be hosted on. These values are public, documented,
and stable in MT5's own API - safe to define independently here.
"""
from enum import IntEnum, Enum


class TradeRetcode(IntEnum):
    """MT5's own trade return codes. DONE (10009) means genuine success."""
    REQUOTE = 10004
    REJECT = 10006
    CANCEL = 10007
    PLACED = 10008
    DONE = 10009
    DONE_PARTIAL = 10010
    ERROR = 10011
    TIMEOUT = 10012
    INVALID = 10013
    INVALID_VOLUME = 10014
    INVALID_PRICE = 10015
    INVALID_STOPS = 10016
    TRADE_DISABLED = 10017
    MARKET_CLOSED = 10018
    NO_MONEY = 10019
    PRICE_CHANGED = 10020
    PRICE_OFF = 10021
    INVALID_EXPIRATION = 10022
    ORDER_CHANGED = 10023
    TOO_MANY_REQUESTS = 10024
    NO_CHANGES = 10025
    SERVER_DISABLES_AT = 10026
    CLIENT_DISABLES_AT = 10027
    LOCKED = 10028
    FROZEN = 10029
    INVALID_FILL = 10030
    CONNECTION = 10031
    ONLY_REAL = 10032
    LIMIT_ORDERS = 10033
    LIMIT_VOLUME = 10034
    INVALID_ORDER = 10035
    POSITION_CLOSED = 10036
    CLOSE_ORDER_EXIST = 10038
    LIMIT_POSITIONS = 10039
    REJECT_CANCEL = 10040
    LONG_ONLY = 10041
    SHORT_ONLY = 10042
    CLOSE_ONLY = 10043
    FIFO_CLOSE = 10044

    @property
    def is_success(self) -> bool:
        return self in (TradeRetcode.DONE, TradeRetcode.DONE_PARTIAL, TradeRetcode.PLACED)


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PendingOrderType(str, Enum):
    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    BUY_STOP = "BUY_STOP"
    SELL_STOP = "SELL_STOP"


class Timeframe(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"
