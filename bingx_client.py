"""
bingx_client.py — BingX Perpetual Futures
FIX CRÍTICO: Firma HMAC correcta según docs oficiales BingX
  - timestamp + signature van SIEMPRE en query string (GET y POST)
  - Para POST: params del body en query string para la firma, body vacío
  - Ref: https://bingx-api.github.io/docs/#/en-us/spot/account-api.html
"""
import hashlib
import hmac
import logging
import time

import pandas as pd
import requests
from urllib.parse import urlencode

from config import (
    BINGX_API_KEY, BINGX_SECRET_KEY, BINGX_BASE_URL,
    BINGX_MODE, MIN_ORDER_USDT, DRY_RUN,
)

logger = logging.getLogger(__name__)

HEDGE_MODE   = BINGX_MODE.lower() == "hedge"
ONE_WAY_MODE = not HEDGE_MODE


class BingXClient:
    def __init__(self):
        self.api_key    = BINGX_API_KEY
        self.secret_key = BINGX_SECRET_KEY
        self.base_url   = BINGX_BASE_URL
        self.session    = requests.Session()
        self.session.headers.update({
            "X-BX-APIKEY": self.api_key,
            "Content-Type": "application/json",
        })
        mode = "HEDGE" if HEDGE_MODE else "ONE-WAY"
        logger.info(f"BingXClient modo {mode}")

    # ── Firma ──────────────────────────────────────────────
    def _timestamp(self) -> str:
        return str(int(time.time() * 1000))

    def _sign(self, query_string: str) -> str:
        """HMAC-SHA256 sobre el query string completo."""
        return hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _build_signed_query(self, params: dict) -> str:
        """
        Construye query string con timestamp y signature.
        BingX: firma = HMAC(todos los params excepto signature, ordenados).
        """
        params = {k: str(v) for k, v in params.items()}
        params["timestamp"] = self._timestamp()
        # Ordenar alfabéticamente y construir query string
        qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        sig = self._sign(qs)
        return f"{qs}&signature={sig}"

    # ── HTTP ───────────────────────────────────────────────
    def _get(self, endpoint: str, params: dict = None, signed: bool = False) -> dict:
        params = params or {}
        try:
            if signed:
                qs  = self._build_signed_query(params)
                url = f"{self.base_url}{endpoint}?{qs}"
                resp = self.session.get(url, timeout=10)
            else:
                resp = self.session.get(
                    f"{self.base_url}{endpoint}", params=params, timeout=10
                )
            return resp.json()
        except Exception as e:
            logger.error(f"GET {endpoint}: {e}")
            return {"code": -1, "msg": str(e)}

    def _post(self, endpoint: str, params: dict) -> dict:
        """
        BingX POST: todos los params (incluyendo timestamp y signature)
        van en el query string de la URL. Body vacío.
        """
        try:
            qs   = self._build_signed_query(params)
            url  = f"{self.base_url}{endpoint}?{qs}"
            resp = self.session.post(url, timeout=10)
            data = resp.json()
            if data.get("code") != 0:
                logger.warning(
                    f"POST {endpoint} code={data.get('code')} "
                    f"msg={data.get('msg','')[:120]}"
                )
            return data
        except Exception as e:
            logger.error(f"POST {endpoint}: {e}")
            return {"code": -1, "msg": str(e)}

    # ── Mercado (sin firma) ────────────────────────────────
    def get_klines(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        data = self._get(
            "/openApi/swap/v2/quote/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        if data.get("code") != 0 or not data.get("data"):
            msg = data.get("msg", "")
            if "pause" in msg.lower():
                logger.warning(f"[PAUSED] {symbol}")
                return pd.DataFrame({"_paused": [True]})
            logger.debug(f"Klines vacías {symbol}: {msg}")
            return pd.DataFrame()

        raw = data["data"]
        if isinstance(raw[0], dict):
            df = pd.DataFrame(raw)
            df.rename(columns={"t":"time","o":"open","h":"high",
                                "l":"low","c":"close","v":"volume"}, inplace=True)
        else:
            df = pd.DataFrame(raw, columns=["time","open","high","low","close","volume"])

        for col in ["open","high","low","close","volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "time" in df.columns:
            df["time"] = pd.to_numeric(df["time"], errors="coerce")
            df.sort_values("time", inplace=True)
            df.reset_index(drop=True, inplace=True)

        return df.iloc[:-1].copy()   # descartar vela abierta actual

    def get_24h_tickers(self) -> list:
        data = self._get("/openApi/swap/v2/quote/ticker")
        if data.get("code") != 0:
            logger.error(f"Tickers: {data.get('msg')}")
            return []
        return data.get("data", [])

    def get_symbol_price(self, symbol: str) -> float:
        data = self._get("/openApi/swap/v2/quote/price", {"symbol": symbol})
        try:
            return float(data["data"]["price"])
        except Exception:
            return 0.0

    # ── Cuenta (con firma) ─────────────────────────────────
    def get_balance(self) -> float:
        data = self._get(
            "/openApi/swap/v2/user/balance", {"currency": "USDT"}, signed=True
        )
        try:
            return float(data["data"]["balance"]["availableMargin"])
        except Exception:
            logger.error(f"Balance error: {data}")
            return 0.0

    def get_open_positions(self) -> list:
        data = self._get("/openApi/swap/v2/user/positions", {}, signed=True)
        if data.get("code") != 0:
            return []
        return [p for p in data.get("data", [])
                if float(p.get("positionAmt", 0)) != 0]

    # ── Apalancamiento ─────────────────────────────────────
    def set_leverage(self, symbol: str, leverage: int):
        if ONE_WAY_MODE:
            res = self._post("/openApi/swap/v2/trade/leverage",
                             {"symbol": symbol, "leverage": leverage})
            logger.debug(f"Leverage {symbol} x{leverage}: {res.get('code')}")
        else:
            for side in ("LONG", "SHORT"):
                self._post("/openApi/swap/v2/trade/leverage",
                           {"symbol": symbol, "side": side, "leverage": leverage})

    # ── Órdenes ───────────────────────────────────────────
    def place_order(self, symbol: str, side: str, position_side: str,
                    quantity: float, leverage: int = 5) -> dict:
        if DRY_RUN:
            logger.info(f"[DRY] place_order {side} {symbol} qty={quantity:.4f}")
            return {"code": 0, "data": {"orderId": "DRY"}}

        self.set_leverage(symbol, leverage)

        params = {
            "symbol":   symbol,
            "side":     side,
            "type":     "MARKET",
            "quantity": f"{quantity:.4f}",
        }
        if HEDGE_MODE:
            params["positionSide"] = position_side

        result = self._post("/openApi/swap/v2/trade/order", params)
        logger.info(
            f"[ORDER] {side} {symbol} qty={quantity:.4f} "
            f"→ code={result.get('code')} {result.get('msg','')[:60]}"
        )
        return result

    def place_stop_order(self, symbol: str, side: str, position_side: str,
                         stop_price: float, quantity: float,
                         order_type: str = "STOP_MARKET") -> dict:
        if DRY_RUN:
            return {"code": 0}

        params = {
            "symbol":      symbol,
            "side":        side,
            "type":        order_type,
            "stopPrice":   f"{stop_price:.8f}",
            "quantity":    f"{quantity:.4f}",
            "workingType": "MARK_PRICE",
        }
        if HEDGE_MODE:
            params["positionSide"] = position_side
        else:
            params["reduceOnly"] = "true"

        return self._post("/openApi/swap/v2/trade/order", params)

    def close_position(self, symbol: str, position_side: str,
                       quantity: float) -> dict:
        if DRY_RUN:
            return {"code": 0}

        close_side = "SELL" if position_side == "LONG" else "BUY"
        params = {
            "symbol":   symbol,
            "side":     close_side,
            "type":     "MARKET",
            "quantity": f"{quantity:.4f}",
        }
        if HEDGE_MODE:
            params["positionSide"] = position_side
        else:
            params["reduceOnly"] = "true"

        return self._post("/openApi/swap/v2/trade/order", params)

    def cancel_all_orders(self, symbol: str) -> dict:
        if DRY_RUN:
            return {"code": 0}
        return self._post("/openApi/swap/v2/trade/allOpenOrders",
                          {"symbol": symbol})

    def validate_qty(self, qty: float, price: float) -> tuple:
        notional = qty * price
        if notional < MIN_ORDER_USDT:
            return 0.0, False, f"Notional ${notional:.2f} < min ${MIN_ORDER_USDT}"
        return qty, True, "OK"
