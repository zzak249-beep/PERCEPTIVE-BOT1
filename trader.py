import asyncio
import logging
import math
from typing import Dict, Optional
import aiohttp

import config
import telegram_notifier as tg
from bingx_client import BingXClient
from strategy import ZigZagSignal, parse_klines

log = logging.getLogger("trader")


class Position:
    def __init__(self, symbol: str, side: str, entry: float,
                 sl: float, tp: float, qty: float):
        self.symbol = symbol
        self.side   = side
        self.entry  = entry
        self.sl     = sl
        self.tp     = tp
        self.qty    = qty
        self.closed = False


class Trader:
    def __init__(self, client: BingXClient, session: aiohttp.ClientSession):
        self.client       = client
        self.session      = session
        self.strategy     = ZigZagSignal()
        self.positions: Dict[str, Position] = {}
        self.daily_pnl    = 0.0
        self.daily_trades = 0
        self.daily_wins   = 0
        self.paused       = False
        # Cache de posiciones vivas (se actualiza una vez por ciclo en main)
        self._live_position_cache: set = set()

    # ──────────────────────────────────────────────────────────────────
    # Llamar UNA VEZ por ciclo desde main.py antes de process_pair
    # ──────────────────────────────────────────────────────────────────
    async def refresh_live_positions(self):
        try:
            live = await self.client.get_positions()
            self._live_position_cache = {
                p.get("symbol", "")
                for p in live
                if self._pos_amt(p) != 0
            }
        except Exception as e:
            log.error(f"refresh_live_positions error: {e}")

    @staticmethod
    def _pos_amt(p: dict) -> float:
        """BingX usa positionAmt O posAmt según versión."""
        for key in ("positionAmt", "posAmt", "availableAmt"):
            try:
                return float(p.get(key, 0))
            except (TypeError, ValueError):
                continue
        return 0.0

    # ──────────────────────────────────────────────────────────────────
    # MAIN LOOP PER PAIR  (balance se pasa desde main.py)
    # ──────────────────────────────────────────────────────────────────
    async def process_pair(self, symbol: str, balance: float):
        if self.paused:
            return

        # ── Check daily loss limit ──────────────────────────────────
        if balance > 0:
            loss_pct = (self.daily_pnl / balance) * 100
            if loss_pct <= -config.MAX_DAILY_LOSS:
                self.paused = True
                await tg.daily_loss_limit(self.session, self.daily_pnl, config.MAX_DAILY_LOSS, balance)
                return

        # ── Ya estamos en posición → monitorear ────────────────────
        pos = self.positions.get(symbol)
        if pos and not pos.closed:
            await self._monitor_position(symbol)
            return

        # ── Límite de posiciones simultáneas ────────────────────────
        open_count = sum(1 for p in self.positions.values() if not p.closed)
        if open_count >= config.MAX_POSITIONS:
            return

        # ── Fetch klines ────────────────────────────────────────────
        raw = await self.client.get_klines(symbol, config.TIMEFRAME, config.KLINE_LIMIT)
        if not raw or len(raw) < 30:
            return

        opens, highs, lows, closes, volumes = parse_klines(raw)
        if len(closes) < 30:
            return

        # ── Calcular señal ───────────────────────────────────────────
        sig = self.strategy.compute(opens, highs, lows, closes, volumes)
        if sig is None:
            return

        # ── Señal → entrada ─────────────────────────────────────────
        await tg.signal_detected(
            self.session, symbol, sig["side"],
            sig["entry"], sig["peak"], sig["valley"], sig["vol_ratio"]
        )
        await self._enter_trade(symbol, sig, balance)

    # ──────────────────────────────────────────────────────────────────
    # ENTRADA
    # ──────────────────────────────────────────────────────────────────
    async def _enter_trade(self, symbol: str, sig: dict, balance: float):
        try:
            entry = sig["entry"]
            sl    = sig["sl"]
            tp    = sig["tp"]
            side  = sig["side"]
            atr   = sig["atr"]

            sl_dist = abs(entry - sl)
            if sl_dist == 0 or entry == 0:
                log.warning(f"[{symbol}] SL dist=0, ignorando señal")
                return

            # Sizing: riesgo fijo sobre balance
            risk_usdt = balance * (config.RISK_PCT / 100)
            qty = (risk_usdt * config.LEVERAGE) / entry
            qty = self._floor_qty(qty)
            if qty <= 0:
                log.warning(f"[{symbol}] qty<=0 tras redondeo, ignorando")
                return

            rr = abs(tp - entry) / sl_dist

            # Leverage
            await self.client.set_leverage(symbol, config.LEVERAGE)
            await asyncio.sleep(0.15)

            # Orden market con SL/TP nativos en BingX
            resp = await self.client.place_market_order(symbol, side, qty, sl, tp)

            code = resp.get("code", -1)
            if code != 0:
                err = resp.get("msg", str(resp))
                log.error(f"[{symbol}] Order rejected (code={code}): {err}")
                await tg.error_alert(self.session, f"[{symbol}] Order rejected: {err}")
                return

            self.positions[symbol] = Position(symbol, side, entry, sl, tp, qty)
            self._live_position_cache.add(symbol)
            self.daily_trades += 1

            await tg.trade_entry(
                self.session, symbol, side, entry, sl, tp, qty, balance, rr, atr
            )
            log.info(f"✅ [{symbol}] {side} @ {entry:.6g} | SL={sl:.6g} TP={tp:.6g} qty={qty:.4f}")

        except Exception as e:
            log.exception(f"[{symbol}] _enter_trade error: {e}")
            await tg.error_alert(self.session, f"[{symbol}] Entry error: {e}")

    # ──────────────────────────────────────────────────────────────────
    # MONITOREO DE POSICIÓN
    # ──────────────────────────────────────────────────────────────────
    async def _monitor_position(self, symbol: str):
        try:
            pos = self.positions.get(symbol)
            if pos is None or pos.closed:
                return

            # Si ya no aparece en el cache de vivas → cerrada por SL/TP
            if symbol not in self._live_position_cache:
                pos.closed = True

                # Precio de salida: última vela cerrada via parse_klines
                raw = await self.client.get_klines(symbol, config.TIMEFRAME, 3)
                _, _, _, C, _ = parse_klines(raw)
                # C[-2] = última vela cerrada; si falla usar entry
                exit_price = float(C[-2]) if len(C) >= 2 else pos.entry

                if pos.side == "BUY":
                    pnl_pts = exit_price - pos.entry
                else:
                    pnl_pts = pos.entry - exit_price

                pnl     = pnl_pts * pos.qty * config.LEVERAGE
                pnl_pct = (pnl_pts / pos.entry) * 100 * config.LEVERAGE

                # Determinar motivo
                dist_tp = abs(exit_price - pos.tp)
                dist_sl = abs(exit_price - pos.sl)
                if dist_tp < dist_sl:
                    reason = "TAKE PROFIT ✅"
                    self.daily_wins += 1
                else:
                    reason = "STOP LOSS ❌"

                self.daily_pnl += pnl

                await tg.trade_exit(
                    self.session, symbol, pos.side,
                    pos.entry, exit_price, pnl, pnl_pct, reason
                )
                log.info(f"[{symbol}] Cerrada | PnL={pnl:+.4f} USDT | {reason}")

        except Exception as e:
            log.error(f"[{symbol}] _monitor_position error: {e}")

    # ──────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _floor_qty(qty: float) -> float:
        """Trunca a 3 decimales (floor, no round) para no exceder balance."""
        return math.floor(qty * 1000) / 1000

    def reset_daily(self):
        self.daily_pnl    = 0.0
        self.daily_trades = 0
        self.daily_wins   = 0
        self.paused       = False
        log.info("🔄 Contadores diarios reseteados")
