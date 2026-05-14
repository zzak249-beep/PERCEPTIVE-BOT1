"""
bingx_client.py — Cliente BingX Perpetual Futures
FIX: Soporte modo ONE-WAY (sin positionSide)
FIX: Firma HMAC correcta para POST
FIX: set_leverage sin parámetro side (one-way)
FIX: Validación de cantidad mínima
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
        })
        mode = "HEDGE" if HEDGE_MODE else "ONE-WAY"
        logger.info(f"BingXClient iniciado en modo {mode}")

    # ──────────────────────────────────────────────────────
    # Firma HMAC-SHA256
    # ──────────────────────────────────────────────────────
    def _timestamp(self) -> int:
        return int(time.time() * 1000)

    def _sign(self, payload: str) -> str:
        return hmac.new(
            self.secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _signed_get_params(self, params: dict) -> dict:
        """Para GET: añade timestamp y firma al query string."""
        params = dict(params)
        params["timestamp"] = self._timestamp()
        raw = urlencode(sorted(params.items()))
        params["signature"] = self._sign(raw)
        return params

    def _signed_post_body(self, params: dict) -> str:
        """
        Para POST: BingX exige firma sobre el body sin signature,
        luego añade signature al body final.
        """
        params = dict(params)
        params["timestamp"] = self._timestamp()
        # Firma sobre params ordenados sin signature
        raw = urlencode(sorted(params.items()))
        params["signature"] = self._sign(raw)
        return urlencode(params)

    # ──────────────────────────────────────────────────────
    # HTTP helpers
    # ──────────────────────────────────────────────────────
    def _get(self, endpoint: str, params: dict = None, signed: bool = False) -> dict:
        params = params or {}
        if signed:
            params = self._signed_get_params(params)
        try:
            resp = self.session.get(
                f"{self.base_url}{endpoint}", params=params, timeout=10
            )
            return resp.json()
        except Exception as e:
            logger.error(f"GET {endpoint} error: {e}")
            return {"code": -1, "msg": str(e)}

    def _post(self, endpoint: str, params: dict) -> dict:
        body = self._signed_post_body(params)
        try:
            resp = self.session.post(
                f"{self.base_url}{endpoint}",
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.warning(f"POST {endpoint} → code={data.get('code')} msg={data.get('msg')}")
            return data
        except Exception as e:
            logger.error(f"POST {endpoint} error: {e}")
            return {"code": -1, "msg": str(e)}

    # ──────────────────────────────────────────────────────
    # Datos de mercado
    # ──────────────────────────────────────────────────────
    def get_klines(self, symbol: str, interval: str, limit: int = 150) -> pd.DataFrame:
        """
        Retorna DataFrame OHLCV.
        NOTA: el último elemento [-1] es la vela actual aún abierta.
              Usar [-2] como última vela CERRADA.
        """
        data = self._get(
            "/openApi/swap/v2/quote/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        if data.get("code") != 0 or not data.get("data"):
            msg = data.get("msg", "")
            if "pause" in msg.lower():
                logger.warning(f"[PAUSED] {symbol}: {msg}")
                return pd.DataFrame({"_paused": [True]})  # señal especial
            logger.debug(f"Klines vacías {symbol}: {msg}")
            return pd.DataFrame()

        raw = data["data"]
        # BingX puede devolver lista de dicts o lista de listas
        if isinstance(raw[0], dict):
            df = pd.DataFrame(raw)
            # renombrar si las claves difieren
            rename = {"t": "time", "o": "open", "h": "high",
                      "l": "low", "c": "close", "v": "volume"}
            df.rename(columns=rename, inplace=True)
        else:
            df = pd.DataFrame(raw, columns=["time", "open", "high", "low", "close", "volume"])

        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "time" in df.columns:
            df["time"] = pd.to_numeric(df["time"], errors="coerce")
            df.sort_values("time", inplace=True)
            df.reset_index(drop=True, inplace=True)

        # Descartar la vela actual (aún abierta) — usar solo velas cerradas
        df = df.iloc[:-1].copy()
        return df

    def get_24h_tickers(self) -> list:
        data = self._get("/openApi/swap/v2/quote/ticker")
        if data.get("code") != 0:
            logger.error(f"Tickers error: {data.get('msg')}")
            return []
        return data.get("data", [])

    def get_symbol_price(self, symbol: str) -> float:
        data = self._get("/openApi/swap/v2/quote/price", {"symbol": symbol})
        try:
            return float(data["data"]["price"])
        except Exception:
            return 0.0

    # ──────────────────────────────────────────────────────
    # Cuenta
    # ──────────────────────────────────────────────────────
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
        return [
            p for p in data.get("data", [])
            if float(p.get("positionAmt", 0)) != 0
        ]

    # ──────────────────────────────────────────────────────
    # Apalancamiento
    # ──────────────────────────────────────────────────────
    def set_leverage(self, symbol: str, leverage: int):
        """
        FIX: En one-way mode NO se envía 'side'.
             En hedge mode se envía 'side=LONG' y 'side=SHORT'.
        """
        if ONE_WAY_MODE:
            res = self._post("/openApi/swap/v2/trade/leverage", {
                "symbol": symbol, "leverage": leverage,
            })
            logger.debug(f"Leverage {symbol} x{leverage}: {res.get('code')}")
        else:
            for side in ("LONG", "SHORT"):
                self._post("/openApi/swap/v2/trade/leverage", {
                    "symbol": symbol, "side": side, "leverage": leverage,
                })

    # ──────────────────────────────────────────────────────
    # Órdenes
    # ──────────────────────────────────────────────────────
    def place_order(
        self,
        symbol: str,
        side: str,           # "BUY" o "SELL"
        position_side: str,  # "LONG" o "SHORT" (solo hedge)
        quantity: float,
        leverage: int = 5,
    ) -> dict:
        """
        Abre posición de mercado.
        FIX ONE-WAY: omite positionSide, usa reduceOnly=false.
        """
        if DRY_RUN:
            logger.info(f"[DRY] place_order {side} {symbol} qty={quantity:.4f}")
            return {"code": 0, "data": {"orderId": "DRY"}}

        self.set_leverage(symbol, leverage)

        params = {
            "symbol":   symbol,
            "side":     side,
            "type":     "MARKET",
            "quantity": round(quantity, 4),
        }

        if HEDGE_MODE:
            params["positionSide"] = position_side
        # ONE-WAY: sin positionSide

        result = self._post("/openApi/swap/v2/trade/order", params)
        logger.info(f"[ORDER] {side} {symbol} qty={quantity:.4f} → code={result.get('code')} {result.get('msg','')}")
        return result

    def place_stop_order(
        self,
        symbol: str,
        side: str,
        position_side: str,
        stop_price: float,
        quantity: float,
        order_type: str = "STOP_MARKET",
    ) -> dict:
        """
        Coloca SL o TP.
        FIX ONE-WAY: usa reduceOnly=true en lugar de positionSide.
        """
        if DRY_RUN:
            return {"code": 0}

        params = {
            "symbol":      symbol,
            "side":        side,
            "type":        order_type,
            "stopPrice":   round(stop_price, 8),
            "quantity":    round(quantity, 4),
            "workingType": "MARK_PRICE",
        }

        if HEDGE_MODE:
            params["positionSide"] = position_side
        else:
            params["reduceOnly"] = "true"

        result = self._post("/openApi/swap/v2/trade/order", params)
        logger.debug(f"[STOP] {order_type} {symbol} stop={stop_price:.6f} → code={result.get('code')}")
        return result

    def close_position(self, symbol: str, position_side: str, quantity: float) -> dict:
        """
        Cierra posición a mercado.
        FIX ONE-WAY: usa reduceOnly=true.
        """
        if DRY_RUN:
            return {"code": 0}

        close_side = "SELL" if position_side == "LONG" else "BUY"
        params = {
            "symbol":   symbol,
            "side":     close_side,
            "type":     "MARKET",
            "quantity": round(quantity, 4),
        }

        if HEDGE_MODE:
            params["positionSide"] = position_side
        else:
            params["reduceOnly"] = "true"

        return self._post("/openApi/swap/v2/trade/order", params)

    def cancel_all_orders(self, symbol: str) -> dict:
        if DRY_RUN:
            return {"code": 0}
        return self._post(
            "/openApi/swap/v2/trade/allOpenOrders", {"symbol": symbol}
        )

    # ──────────────────────────────────────────────────────
    # Validación de cantidad mínima
    # ──────────────────────────────────────────────────────
    def validate_qty(self, qty: float, price: float) -> tuple:
        """(qty_final, ok, motivo)"""
        notional = qty * price
        if notional < MIN_ORDER_USDT:
            return 0.0, False, f"Notional ${notional:.2f} < mínimo ${MIN_ORDER_USDT}"
        return qty, True, "OK"
