"""
MT5 Gateway SDK - a pure HTTP client for the multi-account MT5 gateway.

No dependency on the MetaTrader5 package or any Windows-specific
library - this SDK runs anywhere httpx runs, regardless of what
platform the gateway itself is hosted on.

Basic usage:

    import asyncio
    from mt5_sdk import GatewayClient, OrderSide

    async def main():
        async with GatewayClient("https://34-35-130-0.nip.io", "sk_...") as gw:
            acct = gw.account("demo_1")
            info = await acct.terminal.account_info()
            print(info.balance)

            result = await acct.trading.market_order("EURUSD", OrderSide.BUY, 0.01)
            if result.is_success:
                print("Order filled:", result.deal)
            else:
                print(f"Rejected ({result.retcode_name}): {result.reason}")

    asyncio.run(main())
"""
from .client import Account, GatewayClient, connect_account
from .constants import OrderSide, PendingOrderType, Timeframe, TradeRetcode, describe_retcode
from .exceptions import (
    AccountNotFoundError,
    AuthenticationError,
    ConnectionError,
    Mt5GatewayError,
    ServerError,
    TimeoutError,
    TradeError,
    ValidationError,
    ResourceNotFoundError,
)
from .models import (
    AccountInfo,
    HealthStatus,
    HistoryDeal,
    HistoryOrder,
    PendingOrder,
    Position,
    Rate,
    SymbolInfo,
    TerminalInfo,
    TerminalStartResult,
    Tick,
    TradeResult,
)



__all__ = [
    "ResourceNotFoundError",
    "GatewayClient",
    "Account",
    "connect_account",
    "OrderSide",
    "PendingOrderType",
    "Timeframe",
    "TradeRetcode",
    "describe_retcode",
    "Mt5GatewayError",
    "AuthenticationError",
    "AccountNotFoundError",
    "TradeError",
    "ValidationError",
    "ServerError",
    "TimeoutError",
    "ConnectionError",
    "TerminalInfo",
    "AccountInfo",
    "SymbolInfo",
    "Tick",
    "Rate",
    "Position",
    "PendingOrder",
    "HistoryDeal",
    "HistoryOrder",
    "TradeResult",
    "HealthStatus",
    "TerminalStartResult",
]