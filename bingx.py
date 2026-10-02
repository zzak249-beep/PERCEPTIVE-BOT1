import hashlib
import hmac
import logging
import math
import time

import requests

log = logging.getLogger("bingx")
BASE = "https://open-api.bingx.com"


class BingXError(Exception):
    pass


class BingX:
    def __init__(self, key, secret, mode="hedge"):
        self.key, self.secret, self.mode = key, secret, mode
        self.s = requests.Session()
        self.s.headers["X-BX-APIKEY"] = key or ""

    # ---------- núcleo ----------
    def _req(self, method, path, params=None, signed=False):
        params = dict(params or {})
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 10000
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        if signed:
            sig = hmac.new(self.secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
            qs += f"&signature={sig}"
        url = f"{BASE}{path}" + (f"?{qs}" if qs else "")
        attempts = 3 if method == "GET" else 1
        last = None
        for a in range(attempts):
            try:
                r = self.s.request(method, url, timeout=15)
                if r.status_code == 429:
                    time.sleep(2 + a * 2)
                    continue
                data = r.json()
            except Exception as e:  # red / json
                last = e
                time.sleep(1 + a)
                continue
            if isinstance(data, dict) and data.get("code", 0) not in (0, None):
                raise BingXError(f"{path} -> {data.get('code')}: {data.get('msg')}")
            return data.get("data") if isinstance(data, dict) else data
        raise BingXError(f"{path} falló: {last}")

    def ps(self, direction):
        if self.mode == "oneway":
            return "BOTH"
        return "LONG" if direction == "long" else "SHORT"

    # ---------- mercado ----------
    def contracts(self):
        out = {}
        for c in self._req("GET", "/openApi/swap/v2/quote/contracts") or []:
            sym = c.get("symbol", "")
            if not sym.endswith("-USDT"):
                continue
            if c.get("status") not in (1, "1", None):
                continue
            out[sym] = {
                "qty_prec": int(c.get("quantityPrecision", 3)),
                "px_prec": int(c.get("pricePrecision", 4)),
                "min_qty": float(c.get("tradeMinQuantity", 0) or 0),
            }
        return out

    def tickers(self):
        return self._req("GET", "/openApi/swap/v2/quote/ticker") or []

    def klines(self, symbol, interval, limit):
        data = self._req("GET", "/openApi/swap/v3/quote/klines",
                         {"symbol": symbol, "interval": interval, "limit": limit}) or []
        out = [{"t": int(k["time"]), "o": float(k["open"]), "h": float(k["high"]),
                "l": float(k["low"]), "c": float(k["close"]), "v": float(k["volume"])}
               for k in data]
        out.sort(key=lambda x: x["t"])
        return out

    def price(self, symbol):
        d = self._req("GET", "/openApi/swap/v2/quote/price", {"symbol": symbol})
        if isinstance(d, list):
            d = d[0]
        return float(d["price"])

    # ---------- cuenta ----------
    def equity(self):
        d = self._req("GET", "/openApi/swap/v2/user/balance", signed=True)
        b = d.get("balance", d) if isinstance(d, dict) else d
        return float(b.get("equity") or b.get("balance") or 0)

    def positions(self):
        return self._req("GET", "/openApi/swap/v2/user/positions", signed=True) or []

    def set_leverage(self, symbol, leverage):
        for side in ("LONG", "SHORT"):
            try:
                self._req("POST", "/openApi/swap/v2/trade/leverage",
                          {"symbol": symbol, "side": side, "leverage": leverage}, signed=True)
            except BingXError as e:
                log.warning("leverage %s %s: %s", symbol, side, e)

    def set_margin(self, symbol, mtype):
        try:
            self._req("POST", "/openApi/swap/v2/trade/marginType",
                      {"symbol": symbol, "marginType": mtype}, signed=True)
        except BingXError as e:
            log.info("marginType %s: %s", symbol, e)

    # ---------- órdenes ----------
    def order(self, symbol, side, direction, otype, qty, stop=None, reduce=False):
        """side BUY/SELL; direction = 'long'/'short' de la POSICIÓN afectada."""
        p = {"symbol": symbol, "side": side, "positionSide": self.ps(direction),
             "type": otype, "quantity": qty}
        if stop is not None:
            p["stopPrice"] = stop
            p["workingType"] = "MARK_PRICE"
        if reduce and self.mode == "oneway":
            p["reduceOnly"] = "true"
        return self._req("POST", "/openApi/swap/v2/trade/order", p, signed=True)

    def cancel_order(self, symbol, order_id):
        try:
            self._req("DELETE", "/openApi/swap/v2/trade/order",
                      {"symbol": symbol, "orderId": order_id}, signed=True)
        except BingXError as e:
            log.info("cancel_order %s %s: %s", symbol, order_id, e)

    def cancel_all(self, symbol):
        try:
            self._req("DELETE", "/openApi/swap/v2/trade/allOpenOrders",
                      {"symbol": symbol}, signed=True)
        except BingXError as e:
            log.warning("cancel_all %s: %s", symbol, e)


def floor_to(x, prec):
    f = 10 ** prec
    return math.floor(x * f + 1e-9) / f


def fmt(x, prec):
    return f"{x:.{prec}f}"
