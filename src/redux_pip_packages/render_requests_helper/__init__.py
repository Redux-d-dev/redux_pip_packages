import asyncio
from logging import getLogger
from typing import Callable, Optional

import aiohttp

log = getLogger(__name__)

class Call:
    """Thin aiohttp transport wrapper with retry + backoff."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def make_request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        total_attempts: int = 3,
    ) -> dict:
        params = params or {}
        headers = headers or {}

        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))

        method = method.lower()
        url = self.base_url + url if self.base_url and not url.startswith("http") else url

        if method not in ("get", "post"):
            raise ValueError(f"Method '{method}' not recognised")

        last_error: Optional[Exception] = None

        for attempt in range(1, total_attempts + 1):
            try:
                if method == "get":
                    req = self.session.request(method, url, params=params, headers=headers)
                else:
                    req = self.session.request(method, url, json=params, headers=headers)

                async with req as resp:
                    if resp.status not in (200, 201):
                        body = await resp.text()
                        log.warning(f"[REQUEST] {resp.status} on attempt {attempt}/{total_attempts}: {body}")
                        resp.raise_for_status()
                    return await resp.json(content_type=None)

            except Exception as e:
                last_error = e
                log.warning(f"[REQUEST] Error on attempt {attempt}/{total_attempts}: {e}")
                if attempt < total_attempts:
                    await asyncio.sleep(2 ** attempt)

        raise last_error or RuntimeError("Request failed with no captured error")

    async def close_session(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()


class RenderRequestsHelper(Call):
    """
    Exchange-agnostic request helper that detects IP-whitelist rejections
    and hands off to a caller-supplied callback to resolve new credentials.

    on_api_switch: async callable, returns fresh `headers` dict for
                   make_api_call, or returns anything (ignored) for
                   make_request_with_sdk — in that case it should mutate
                   whatever the lambda_sdk_method closes over.
    """

    def __init__(
        self,
        on_api_switch: Optional[Callable] = None,
        api_switch: bool = True,
        api_switch_signal_code: str | int = "10010",
        api_switch_limit: int = 5,
        base_url: Optional[str] = None,
    ) -> None:
        super().__init__(base_url=base_url)
        self.api_switch_signal_code = str(api_switch_signal_code)
        self._on_api_switch = on_api_switch
        self.api_switch_limit = api_switch_limit
        self.api_switch_count = 0
        self.api_switch = api_switch
        self._switch_lock = asyncio.Lock()

        if api_switch and not on_api_switch:
            raise ValueError("on_api_switch callback must be provided if api_switch is True")

    async def _try_switch(self, error: Exception) -> bool:
        """
        Returns True if a switch was performed and caller should retry.
        Returns False if switching isn't applicable/available/exhausted.
        """
        if self.api_switch_signal_code not in str(error) or not self.api_switch:
            return False

        async with self._switch_lock:
            if self.api_switch_count >= self.api_switch_limit:
                return False
            self.api_switch_count += 1
            count = self.api_switch_count

        new_headers = await self._on_api_switch()
        log.warning(
            f"API switch triggered due to error: {error}. "
            f"Attempt {count}/{self.api_switch_limit}"
        )
        return new_headers if new_headers is not None else True

    async def _make_request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        response = await self.make_request(method, url, params, headers)

        ret_code = response.get("ret_code") if response.get("ret_code") is not None else response.get("retCode")
        ret_msg = response.get("ret_msg") or response.get("retMsg", "Unknown error")

        if ret_code not in (0, None):
            raise Exception(f"API error [{ret_code}]: {ret_msg}")

        return response

    async def make_api_call(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        headers = headers or {}
        while True:
            try:
                resp =  await self._make_request(method, url, params, headers)
                self.api_switch_count = 0  # reset on success
                return resp
            except Exception as e:
                result = await self._try_switch(e)
                if result is False:
                    raise
                if isinstance(result, dict):
                    headers = result
                # else: switch happened, callback mutates external state, just retry

    async def make_request_with_sdk(
        self,
        lambda_sdk_method: Callable,
        is_async: bool = True,
        **kwargs,
    ) -> dict:
        """
        lambda_sdk_method: zero-state-holding callable (e.g. a closure that
        reads current credentials from wherever on_api_switch writes them)
        so a rebuilt SDK client is picked up automatically on next call.
        """
        while True:
            try:
                if is_async:
                    resp =  await lambda_sdk_method(**kwargs)
                else:
                    resp = await asyncio.to_thread(lambda_sdk_method, **kwargs)
                self.api_switch_count = 0  # reset on success
                return resp
            except Exception as e:
                result = await self._try_switch(e)
                if result is False:
                    raise
                # SDK path: callback is expected to rebuild the client in place
