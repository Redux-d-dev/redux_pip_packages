"""
The MT5 Gateway SDK's core client.

Two-tier design, matching the gateway's actual shape:
  - GatewayClient: account-management (start/stop/health), one API key
    can cover several accounts.
  - Account: scoped to one account_id, exposes the actual trading
    surface via small namespace objects (.terminal, .symbols,
    .trading, .orders, .positions, .history) rather than one giant
    class with 25 methods.

Deliberately depends on nothing platform-specific - only httpx and
pydantic. This SDK must work from any bot, on any OS, regardless of
what the gateway itself happens to be hosted on (Linux/Wine tonight,
Windows eventually).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Optional

import httpx

from . import exceptions as exc
from .constants import OrderSide, PendingOrderType, Timeframe
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

_DEFAULT_TIMEOUT = 90.0  # matches the gateway's own worker-proxy timeout tonight
_RETRYABLE_STATUS = frozenset({502, 503, 504})
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 2.0


def _raise_for_response(response: httpx.Response, *, account_id: Optional[str] = None) -> None:
    """
    Maps the gateway's actual response shapes to SDK exceptions.
    Never assumes the body is JSON - nginx's own error pages (e.g. a
    504 Gateway Time-out) are plain HTML, not JSON, and trying to
    .json() one unconditionally would raise a confusing, unrelated
    parsing error instead of the real problem (confirmed hitting this
    ourselves during testing).
    """
    if response.status_code < 400:
        return

    try:
        body: Any = response.json()
    except ValueError:
        body = response.text

    status = response.status_code

    if status in (401, 403):
        raise exc.AuthenticationError(
            "API key missing or not authorized.", status_code=status, raw=body
        )
    if status == 404 and account_id is not None:
        raise exc.AccountNotFoundError(account_id, status_code=status, raw=body)
    if status == 504 or (status in _RETRYABLE_STATUS and isinstance(body, str)):
        raise exc.TimeoutError(
            "Gateway timed out - the underlying call may still be running server-side.",
            status_code=status, raw=body,
        )
    if status == 400 and isinstance(body, dict) and "detail" in body:
        detail = body["detail"]
        if isinstance(detail, dict) and "retcode" in detail:
            raise exc.TradeError(
                detail.get("comment", "Trade request rejected by MT5."),
                retcode=detail.get("retcode"), raw=detail,
            )
        raise exc.ValidationError(str(detail), status_code=status, raw=body)
    if status in (500, 502):
        detail = body.get("detail") if isinstance(body, dict) else body
        raise exc.ServerError(str(detail), status_code=status, raw=body)

    # Fallback for anything not explicitly mapped above - still a real,
    # catchable error, just without a more specific subclass.
    raise exc.Mt5GatewayError(f"Unexpected response ({status}): {body}", status_code=status, raw=body)


class GatewayClient:
    """
    Top-level entry point. One instance per API key - that key may be
    scoped to several accounts, each reached via .account(account_id).
    """

    def __init__(self, base_url: str, api_key: str, *, timeout: float = _DEFAULT_TIMEOUT):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    async def __aenter__(self) -> GatewayClient:
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(
        self, method: str, path: str, *, account_id: Optional[str] = None,
        idempotent: bool = False, **kwargs,
    ) -> httpx.Response:
        """
        Central request path - every call in this SDK goes through
        here, so error mapping and retry logic only need to live in
        one place. idempotent=True (GETs, or writes with an explicit
        Idempotency-Key) allows safe automatic retry on transient
        gateway/network failures; non-idempotent writes are never
        silently retried, since that could double-execute a real trade.
        """
        last_exc: Optional[Exception] = None
        attempts = _MAX_RETRIES if idempotent else 1

        for attempt in range(attempts):
            try:
                response = await self._http.request(method, path, **kwargs)
            except httpx.ConnectError as e:
                last_exc = exc.ConnectionError(f"Could not reach gateway: {e}", raw=e)
            except httpx.TimeoutException as e:
                last_exc = exc.TimeoutError(f"Request timed out: {e}", raw=e)
            else:
                if response.status_code in _RETRYABLE_STATUS and idempotent and attempt < attempts - 1:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
                    continue
                _raise_for_response(response, account_id=account_id)
                return response

            if attempt < attempts - 1:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            raise last_exc

        raise last_exc  # pragma: no cover - unreachable, satisfies type checkers

    # ---------------- Gateway-level account management ----------------

    async def health(self, account_id: str) -> HealthStatus:
        resp = await self._request("GET", f"/health/{account_id}", account_id=account_id, idempotent=True)
        return HealthStatus.model_validate(resp.json())

    async def start_terminal(self, account_id: str) -> TerminalStartResult:
        resp = await self._request("POST", f"/accounts/{account_id}/terminal/start", account_id=account_id)
        return TerminalStartResult.model_validate(resp.json())

    async def stop_terminal(self, account_id: str) -> dict[str, Any]:
        resp = await self._request("POST", f"/accounts/{account_id}/terminal/stop", account_id=account_id)
        return resp.json()

    def account(self, account_id: str) -> "Account":
        """Returns a handle scoped to one account - the actual trading surface lives here."""
        return Account(self, account_id)


def connect_account(base_url: str, api_key: str, account_id: str, *, timeout: float = _DEFAULT_TIMEOUT) -> "Account":
    """
    Standalone entry point for callers who want ONE fully independent
    account with its own dedicated GatewayClient/HTTP connection - no
    sharing required. This SDK does not assume or require managing
    multiple accounts through a single shared client: use GatewayClient
    directly if one API key covers several accounts and you want to
    reuse one connection, or call this once per account if you'd
    rather each account be entirely self-contained, with its own
    connection and no shared state at all. Both patterns are fully
    supported - pick whichever matches how your bot is structured.
    """
    gateway = GatewayClient(base_url, api_key, timeout=timeout)
    return gateway.account(account_id)


class Account:
    """
    One account, scoped by account_id. Groups the trading surface into
    small namespaces matching routes.py's own section comments, so
    callers get e.g. `account.trading.market_order(...)` instead of
    one 25-method flat object.
    """

    def __init__(self, gateway: GatewayClient, account_id: str):
        self._gateway = gateway
        self._account_id = account_id
        self._prefix = f"/api/v1/accounts/{account_id}"
        self.terminal = _TerminalNamespace(self)
        self.symbols = _SymbolsNamespace(self)
        self.trading = _TradingNamespace(self)
        self.orders = _OrdersNamespace(self)
        self.positions = _PositionsNamespace(self)
        self.history = _HistoryNamespace(self)

    async def _request(self, method: str, path: str, *, idempotent: bool = False, **kwargs) -> httpx.Response:
        return await self._gateway._request(
            method, f"{self._prefix}{path}", account_id=self._account_id, idempotent=idempotent, **kwargs
        )


def _new_idempotency_key() -> str:
    return str(uuid.uuid4())


class _TerminalNamespace:
    def __init__(self, account: Account):
        self._a = account

    async def info(self) -> TerminalInfo:
        resp = await self._a._request("GET", "/terminal/info", idempotent=True)
        return TerminalInfo.model_validate(resp.json())

    async def account_info(self) -> AccountInfo:
        resp = await self._a._request("GET", "/terminal/account/info", idempotent=True)
        return AccountInfo.model_validate(resp.json())

    async def version(self) -> list:
        resp = await self._a._request("GET", "/terminal/version", idempotent=True)
        return resp.json()

    async def connect(self) -> dict[str, Any]:
        resp = await self._a._request("POST", "/terminal/connect")
        return resp.json()

    async def disconnect(self) -> dict[str, Any]:
        resp = await self._a._request("POST", "/terminal/disconnect")
        return resp.json()

    async def ping(self) -> bool:
        resp = await self._a._request("GET", "/terminal/ping", idempotent=True)
        return bool(resp.json().get("connected"))


class _SymbolsNamespace:
    def __init__(self, account: Account):
        self._a = account

    async def list(self) -> list[str]:
        """
        Returns every symbol name the server offers - can be several
        thousand and genuinely slow (confirmed: ~28s+ server-side for
        a full unfiltered list during testing). Prefer get()/select()
        for specific symbols where possible.
        """
        resp = await self._a._request("GET", "/symbols", idempotent=True)
        return resp.json()

    async def get(self, symbol: str) -> SymbolInfo:
        resp = await self._a._request("GET", f"/symbols/{symbol}", idempotent=True)
        return SymbolInfo.model_validate(resp.json())

    async def select(self, symbol: str) -> bool:
        resp = await self._a._request("POST", f"/symbols/select/{symbol}")
        return bool(resp.json().get("selected"))

    async def tick(self, symbol: str) -> Tick:
        resp = await self._a._request("GET", f"/symbols/ticks/{symbol}", idempotent=True)
        return Tick.model_validate(resp.json())

    async def rates_from_pos(
        self, symbol: str, timeframe: Timeframe = Timeframe.M1, pos: int = 0, count: int = 100,
    ) -> list[Rate]:
        resp = await self._a._request(
            "GET", "/symbols/rates/pos", idempotent=True,
            params={"symbol": symbol, "timeframe": timeframe.value, "pos": pos, "count": count},
        )
        return [Rate.model_validate(r) for r in resp.json()]

    async def rates_range(
        self, symbol: str, timeframe: Timeframe = Timeframe.M1,
        date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
    ) -> list[Rate]:
        params: dict[str, Any] = {"symbol": symbol, "timeframe": timeframe.value}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        resp = await self._a._request("GET", "/symbols/rates/range", idempotent=True, params=params)
        return [Rate.model_validate(r) for r in resp.json()]


class _TradingNamespace:
    def __init__(self, account: Account):
        self._a = account

    async def market_order(
        self, symbol: str, side: OrderSide, volume: float, *,
        deviation: int = 10, magic: int = 0, comment: str = "",
        sl: Optional[float] = None, tp: Optional[float] = None,
        idempotency_key: Optional[str] = None,
    ) -> TradeResult:
        """
        Places a real market order. idempotency_key defaults to a
        fresh UUID per call - pass your own if you need to safely
        retry the exact same intended order (e.g. after a timeout)
        without risking a duplicate execution.
        """
        payload: dict[str, Any] = {
            "symbol": symbol, "side": side.value, "volume": volume,
            "deviation": deviation, "magic": magic, "comment": comment,
        }
        if sl is not None:
            payload["sl"] = sl
        if tp is not None:
            payload["tp"] = tp
        headers = {"Idempotency-Key": idempotency_key or _new_idempotency_key()}
        resp = await self._a._request("POST", "/trading/order", json=payload, headers=headers)
        return TradeResult.model_validate(resp.json())

    async def modify_sl_tp(self, ticket: int, *, sl: Optional[float] = None, tp: Optional[float] = None) -> TradeResult:
        payload = {"ticket": ticket, "sl": sl, "tp": tp}
        resp = await self._a._request("POST", "/trading/modify-sl-tp", json=payload)
        return TradeResult.model_validate(resp.json())

    async def order_check(self, symbol: str) -> dict[str, Any]:
        resp = await self._a._request("GET", f"/trading/order_check/{symbol}", idempotent=True)
        return resp.json()


class _OrdersNamespace:
    def __init__(self, account: Account):
        self._a = account

    async def list(self) -> list[PendingOrder]:
        resp = await self._a._request("GET", "/orders", idempotent=True)
        return [PendingOrder.model_validate(o) for o in resp.json()]

    async def total(self) -> int:
        resp = await self._a._request("GET", "/orders/total", idempotent=True)
        return int(resp.json().get("count", 0))

    async def place_pending(
        self, symbol: str, order_type: PendingOrderType, volume: float, price: float, *,
        magic: int = 0, comment: str = "", sl: Optional[float] = None, tp: Optional[float] = None,
        expiration: Optional[int] = None, idempotency_key: Optional[str] = None,
    ) -> TradeResult:
        payload: dict[str, Any] = {
            "symbol": symbol, "order_type": order_type.value, "volume": volume, "price": price,
            "magic": magic, "comment": comment,
        }
        if sl is not None:
            payload["sl"] = sl
        if tp is not None:
            payload["tp"] = tp
        if expiration is not None:
            payload["expiration"] = expiration
        headers = {"Idempotency-Key": idempotency_key or _new_idempotency_key()}
        resp = await self._a._request("POST", "/orders/pending", json=payload, headers=headers)
        return TradeResult.model_validate(resp.json())

    async def modify(
        self, ticket: int, *, price: Optional[float] = None, sl: Optional[float] = None,
        tp: Optional[float] = None, expiration: Optional[int] = None,
    ) -> TradeResult:
        payload: dict[str, Any] = {}
        if price is not None:
            payload["price"] = price
        if sl is not None:
            payload["sl"] = sl
        if tp is not None:
            payload["tp"] = tp
        if expiration is not None:
            payload["expiration"] = expiration
        resp = await self._a._request("PUT", f"/orders/{ticket}", json=payload)
        return TradeResult.model_validate(resp.json())

    async def cancel(self, ticket: int) -> TradeResult:
        resp = await self._a._request("DELETE", f"/orders/{ticket}")
        return TradeResult.model_validate(resp.json())


class _PositionsNamespace:
    def __init__(self, account: Account):
        self._a = account

    async def list(self) -> list[Position]:
        resp = await self._a._request("GET", "/positions", idempotent=True)
        return [Position.model_validate(p) for p in resp.json()]

    async def by_symbol(self, symbol: str) -> list[Position]:
        resp = await self._a._request("GET", f"/positions/by_symbol/{symbol}", idempotent=True)
        return [Position.model_validate(p) for p in resp.json()]

    async def close(self, ticket: int, *, volume: Optional[float] = None) -> TradeResult:
        payload: dict[str, Any] = {"ticket": ticket}
        if volume is not None:
            payload["volume"] = volume
        resp = await self._a._request("POST", "/positions/close", json=payload)
        return TradeResult.model_validate(resp.json())

    async def close_all(self) -> dict[str, Any]:
        resp = await self._a._request("POST", "/positions/close_all")
        return resp.json()


class _HistoryNamespace:
    def __init__(self, account: Account):
        self._a = account

    async def deals(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> list[HistoryDeal]:
        params: dict[str, Any] = {}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        resp = await self._a._request("GET", "/history/deals", idempotent=True, params=params)
        return [HistoryDeal.model_validate(d) for d in resp.json()]

    async def orders(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> list[HistoryOrder]:
        params: dict[str, Any] = {}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        resp = await self._a._request("GET", "/history/orders", idempotent=True, params=params)
        return [HistoryOrder.model_validate(o) for o in resp.json()]

    async def order_by_ticket(self, ticket: int) -> HistoryOrder:
        resp = await self._a._request("GET", f"/history/order_by_ticket/{ticket}", idempotent=True)
        return HistoryOrder.model_validate(resp.json())
