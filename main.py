"""
main.py — V35 PROFITABLE EDITION
Mejoras: trailing stop, mejor logging, análisis integrado
"""
import logging, os, sys, time
from collections import Counter
from datetime import datetime, timezone
import schedule

from bingx_client       import BingXClient
from config             import (BINGX_MODE, CANDLE_INTERVAL, DATA_DIR, DRY_RUN,
                                 LEVERAGE, MAX_OPEN_TRADES, TIME_STOP_CANDLES,
                                 TOP_N_SYMBOLS, VOL_MULT, ADX_MIN)
from learning_engine    import LearningEngine
from risk_manager       import RiskManager
from hourly_reviewer    import HourlyReviewer
from scanner            import MarketScanner
from strategy           import StrategyV35
from telegram_notifier  import TelegramNotifier

os.makedirs(DATA_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler(f"{DATA_DIR}/bot.log")],
)
logger = logging.getLogger("SniperV35")


class SniperBotV35:
    def __init__(self):
        logger.info("=== Sniper Bot V35 PROFITABLE EDITION ===")
        self.client   = BingXClient()
        self.strategy = StrategyV35()
        self.telegram = TelegramNotifier()
        self.scanner  = MarketScanner(self.client)
        self.risk     = RiskManager()
        self.learning = LearningEngine(telegram=self.telegram)
        self.reviewer = HourlyReviewer(self.learning, self.telegram, self.client)
        self._active: dict      = {}
        self._top_symbols: list = []
        self._tick: int         = 0
        self._all_reasons       = Counter()
        self._best_diag: dict   = {}

    # ── Startup ───────────────────────────────────────────
    def startup(self):
        balance = self.client.get_balance()
        self._top_symbols = self.scanner.get_top_symbols(TOP_N_SYMBOLS)
        stats = self.learning.get_stats(today_only=False)
        logger.info(
            f"Balance=${balance:.2f} | Pares={len(self._top_symbols)} | "
            f"DRY={DRY_RUN} | MODE={BINGX_MODE.upper()} | "
            f"ADX≥{self.learning.params['adx_min']} VOL≥{VOL_MULT}x | "
            f"Histórico: {stats['total']} trades WR={stats['winrate']}%"
        )
        self.telegram.notify_startup(balance, len(self._top_symbols), dry_run=DRY_RUN)

    # ── Tareas programadas ────────────────────────────────
    def hourly_task(self):
        try:
            self.reviewer.run(self._active)
        except Exception as e:
            logger.error(f"Hourly error: {e}")
        self._top_symbols = self.scanner.get_top_symbols(TOP_N_SYMBOLS)
        self.telegram.notify_scan_results(self._top_symbols, self.scanner)

    def daily_report(self):
        self.telegram.notify_daily_report(
            self.learning.get_stats(today_only=True))

    # ── Tick cada 3 min ───────────────────────────────────
    def tick(self):
        self._tick += 1
        symbols  = [s["symbol"] for s in self._top_symbols]
        balance  = self.client.get_balance()
        reasons  = Counter()
        checked  = 0

        for symbol in symbols:
            try:
                df = self.client.get_klines(symbol, CANDLE_INTERVAL, limit=150)
                if not df.empty and "_paused" in df.columns:
                    self.scanner.mark_paused(symbol)
                    reasons["pausado"] += 1
                    continue
                if df.empty or len(df) < 30:
                    reasons["pocas_velas"] += 1
                    continue
                checked += 1

                if symbol in self._active:
                    self._manage_open(symbol, df)
                    continue

                signal = self.strategy.get_signal(
                    df, adx_override=self.learning.params["adx_min"])

                if signal["signal"] == "NONE":
                    prefix = signal.get("reason","?").split(" ")[0][:18]
                    reasons[prefix] += 1
                    diag  = self.strategy.get_diagnostics(df)
                    score = diag.get("adx",0) + diag.get("vol_ratio",0)*10
                    if score > self._best_diag.get("_score",0):
                        diag["_score"] = score
                        diag["_sym"]   = symbol
                        self._best_diag = diag
                    continue

                logger.info(
                    f"[{symbol}] 🎯 {signal['signal']} "
                    f"R:R={signal.get('rr','?')} "
                    f"ADX={signal['adx']} RSI={signal.get('rsi','?')} "
                    f"vol={signal['vol_ratio']}x"
                )

                ok, lreason = self.learning.should_take(signal)
                if not ok:
                    logger.info(f"[{symbol}] Learning: {lreason}")
                    reasons["aprendizaje"] += 1
                    continue

                res = self._open_trade(symbol, signal, balance)
                if res == "OPENED":
                    balance = self.client.get_balance()
                time.sleep(0.3)

            except Exception as e:
                logger.error(f"[{symbol}] tick error: {e}")

        # Resumen de consola
        top_r = ", ".join(f"{k}={v}" for k,v in reasons.most_common(3))
        logger.info(f"TICK#{self._tick} checked={checked} open={len(self._active)}/{MAX_OPEN_TRADES} "
                    f"bal=${balance:.2f} | {top_r or 'SIN_RECHAZOS'}")

        self._all_reasons.update(reasons)

        # Telegram diagnóstico cada 10 ticks
        if self._tick % 10 == 0:
            self.telegram.notify_tick_status(
                self._tick, balance, len(self._active),
                dict(self._all_reasons), self._best_diag)
            self._all_reasons.clear()
            self._best_diag = {}

    # ── Abrir trade ───────────────────────────────────────
    def _open_trade(self, symbol: str, signal: dict, balance: float) -> str:
        ok, reason = self.risk.can_open(symbol)
        if not ok:
            return "BLOCKED"

        qty = self.risk.calc_quantity(balance, signal["entry"], signal["sl"])
        if qty <= 0:
            return "REJECTED"

        qty, ok, rq = self.client.validate_qty(qty, signal["entry"])
        if not ok:
            logger.warning(f"[{symbol}] {rq}")
            return "REJECTED"

        ps  = "LONG"  if signal["signal"] == "LONG" else "SHORT"
        os_ = "BUY"   if signal["signal"] == "LONG" else "SELL"
        cs  = "SELL"  if signal["signal"] == "LONG" else "BUY"

        res = self.client.place_order(
            symbol=symbol, side=os_, position_side=ps,
            quantity=qty, leverage=LEVERAGE)
        if res.get("code") != 0:
            logger.error(f"[{symbol}] BingX rechazó: {res}")
            return "REJECTED"

        self.client.place_stop_order(symbol, cs, ps,
            stop_price=signal["sl"], quantity=qty, order_type="STOP_MARKET")
        self.client.place_stop_order(symbol, cs, ps,
            stop_price=signal["tp"], quantity=qty, order_type="TAKE_PROFIT_MARKET")

        meta = {
            "signal": signal, "qty": qty, "position_side": ps,
            "open_time": datetime.now(timezone.utc), "candle_count": 0,
            "position_usdt": qty * signal["entry"], "leverage": LEVERAGE,
            "sl_current": signal["sl"],   # SL actual (puede moverse con trailing)
        }
        self._active[symbol] = meta
        self.risk.register(symbol, meta)
        self.telegram.notify_trade_open(symbol, signal, meta)
        logger.info(f"[{symbol}] ✅ {signal['signal']} qty={qty:.4f} "
                    f"entry={signal['entry']:.6f} R:R={signal.get('rr','?')}")
        return "OPENED"

    # ── Gestionar trade abierto ───────────────────────────
    def _manage_open(self, symbol: str, df):
        trade = self._active.get(symbol)
        if not trade:
            return

        trade["candle_count"] += 1
        price  = float(df["close"].iloc[-1])
        signal = trade["signal"]

        # Verificar si BingX cerró la posición (TP/SL alcanzado)
        positions  = self.client.get_open_positions()
        still_open = any(p.get("symbol") == symbol
                         and float(p.get("positionAmt",0)) != 0
                         for p in positions)

        if not still_open:
            self._close_trade(symbol, trade, price, "TP/SL")
            return

        # ── Trailing stop ──────────────────────────────────
        ts = self.strategy.check_trailing_stop(signal, price)
        if ts["action"] == "move_sl":
            new_sl = ts["new_sl"]
            if new_sl != trade.get("sl_current"):
                trade["sl_current"] = new_sl
                # Cancelar SL anterior y colocar uno nuevo
                self.client.cancel_all_orders(symbol)
                cs = "SELL" if signal["signal"] == "LONG" else "BUY"
                ps = trade["position_side"]
                self.client.place_stop_order(symbol, cs, ps,
                    stop_price=new_sl, quantity=trade["qty"],
                    order_type="STOP_MARKET")
                self.client.place_stop_order(symbol, cs, ps,
                    stop_price=signal["tp"], quantity=trade["qty"],
                    order_type="TAKE_PROFIT_MARKET")
                logger.info(f"[{symbol}] 🔄 Trailing SL → {new_sl:.6f}")

        # ── Time-Stop ──────────────────────────────────────
        if trade["candle_count"] >= TIME_STOP_CANDLES:
            logger.info(f"[{symbol}] ⏱️ TIME-STOP c={trade['candle_count']}")
            self.client.cancel_all_orders(symbol)
            self.client.close_position(symbol, trade["position_side"], trade["qty"])
            self._close_trade(symbol, trade, price, "TIME_STOP")

    def _close_trade(self, symbol: str, trade: dict, price: float, reason: str):
        sig = trade["signal"]
        pct = (price - sig["entry"]) / sig["entry"]
        if sig["signal"] == "SHORT":
            pct = -pct
        pnl  = round(pct * trade["position_usdt"] * trade["leverage"], 4)
        dur  = (datetime.now(timezone.utc) - trade["open_time"]).total_seconds() / 60
        outcome = {"pnl": pnl, "reason": reason, "duration_min": dur}
        self.learning.record(symbol, sig, outcome)
        self.telegram.notify_trade_close(symbol, outcome)
        del self._active[symbol]
        self.risk.close(symbol)
        icon = "✅" if pnl > 0 else "❌"
        logger.info(f"[{symbol}] {icon} {reason} pnl={pnl:+.4f} dur={dur:.0f}min")

    # ── Run ───────────────────────────────────────────────
    def run(self):
        self.startup()
        schedule.every(3).minutes.do(self.tick)
        schedule.every(1).hour.do(self.hourly_task)
        schedule.every().day.at("00:01").do(self.daily_report)
        logger.info("Scheduler: 3min | hourly | 00:01UTC daily")
        self.tick()
        while True:
            schedule.run_pending()
            time.sleep(10)


if __name__ == "__main__":
    SniperBotV35().run()
