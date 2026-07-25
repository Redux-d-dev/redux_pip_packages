"""
Exception hierarchy for the MT5 Gateway SDK.

Every exception carries enough context for the caller to make a real
decision (retry? alert a human? just log it?) rather than a bare
"something went wrong". Mapped directly from what the actual gateway
returns - see _raise_for_response() in client.py for the mapping logic.
"""
from __future__ import annotations

from typing import Any, Optional


class Mt5GatewayError(Exception):
    """
    Base class for every error this SDK raises. Callers can catch this
    alone to handle "anything went wrong with the gateway" generically,
    or catch a specific subclass for precise handling.
    """

    def __init__(self, message: str, *, status_code: int | None = None, raw: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw = raw  # the original response body/exception, for debugging


class AuthenticationError(Mt5GatewayError):
    """The API key is missing, invalid, or not authorized at all."""


class AccountNotFoundError(Mt5GatewayError):
    """
    The account_id is unknown OR the API key isn't scoped to it.
    The gateway deliberately returns the same error for both cases
    (security: never reveal which one it was) - the SDK preserves
    that ambiguity rather than pretending to know which it is.
    """

    def __init__(self, account_id: str, *, status_code: Optional[int] = None, raw: Any = None):
        super().__init__(f"Unknown account_id or unauthorized: '{account_id}'", status_code=status_code, raw=raw)
        self.account_id = account_id


class TradeError(Mt5GatewayError):
    """
    A trade request was understood and sent to the broker, but the
    broker/terminal rejected it (bad price, market closed, insufficient
    margin, invalid stops, etc). retcode is MT5's own trade return
    code - see constants.TradeRetcode for the common ones.
    """

    def __init__(self, message: str, *, retcode: Optional[int] = None, raw: Any = None):
        super().__init__(message, status_code=400, raw=raw)
        print(retcode)
        self.retcode = retcode


class ValidationError(Mt5GatewayError):
    """The request itself was malformed (bad symbol, bad enum value, missing field) - a 4xx that isn't a trade rejection or auth issue."""


class ServerError(Mt5GatewayError):
    """
    The gateway or the underlying MT5 call itself failed unexpectedly
    (a 5xx that isn't a timeout). Often means the terminal or worker
    process is in a bad state - worth checking gateway_health() next.
    """


class TimeoutError(Mt5GatewayError):
    """
    The gateway didn't respond in time. This does NOT necessarily mean
    the underlying operation failed - for slow calls (e.g. unfiltered
    symbol lists, or an account still cold-starting) it may still be
    running server-side. Safe to retry only for read-only calls, or
    for trading calls that were sent with an Idempotency-Key.
    """


class ConnectionError(Mt5GatewayError):
    """Couldn't reach the gateway at all - DNS failure, connection refused, network unreachable."""
