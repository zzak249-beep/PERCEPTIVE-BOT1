"""
telegram_notifier.py — Notificaciones Telegram
FIX: notify_tick_status reemplaza "sin señales activas" con diagnóstico real
"""
import logging
import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, VOL_MULT, ADX_MIN

logger = logging.getLogger(__name__)
BAR = "━━━━━━━━━━━━━━━━"


class TelegramNotifier:
    def __init__(self):
        self.token   = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self._url    = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.token or not self.chat_id:
            return False
        try:
            resp = requests.post(
                self._url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode},
                timeout=10,
            )
            ok = resp.json().get("ok", False)
            if not ok:
                logger.error(f"Telegram error: {resp.text[:200]}")
            return ok
        except Exception as e:
            logger.error(f"Telegram send: {e}")
            return False

    def notify_startup(self, balance: float, symbol_count: int, dry_run: bool = False):
        mode = "⚠️ <b>DRY RUN</b>" if dry_run else "✅ <b>MODO REAL</b>"
        self.send(
            f"🚀 <b>SNIPER BOT V35 INICIADO</b>\n{BAR}\n"
            f"{mode}\n"
            f"💰 Balance: <b>${balance:,.2f} USDT</b>\n"
            f"🔍 Pares: <b>{symbol_count}</b>\n"
            f"📊 Filtros activos: Vol≥{VOL_MULT}x | ADX≥{ADX_MIN}\n"
            f"⏱️ Ciclo: 3 min | Time-Stop: 45 min\n"
            f"🧠 Aprendizaje: <b>ACTIVO</b>"
        )

    def notify_trade_open(self, symbol: str, signal: dict, trade: dict):
        direction = "🟢 LONG" if signal["signal"] == "LONG" else "🔴 SHORT"
        sl_dist   = abs(signal["entry"] - signal["sl"])
        tp_dist   = abs(signal["tp"]    - signal["entry"])
        rr        = tp_dist / sl_dist if sl_dist > 0 else 0
        self.send(
            f"⚡ <b>TRADE ABIERTO — V35</b>\n{BAR}\n"
            f"📌 <b>{symbol}</b>  {direction}\n"
            f"💰 Entrada: <code>${signal['entry']:.6f}</code>\n"
            f"🛡️ SL:      <code>${signal['sl']:.6f}</code>\n"
            f"🎯 TP:      <code>${signal['tp']:.6f}</code>\n"
            f"📐 R:R ≈ 1:{rr:.1f}\n"
            f"{BAR}\n"
            f"ADX={signal['adx']}  Vol={signal.get('vol_ratio','?')}x  "
            f"Fuerza={signal['strength']}%\n"
            f"Capital: ${trade.get('position_usdt',0):.2f}  Lev: {trade.get('leverage',5)}x"
        )

    def notify_trade_close(self, symbol: str, result: dict):
        pnl   = result.get("pnl", 0)
        emoji = "✅" if pnl > 0 else "❌"
        sign  = "+" if pnl >= 0 else ""
        self.send(
            f"{emoji} <b>TRADE CERRADO</b>\n{BAR}\n"
            f"📌 <b>{symbol}</b>\n"
            f"💸 PnL: <b>{sign}{pnl:.4f} USDT</b>\n"
            f"📋 Razón: {result.get('reason','TP/SL')}\n"
            f"⏱️ Duración: {result.get('duration_min',0):.0f} min"
        )

    def notify_tick_status(self, tick: int, balance: float, open_n: int,
                           reasons: dict, best: dict):
        """
        Reemplaza 'sin señales activas ahora' con diagnóstico real.
        Se envía cada 10 ticks (~30 min) para no saturar.
        """
        top = sorted(reasons.items(), key=lambda x: -x[1])[:4]
        reason_txt = "  " + "\n  ".join(f"{r}: {n}x" for r, n in top) if top else "  (ninguno)"

        best_txt = ""
        if best:
            sym = best.get("_sym", "?")
            best_txt = (
                f"\n🔍 <b>Más cercano:</b> {sym}\n"
                f"  ADX={best.get('adx')}  Vol={best.get('vol_ratio')}x  "
                f"Gap={best.get('gap_pct')}%\n"
                f"  cross_bull={best.get('cross_bull')}  "
                f"cross_bear={best.get('cross_bear')}\n"
                f"  ema21={best.get('close_vs_ema21')}"
            )

        self.send(
            f"📡 <b>ESTADO V35 — Tick #{tick}</b>\n{BAR}\n"
            f"💰 Balance: ${balance:.2f} | Abiertos: {open_n}/3\n"
            f"\n⛔ <b>Razones de rechazo:</b>\n{reason_txt}"
            f"{best_txt}"
        )

    def notify_scan_results(self, top_symbols: list, scanner):
        summary = scanner.summary_text(top_symbols, n=5)
        self.send(
            f"🔍 <b>TOP 20 PARES — V35</b>\n{BAR}\n"
            f"{summary}\n{BAR}\n"
            f"Filtros: Vol≥{VOL_MULT}x | ADX≥{ADX_MIN}"
        )

    def notify_daily_report(self, stats: dict):
        wr    = stats.get("winrate", 0)
        emoji = "🏆" if wr >= 55 else ("⚠️" if wr >= 40 else "🚨")
        sign  = "+" if stats.get("total_pnl", 0) >= 0 else ""
        self.send(
            f"{emoji} <b>REPORTE DIARIO V35</b>\n{BAR}\n"
            f"Trades: {stats.get('total',0)}  ✅{stats.get('wins',0)} ❌{stats.get('losses',0)}\n"
            f"WR: <b>{wr:.1f}%</b>\n"
            f"PnL: <b>{sign}{stats.get('total_pnl',0):.4f} USDT</b>\n"
            f"{BAR}\n"
            f"🧠 {stats.get('learning_notes','...')}"
        )

    def notify_learning_update(self, old: dict, new: dict, reason: str):
        self.send(
            f"🧠 <b>AJUSTE AUTOMÁTICO</b>\n{BAR}\n"
            f"{reason}\n"
            f"ADX: {old.get('adx_min')} → <b>{new.get('adx_min')}</b>\n"
            f"Fuerza: {old.get('min_strength')} → <b>{new.get('min_strength')}</b>"
        )

    def notify_blacklist(self, symbol: str, winrate: float, count: int):
        self.send(
            f"🚫 <b>PAR BLOQUEADO</b>: {symbol}\n"
            f"WR {winrate:.0f}% en {count} trades"
        )

    def notify_error(self, error: str):
        self.send(f"⚠️ <b>ERROR V35</b>\n<code>{error[:400]}</code>")

    def notify_profitability(self, trades: list):
        """Análisis completo de rentabilidad enviado a Telegram."""
        if not trades:
            self.send("📊 <b>Sin trades registrados aún.</b>")
            return

        from collections import defaultdict

        wins   = [t for t in trades if t.get("won")]
        losses = [t for t in trades if not t.get("won")]
        pnls   = [t.get("pnl", 0) for t in trades]
        total  = len(trades)
        wr     = len(wins) / total * 100

        avg_w = sum(t["pnl"] for t in wins)  / len(wins)  if wins   else 0
        avg_l = sum(t["pnl"] for t in losses)/ len(losses) if losses else 0
        rr    = abs(avg_w / avg_l) if avg_l != 0 else 0

        # Por dirección
        longs  = [t for t in trades if t.get("direction") == "LONG"]
        shorts = [t for t in trades if t.get("direction") == "SHORT"]
        lw = sum(1 for t in longs  if t.get("won"))
        sw = sum(1 for t in shorts if t.get("won"))

        # Últimas 10
        recent = trades[-10:]
        recent_wr  = sum(1 for t in recent if t.get("won")) / len(recent) * 100
        recent_pnl = sum(t.get("pnl",0) for t in recent)

        # Top 3 mejores y peores símbolos
        by_sym = defaultdict(list)
        for t in trades:
            by_sym[t.get("symbol","?")].append(t.get("pnl",0))
        sym_pnl = [(s, sum(p), len(p), sum(1 for x in p if x>0)/len(p)*100)
                   for s,p in by_sym.items()]
        sym_pnl.sort(key=lambda x: x[1], reverse=True)
        best3  = sym_pnl[:3]
        worst3 = sym_pnl[-3:]

        verdict = "🏆 RENTABLE" if sum(pnls) > 0 else "🚨 PÉRDIDA NETA"
        be_wr   = 100 / (1 + rr) if rr > 0 else 50

        self.send(
            f"📊 <b>ANÁLISIS DE RENTABILIDAD V35</b>\n{BAR}\n"
            f"{verdict}\n\n"
            f"<b>GLOBAL ({total} trades)</b>\n"
            f"  WR: <b>{wr:.1f}%</b>  (break-even: {be_wr:.0f}%)\n"
            f"  PnL: <b>{sum(pnls):+.4f} USDT</b>\n"
            f"  Avg win: +{avg_w:.4f}  Avg loss: {avg_l:.4f}\n"
            f"  Ratio W/L: {rr:.2f}x\n\n"
            f"<b>DIRECCIÓN</b>\n"
            f"  LONG:  {len(longs)} trades  WR={lw/len(longs)*100:.0f}%  PnL={sum(t['pnl'] for t in longs):+.4f}\n"
            f"  SHORT: {len(shorts)} trades  WR={sw/len(shorts)*100:.0f}%  PnL={sum(t['pnl'] for t in shorts):+.4f}\n\n"
            f"<b>ÚLTIMOS 10 TRADES</b>\n"
            f"  WR: {recent_wr:.0f}%  PnL: {recent_pnl:+.4f}\n\n"
            f"<b>MEJORES PARES</b>\n"
            + "\n".join(f"  ✅ {s}: {p:+.4f} ({c}tr {w:.0f}%WR)" for s,p,c,w in best3) +
            f"\n\n<b>PEORES PARES</b>\n"
            + "\n".join(f"  ❌ {s}: {p:+.4f} ({c}tr {w:.0f}%WR)" for s,p,c,w in worst3)
        )
