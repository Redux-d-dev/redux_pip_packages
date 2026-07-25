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


# Human-readable explanation for every retcode above - so callers can
# just read `result.reason` instead of maintaining their own mapping
# of numeric codes to meaning.
TRADE_RETCODE_MESSAGES: dict[int, str] = {
    TradeRetcode.REQUOTE: "Price changed - a requote occurred, the broker offered a new price.",
    TradeRetcode.REJECT: "Request rejected by the broker/server.",
    TradeRetcode.CANCEL: "Request canceled by the trader (e.g. in the terminal UI).",
    TradeRetcode.PLACED: "Order placed successfully.",
    TradeRetcode.DONE: "Request completed successfully.",
    TradeRetcode.DONE_PARTIAL: "Request completed, but only partially filled.",
    TradeRetcode.ERROR: "Request processing error.",
    TradeRetcode.TIMEOUT: "Request timed out - no response from the server in time.",
    TradeRetcode.INVALID: "Invalid request - malformed or missing required fields.",
    TradeRetcode.INVALID_VOLUME: "Invalid volume in the request (below min, above max, or wrong step).",
    TradeRetcode.INVALID_PRICE: "Invalid price in the request.",
    TradeRetcode.INVALID_STOPS: "Invalid stop loss or take profit (too close to price, or invalid value).",
    TradeRetcode.TRADE_DISABLED: "Trading is disabled for this account or symbol.",
    TradeRetcode.MARKET_CLOSED: "Market is closed for this symbol right now.",
    TradeRetcode.NO_MONEY: "Insufficient funds/margin to complete the request.",
    TradeRetcode.PRICE_CHANGED: "Price changed since the request was sent.",
    TradeRetcode.PRICE_OFF: "No quotes currently available for this symbol.",
    TradeRetcode.INVALID_EXPIRATION: "Invalid order expiration date/time.",
    TradeRetcode.ORDER_CHANGED: "Order state changed (e.g. already filled/canceled) before this request reached it.",
    TradeRetcode.TOO_MANY_REQUESTS: "Too many requests sent too quickly - rate limited by the server.",
    TradeRetcode.NO_CHANGES: "No actual changes in the request compared to the current order/position state.",
    TradeRetcode.SERVER_DISABLES_AT: "Autotrading is disabled by the trade server.",
    TradeRetcode.CLIENT_DISABLES_AT: "Autotrading is disabled by the client terminal.",
    TradeRetcode.LOCKED: "Request locked for processing - try again shortly.",
    TradeRetcode.FROZEN: "Order/position is frozen - modification/close not currently allowed.",
    TradeRetcode.INVALID_FILL: "Invalid order filling type for this symbol.",
    TradeRetcode.CONNECTION: "No connection to the trade server.",
    TradeRetcode.ONLY_REAL: "Operation only allowed on a real account, not this account type.",
    TradeRetcode.LIMIT_ORDERS: "Reached the maximum number of pending orders allowed.",
    TradeRetcode.LIMIT_VOLUME: "Reached the maximum order/position volume allowed for this symbol.",
    TradeRetcode.INVALID_ORDER: "Invalid or prohibited order type for this operation.",
    TradeRetcode.POSITION_CLOSED: "Position already closed.",
    TradeRetcode.CLOSE_ORDER_EXIST: "A close order for this position already exists.",
    TradeRetcode.LIMIT_POSITIONS: "Reached the maximum number of open positions allowed.",
    TradeRetcode.REJECT_CANCEL: "Rejected: pending order cancellation in progress.",
    TradeRetcode.LONG_ONLY: "Only long (buy) positions allowed for this symbol.",
    TradeRetcode.SHORT_ONLY: "Only short (sell) positions allowed for this symbol.",
    TradeRetcode.CLOSE_ONLY: "Only position-closing operations allowed for this symbol right now.",
    TradeRetcode.FIFO_CLOSE: "Positions must be closed in FIFO order (oldest first) for this account.",
}


def describe_retcode(retcode: int) -> str:
    """Human-readable meaning for a retcode - falls back gracefully for anything unrecognized."""
    try:
        return TRADE_RETCODE_MESSAGES[TradeRetcode(retcode)]
    except ValueError:
        return f"Unrecognized retcode {retcode} - not in MT5's documented set."


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