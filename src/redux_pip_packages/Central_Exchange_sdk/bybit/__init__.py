import asyncio
import aiohttp
import hmac
import hashlib
import time
import json
from typing import Dict, Any, Optional
import urllib
from dotenv import load_dotenv
import os
import ipaddress



from ...render_requests_helper import RenderRequestsHelper

load_dotenv()

_log_cache: dict = {}
IS_ON_RENDER = os.getenv("RENDER", "false").lower() == "true"

def log(msg: str, cooldown: int = 60, key: str = None):
    now = time.time()
    cache_key = key or msg
    if now - _log_cache.get(cache_key, 0) < cooldown:
        return
    _log_cache[cache_key] = now
    wat = time.gmtime(now + 3600)
    ts  = time.strftime("%H:%M:%S", wat)
    print(f"[{ts}] {msg}", flush=True)


async def get_current_ip() -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.ipify.org?format=json",
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            data = await resp.json()
            return data["ip"]



def resolve_api_key(api_keys: list, current_ip: str) -> dict | None:

    # If local, always return the fallback key directly — no IP matching
    if not IS_ON_RENDER:
        for entry in api_keys:
            if not entry.get("ip_range"):
                key    = entry["key"]
                secret = entry["secret"]-
                if key and secret:
                    log(f"Local mode → using fallback key: {entry['key_ref']}")
                    return {"key": key, "secret": secret}
        return None

    # On Render — match by subnet first, then octet range within it
    try:
        ip_obj = ipaddress.ip_address(current_ip)
        last_octet = int(current_ip.split(".")[-1])
    except (ValueError, IndexError):
        log(f"Could not parse current IP: {current_ip}")
        return None

    for entry in api_keys:
        ip_range = entry.get("ip_range")
        if not ip_range:
            continue

        subnet = ip_range.get("subnet")
        if not subnet:
            continue

        try:
            if ip_obj not in ipaddress.ip_network(subnet):
                continue  # wrong subnet entirely — skip regardless of octet
        except ValueError:
            log(f"Invalid subnet in config for {entry.get('key_ref')}: {subnet}")
            continue

        if ip_range["start"] <= last_octet <= ip_range["end"]:
            key    = entry["key"]
            secret = entry["secret"]
            if key and secret:
                log(f"Render mode → using key: {entry['key_ref']} (IP: {current_ip})")
                return {"key": key, "secret": secret}

    return None



class Bybit(RenderRequestsHelper):
    def __init__(self, Config: object):
        super().__init__(
            on_api_switch=self._handle_ip_switch,
            api_switch=True,
            api_switch_signal_code="10010",
            base_url="https://api.bybit.com",
        )
        self.api_key    = Config.BYBIT_API_KEY
        self.api_secret = Config.BYBIT_SECRET_KEY
        self.ip_bounded_api_key = Config.BYBIT_API_KEYS[0]["key"]  # fallback key for IP-bounded endpoints (withdraw)
        self.ip_bounded_api_secret = Config.BYBIT_API_KEYS[0]["secret"]
        self.BYBIT_API_KEYS = Config.BYBIT_API_KEYS
        self._clock_offset_ms: int = 0
        self.pairs = {}

    async def _handle_ip_switch(self):
        """
        Rebuilds credentials in place. Because _request re-signs fresh on
        every call using self.api_key / self.api_secret, nothing else needs
        to change once these two attrs are updated.
        """
        current_ip = await get_current_ip()
        resolved = resolve_api_key(self.BYBIT_API_KEYS, current_ip)
        if not resolved:
            raise Exception(f"No valid Bybit API key for IP {current_ip}")

        self.ip_bounded_api_key = resolved["key"]
        self.ip_bounded_api_secret = resolved["secret"]
        log(f"[IP SWITCH] Bybit key switched to '{resolved.get('label', '?')}' for IP {current_ip}")
        return None

    def _generate_signature(self, timestamp: str, payload: str, use_ip_bounded_api= False) -> str:
        recv_window = "5000"
        api_key = self.api_key if not use_ip_bounded_api else self.ip_bounded_api_key
        api_secret = self.api_secret if not use_ip_bounded_api else self.ip_bounded_api_secret
        message = timestamp + api_key + recv_window + payload
        return hmac.new(
            api_secret.encode("utf-8"),
            message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

    def _get_headers(self, timestamp: str, signature: str, use_ip_bounded_api: bool = False) -> Dict[str, str]:
        return {
            "X-BAPI-API-KEY":     self.api_key if not use_ip_bounded_api else self.ip_bounded_api_key,
            "X-BAPI-SIGN":        signature,
            "X-BAPI-TIMESTAMP":   timestamp,
            "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type":       "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        signed: bool = False,
        max_retries: int = 3,
        use_ip_bounded_api = False,
    ) -> Dict[str, Any] | None:
        last_error = None

        for attempt in range(1, max_retries + 1):
            timestamp = str(int(time.time() * 1000) + self._clock_offset_ms)

            if method.upper() == "GET":
                query_string = urllib.parse.urlencode(params or {})
                url        = self.base_url + endpoint + (f"?{query_string}" if query_string else "")
                payload    = query_string
                req_params = {}  # already baked into url
            else:  # POST
                url        = self.base_url + endpoint
                payload    = json.dumps(params or {})
                req_params = params or {}  # make_request sends this as json=

            headers = (
                self._get_headers(timestamp, self._generate_signature(timestamp, payload, use_ip_bounded_api), use_ip_bounded_api)
                if signed
                else {"Content-Type": "application/json"}
            )

            try:
                data = await self.make_request(method, url, params=req_params, headers=headers)

                if data is None:
                    raise Exception("Empty response from Bybit")

                resp_code = data.get("retCode", data.get("ret_code"))

                if resp_code != 0:
                    #print(data)
                    raise Exception(f"Bybit API Error [{resp_code}]: {data.get('retMsg', data.get('ret_msg', 'Unknown error message'))}")

                if attempt > 1:
                    log(f"[BYBIT] Recovered on attempt {attempt}")
                return data

            except Exception as e:
                last_error = e
                switched = await self._try_switch(e)
                if switched is not False:
                    continue  # retry immediately with new key and secrets
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)

        raise last_error

    async def sync_time(self):
        data = await self.make_request("GET", f"{self.base_url}/v5/market/time")
        server_time_ms = data["time"]  # already ms
        self._clock_offset_ms = server_time_ms - int(time.time() * 1000)
        print(f"[TIME SYNC] Bybit offset: {self._clock_offset_ms}ms")

    async def get_bid_ask(self) -> list:
        data = await self._request("GET", "/v5/market/tickers", {"category": "spot"})
        if not data:
            return []

        return [
            {
                "exchange":    "bybit",
                "symbol":      p.get("symbol"),
                "last_price":  p.get("lastPrice"),
                "bid_price":   float(p.get("bid1Price")),
                "ask_price":   float(p.get("ask1Price")),
                "bid_qty_usd": float(p.get("bid1Size"))  * float(p.get("bid1Price")),
                "ask_qty_usd": float(p.get("ask1Size"))  * float(p.get("ask1Price")),
            }
            for p in data["result"]["list"]
            if p.get("bid1Price") and p.get("ask1Price") and p.get("symbol")
        ]


    async def get_ticker(self, symbol: str) -> dict | None:
        data = await self._request("GET", "/v5/market/tickers", {"category": "spot", "symbol": symbol})
        if not data:
            return None
        rows = data.get("result", {}).get("list", [])
        if not rows:
            return None
        p = rows[0]
        if not p.get("bid1Price") or not p.get("ask1Price"):
            return None
        return {
            "exchange":  "bybit",
            "symbol":    symbol,
            "bid_price": float(p["bid1Price"]),
            "ask_price": float(p["ask1Price"]),
        }
    


    async def load_pairs(self):
        """
        Bybit docs rate limit = 10 req/s (IP)
        Public endpoints. Loads all linear instruments and borrowable coins
        into one unified self.pairs dict. Call once on startup.
        Lookup by symbol is O(1) after that.
        """
        instruments_data, borrow_data = await asyncio.gather(
            self._request("GET", "/v5/market/instruments-info", {"category": "spot", "limit": 1000}),
            self._request("GET", "/v5/spot-margin-trade/currency-data")
        )

        borrowable_map = {}
        for p in borrow_data.get("result", {}).get("list", []):
            if not p.get("flexibleManualBorrowable"):
                continue
            borrowable_map[p["currency"]] = {
                "minBorrowQty":    float(p["minFlexibleManualBorrowQty"]),
                "borrowAccuracy":  int(p["flexibleManualBorrowAccuracy"]),
            }

        for p in instruments_data.get("result", {}).get("list", []):
            symbol = p["symbol"]
            if not symbol.endswith("USDT"):
                continue
            coin        = symbol.replace("USDT", "").replace("USDC", "")
            borrow_info = borrowable_map.get(coin)

            self.pairs[symbol] = {
                "minOrderQty":      float(p["lotSizeFilter"]["minOrderQty"]),
                "qtyStep":          float(p["lotSizeFilter"]["qtyStep"]),
                "maxLeverage":      int(float(p["leverageFilter"]["maxLeverage"])),
                "minNotionalValue": float(p["lotSizeFilter"]["minNotionalValue"]),
                "borrowable":       borrow_info is not None,
                "minBorrowQty":     borrow_info["minBorrowQty"]   if borrow_info else None,
                "borrowAccuracy":   borrow_info["borrowAccuracy"] if borrow_info else None,
            }

        log(f"[PAIRS] Loaded {len(self.pairs)} pairs — {len(borrowable_map)} borrowable")

    async def get_balance(self) -> dict:
        data    = await self._request(
            "GET",
            "/v5/account/wallet-balance",
            {"accountType": "UNIFIED", "coin": "USDT"},
            signed=True,
        )
        account = data.get("result", {}).get("list", [{}])[0]
        usdt    = next((c for c in account.get("coin", []) if c["coin"] == "USDT"), {})

        return {
            "walletBalance":  float(usdt.get('walletBalance', 0)),
            "equity":         float(usdt.get("equity", 0)),
            "accountIMRate":  float(account.get("accountIMRate", 0)),
        }

    async def get_max_borrowable(self, symbol: str) -> float | None:
        coin = symbol.replace("USDT", "")
        data = await self._request(
            "GET",
            "/v5/spot-margin-trade/max-borrowable",
            {"currency": coin.upper()},
            signed=True,
        )
        return float(data.get("result", {}).get("maxLoan", 0))

    async def margin_borrow(self, coin: str, amount: str) -> dict | None:
        try:
            data = await self._request("POST", "/v5/account/borrow", {
                "coin":   coin,
                "amount": amount,
            }, signed=True)
            return data.get("result")
        except Exception as e:
            log(f"[BORROW] Failed to borrow {amount} {coin}: {e}")
            return None

    async def margin_repay(self, symbol: str) -> bool:
        coin = symbol.upper().replace("USDT", "")
        try:
            data   = await self._request("POST", "/v5/account/no-convert-repay", {
                "coin":          coin,
                "repaymentType": "FLEXIBLE",
            }, signed=True)
            status = data.get("result", {}).get("resultStatus")

            if status == "SU":
                return True
            elif status == "P":
                log(f"[REPAY] {coin} repayment processing...")
                return True
            else:
                log(f"[REPAY] {coin} repayment failed. Status: {status}")
                return False

        except Exception as e:
            msg = str(e)
            if "131084" in msg:
                log("[REPAY] Blackout window — repayment prohibited right now")
            elif "34022044" in msg:
                log(f"[REPAY] {coin} — nothing to repay or amount too small, skipping")
                return True
            else:
                log(f"[REPAY] Failed to repay {coin}: {e}")
            return False

    async def set_spot_leverage(self, leverage: str = "10") -> bool:
        try:
            await self._request("POST", "/v5/spot-margin-trade/set-leverage", {
                "leverage": leverage,
            }, signed=True)
            return True
        except Exception as e:
            msg = str(e)
            if "170036" in msg:
                log("[SPOT LEVERAGE] Spot margin not enabled — complete quiz on app first")
            elif "170037" in msg:
                log("[SPOT LEVERAGE] Coin not supported for spot margin")
            else:
                log(f"[SPOT LEVERAGE] Failed: {msg}")
            return False

    async def spot_sell(self, symbol: str, qty: str, price: float = None) -> dict | None:
        try:
            resp = await self._request("POST", "/v5/order/create", {
                "category":  "spot",
                "symbol":    symbol,
                "side":      "Sell",
                "orderType": "Market",
                "qty":       str(qty),
                "isLeverage": 1,
                "marketUnit": "baseCoin",
            }, signed=True)
            data = resp.get("result")
            if not data:
                return None
            return {**data, "order_id": data.get("orderId")}
        except Exception as e:
            log(f"[SPOT SELL] Failed {qty} {symbol}: {e}")
            raise e

    async def spot_buy(self, symbol: str, qty: str, price: float = None) -> dict | None:
        try:
            resp = await self._request("POST", "/v5/order/create", {
                "category":  "spot",
                "symbol":    symbol,
                "side":      "Buy",
                "orderType": "Market",
                "qty":       str(qty),
                "isLeverage": 1,
                "marketUnit": "baseCoin",
            }, signed=True)
            data = resp.get("result")
            if not data:
                return None
            return {**data, "order_id": data.get("orderId")}
        except Exception as e:
            log(f"[SPOT BUY] Failed {qty} {symbol}: {e}")
            raise e

    async def futures_short(self, symbol: str, qty: str) -> dict | None:
        try:
            resp = await self._request("POST", "/v5/order/create", {
                "category":  "linear",
                "symbol":    symbol,
                "side":      "Sell",
                "orderType": "Market",
                "qty":       str(qty),
            }, signed=True)
            data = resp.get("result")
            if not data:
                return None
            return {**data, "order_id": data.get("orderId")}
        except Exception as e:
            log(f"[FUTURES SHORT] Failed {qty} {symbol}: {e}")
            raise e

    async def futures_close(self, symbol: str, qty: str) -> dict | None:
        try:
            resp = await self._request("POST", "/v5/order/create", {
                "category":   "linear",
                "symbol":     symbol,
                "side":       "Buy",
                "orderType":  "Market",
                "qty":        str(qty),
                "reduceOnly": True,
            }, signed=True)
            data = resp.get("result")
            if not data:
                return None
            return {**data, "order_id": data.get("orderId")}
        except Exception as e:
            log(f"[FUTURES CLOSE] Failed {qty} {symbol}: {e}")
            raise e

    async def get_fill(self, symbol: str, order_id: str) -> dict | None:
        data = await self._request(
            "GET", "/v5/order/history",
            {"category": "spot", "symbol": symbol, "orderId": order_id},
            signed=True,
        )
        orders = data.get("result", {}).get("list", []) if data else []

        if not orders:
            return None

        o          = orders[0]
        avg_price  = float(o.get("avgPrice")   or 0)
        filled_qty = float(o.get("cumExecQty") or 0)
        fee_detail = o.get("cumFeeDetail") or {}
        fee_coin   = next(iter(fee_detail), None)
        fee_amount = float(fee_detail.get(fee_coin, 0)) if fee_coin else 0.0
        fee_usd    = fee_amount * avg_price if fee_coin and fee_coin != "USDT" else fee_amount

        return {
            "order_id":   order_id,
            "avg_price":  avg_price,
            "filled_qty": filled_qty,
            "fee_usd":    fee_usd,
        }

    # ─── PREDEFINED USDT DEPOSIT ADDRESSES ───────────────────────────────
    _usdt_deposit_addresses: dict = {}

    async def withdraw_coin(
        self,
        coin:    str,
        chain:   str,
        address: str,
        amount:  str,
        tag:     str = "",
    ) -> str | None:
        """
        Confirmed working and reliable provided that the provided Args are correct.
        Tested transfer from bybit to mexc already

        _summary_

        Args:
            coin (str): _description_
            chain (str): _description_
            address (str): _description_
            amount (str): _description_
            tag (str, optional): _description_. Defaults to "".

        Returns:
            str | None: _description_
        
        """
        try:
            body = {
                "coin":        coin.upper(),
                "chain":       chain,
                "address":     address,
                "amount":      str(amount),
                "timestamp":   str(int(time.time() * 1000)),
                "accountType": "UTA",
            }
            if tag:
                body["tag"] = tag
            #print(body)
            #exit(0)

            # max_retries=1: no automatic retry on a withdraw call — an
            # ambiguous timeout/error here must NOT be silently retried,
            # since the first attempt may have already succeeded server-side.
            # Check deposit/withdraw history before manually retrying.
            data = await self._request(
                "POST",
                "/v5/asset/withdraw/create",
                body,
                signed=True,
                max_retries=1,
                use_ip_bounded_api=True
            )
            withdraw_id = data.get("result", {}).get("id")
            log(f"[WITHDRAW] {coin} {amount} via {chain} → {address} | id={withdraw_id}")
            return withdraw_id
        except Exception as e:
            log(f"[WITHDRAW] Failed to withdraw {amount} {coin} via {chain}: {e}")
            
            return None

    async def poll_deposit_confirmed(
        self,
        coin:            str,
        expected_amount: float,
        timeout_secs:    int   = 1800,
        poll_interval:   int   = 10,
    ) -> bool:
        """
        """
        deadline = time.time() + timeout_secs
        log(f"[POLL DEPOSIT] Waiting for {expected_amount} {coin} to land on Bybit...")

        while time.time() < deadline:
            try:
                data = await self._request(
                    "GET",
                    "/v5/asset/deposit/query-record",
                    {"coin": coin.upper(), "limit": 10},
                    signed=True,
                )
                records = data.get("result", {}).get("rows", [])
                for record in records:
                    if record.get("coin") != coin.upper():
                        continue
                    if float(record.get("amount", 0)) >= expected_amount * 0.99:
                        status = int(record.get("status", 0))
                        if status == 3:
                            log(f"[POLL DEPOSIT] ✅ {coin} deposit confirmed on Bybit")
                            return True
                        elif status == 4:
                            log(f"[POLL DEPOSIT] ❌ {coin} deposit failed on Bybit")
                            return False
                        else:
                            log(f"[POLL DEPOSIT] {coin} deposit status={status}, still waiting...")
            except Exception as e:
                log(f"[POLL DEPOSIT] Error polling Bybit deposit: {e}")

            await asyncio.sleep(poll_interval)

        log(f"[POLL DEPOSIT] ⏰ Timeout waiting for {coin} deposit on Bybit")
        return False

    async def withdraw_usdt(
        self,
        destination_exchange: str,
        amount:               str,
        chain:                str = "APT",
    ) -> str | None:
        address = self._usdt_deposit_addresses.get(destination_exchange, {}).get(chain)
        if not address:
            log(f"[USDT TRANSFER] No predefined USDT {chain} address for {destination_exchange}")
            return None
        return await self.withdraw_coin("USDT", chain, address, amount)

    async def poll_usdt_deposit_confirmed(
        self,
        expected_amount: float,
        timeout_secs:    int = 1800,
        poll_interval:   int = 30,
    ) -> bool:
        return await self.poll_deposit_confirmed(
            "USDT", expected_amount, timeout_secs, poll_interval
        )
