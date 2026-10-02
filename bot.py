"""
Bot Wyckoff para BingX perpetuos.
- Escanea el top-N de pares por volumen, vela cerrada a vela cerrada, con el motor wyckoff.py
- Envía a Telegram: señales de ENTRADA (con SL/TP1/TP2/RR) y eventos Wyckoff (Spring, UTAD, SOS, SOW...)
- Opcional: ejecución automática en BingX (AUTO_TRADE=1). Por defecto SOLO señales.
Todas las opciones se configuran con variables de entorno (ver config.py).
"""
import logging
import math
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import notifier
import wyckoff as W
from bingx import BingX, BingXError, floor_to
from config import cfg
from notifier import esc

log = logging.getLogger("bot")
STOP = threading.Event()

TF_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
         "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
         "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000}

EVENTS = {  # clave -> (bit, texto)
    "ps": (W.BIT_PS, "⚪ Parada preliminar (PS)"),
    "sc": (W.BIT_SC, "🔻 Clímax vendedor (SC)"),
    "bc": (W.BIT_BC, "🔺 Clímax comprador (BC)"),
    "ar": (W.BIT_AR, "↔️ Reacción automática (AR)"),
    "st": (W.BIT_ST, "🔁 Test secundario (ST)"),
    "spring": (W.BIT_SPRING, "🟢 SPRING"),
    "utad": (W.BIT_UTAD, "🔴 UTAD"),
    "test": (W.BIT_TEST, "🧪 Test de Fase C"),
    "ctest": (W.BIT_CTEST, "🧪 Test continuación"),
    "sos": (W.BIT_SOS, "🟢 SOS (señal de fuerza)"),
    "sow": (W.BIT_SOW, "🔴 SOW (señal de debilidad)"),
    "lps": (W.BIT_LPS, "🟢 LPS"),
    "lpsy": (W.BIT_LPSY, "🔴 LPSY"),
    "e": (W.BIT_E, "🚀 Fase E (tendencia en marcha)"),
}
TYPE_NAMES = {1: "Acumulación", 2: "Reacumulación", -1: "Distribución", -2: "Redistribución"}


def active_events():
    ev = cfg.ALERT_EVENTS
    if not ev or "none" in ev:
        return {}
    if "all" in ev:
        return dict(EVENTS)
    return {k: EVENTS[k] for k in ev if k in EVENTS}


# ───────────────────────── estado por símbolo ─────────────────────────
class Sym:
    def __init__(self, name, info, strictness, tf_ms):
        self.name, self.info, self.tf_ms = name, info, tf_ms
        self.tick = 10 ** -info["px_prec"]
        self.eng = W.Engine(self.tick, tf_ms, strictness)
        self.fails = 0
        self.last_entry_t = 0

    def feed(self, candles):
        """Procesa velas cerradas nuevas (ordenadas). Devuelve lista de resultados del motor."""
        out = []
        for c in candles:
            if c["t"] <= self.eng.last_t:
                continue
            out.append(self.eng.add_bar(c))
        return out


def closed_only(kl, tf_ms):
    now = int(time.time() * 1000)
    return [k for k in kl if k["t"] + tf_ms <= now]


# ───────────────────────── universo ─────────────────────────
def build_universe(bx):
    contracts = bx.contracts()
    if cfg.SYMBOLS:
        names = [s for s in cfg.SYMBOLS if s in contracts]
    else:
        ranked = []
        for t in bx.tickers():
            sym = t.get("symbol", "")
            if sym not in contracts or sym in cfg.EXCLUDE:
                continue
            try:
                qv = float(t.get("quoteVolume") or 0) or float(t.get("volume") or 0) * float(t.get("lastPrice") or 0)
            except (TypeError, ValueError):
                continue
            if qv >= cfg.MIN_QUOTE_VOL:
                ranked.append((qv, sym))
        ranked.sort(reverse=True)
        names = [s for _, s in (ranked[:cfg.TOP_N] if cfg.TOP_N > 0 else ranked)]  # TOP_N=0 -> TODAS
    return {n: contracts[n] for n in names}


def warm(bx, name, info, tf_ms):
    s = Sym(name, info, cfg.STRICTNESS, tf_ms)
    kl = closed_only(bx.klines(name, cfg.TIMEFRAME, cfg.WARMUP_BARS), tf_ms)
    s.feed(kl)                      # calentamiento: se ignoran señales históricas
    return s


def sync_universe(bx, syms, tf_ms, pool):
    uni = build_universe(bx)
    for n in [n for n in syms if n not in uni]:
        syms.pop(n)
    new = [n for n in uni if n not in syms]

    def _w(n):
        try:
            return n, warm(bx, n, uni[n], tf_ms)
        except Exception as e:
            log.warning("warmup %s: %s", n, e)
            return n, None
    for n, s in pool.map(_w, new):
        if s:
            syms[n] = s
    log.info("Universo: %d símbolos (%d nuevos)", len(syms), len(new))
    return len(new)


# ───────────────────────── mensajes ─────────────────────────
def _p(x, prec):
    return f"{x:.{prec}f}"


def _pct(a, b):
    return (a - b) / b * 100.0


def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%H:%M UTC")


def entry_msg(s, r, plan):
    is_long, sl, tp1, tp2, rr2 = plan
    pr = s.info["px_prec"]
    e = r["entryPrice"]
    head = "🟢 <b>LONG" if is_long else "🔴 <b>SHORT"
    return (
        f"{head} · {esc(s.name)}</b> · {cfg.TIMEFRAME}\n"
        f"Wyckoff {TYPE_NAMES.get(r['type'], '-')} · Entrada: {esc(W.ENTRY_KIND_NAMES.get(r['entryKind'], '-'))}\n"
        f"Fase {W.PHASE_NAMES.get(r['phase'], '-')} · Confianza {r['conf']} · Validación {r['val']}\n"
        f"━━━━━━━━━━━━\n"
        f"Entrada  <code>{_p(e, pr)}</code>\n"
        f"SL       <code>{_p(sl, pr)}</code> ({_pct(sl, e):+.2f}%)\n"
        f"TP1      <code>{_p(tp1, pr)}</code> ({_pct(tp1, e):+.2f}%)\n"
        f"TP2      <code>{_p(tp2, pr)}</code> ({_pct(tp2, e):+.2f}%) · RR {rr2:.1f}\n"
        f"Rango    <code>{_p(r['rangeLow'], pr)}</code> – <code>{_p(r['rangeHigh'], pr)}</code>\n"
        f"🕐 vela {utc(r['t'])}"
    )


def event_msg(s, r, label):
    pr = s.info["px_prec"]
    return (
        f"{label} · <b>{esc(s.name)}</b> · {cfg.TIMEFRAME}\n"
        f"{TYPE_NAMES.get(r['type'], 'Estructura')} · Fase {W.PHASE_NAMES.get(r['phase'], '-')} · "
        f"Conf {r['conf']}\n"
        f"Precio <code>{_p(r['close'], pr)}</code> · {esc(s.eng.next_step())}\n"
        f"🕐 vela {utc(r['t'])}"
    )


# ───────────────────────── ejecución (opcional) ─────────────────────────
class Trader:
    def __init__(self, bx):
        self.bx = bx
        self.prepared = set()

    def execute(self, s, is_long, entry, sl, tp1, tp2):
        bx, name, info = self.bx, s.name, s.info
        opened = bx.open_symbols()
        if name in opened:
            return "ya hay posición abierta"
        if len(opened) >= cfg.MAX_POSITIONS:
            return f"máximo de posiciones ({cfg.MAX_POSITIONS})"
        px = bx.price(name)
        risk = abs(entry - sl)
        if (is_long and (px <= sl or px >= tp1)) or ((not is_long) and (px >= sl or px <= tp1)):
            return "precio ya fuera del plan"
        if abs(px - entry) > 0.5 * risk:
            return "precio se alejó >0.5R de la entrada"
        eq = bx.equity()
        if eq <= 0:
            return "equity 0"
        qty = eq * cfg.RISK_PCT / 100.0 / abs(px - sl)
        qty = min(qty, eq * cfg.LEVERAGE * 0.95 / px)
        qty = floor_to(qty, info["qty_prec"])
        if qty <= 0 or qty < info["min_qty"]:
            return f"qty {qty} < mínimo {info['min_qty']}"
        if name not in self.prepared:
            bx.set_margin(name, cfg.MARGIN_TYPE)
            bx.set_leverage(name, cfg.LEVERAGE)
            self.prepared.add(name)
        side, close, d = ("BUY", "SELL", "long") if is_long else ("SELL", "BUY", "short")
        pr = info["px_prec"]
        bx.order(name, side, d, "MARKET", qty)
        try:
            bx.order(name, close, d, "STOP_MARKET", qty, stop=round(sl, pr), reduce=True)
        except BingXError as e:
            log.error("SL falló %s: %s -> cierro posición", name, e)
            try:
                bx.order(name, close, d, "MARKET", qty, reduce=True)
            except BingXError as e2:
                notifier.send(f"🚨 <b>{esc(name)}</b>: SL falló y NO pude cerrar. REVISA A MANO.\n{esc(e2)}")
            raise
        q1 = floor_to(qty * cfg.TP1_FRAC, info["qty_prec"])
        q2 = floor_to(qty - q1, info["qty_prec"])
        try:
            if q1 >= info["min_qty"] and q2 >= info["min_qty"]:
                bx.order(name, close, d, "TAKE_PROFIT_MARKET", q1, stop=round(tp1, pr), reduce=True)
                bx.order(name, close, d, "TAKE_PROFIT_MARKET", q2, stop=round(tp2, pr), reduce=True)
            else:
                bx.order(name, close, d, "TAKE_PROFIT_MARKET", qty, stop=round(tp1, pr), reduce=True)
        except BingXError as e:
            notifier.send(f"⚠️ <b>{esc(name)}</b>: posición abierta con SL pero falló el TP: {esc(e)}")
        return f"ejecutada qty {qty} (riesgo {cfg.RISK_PCT}%)"


# ───────────────────────── ciclo ─────────────────────────
def process_symbol(bx, s, tf_ms):
    """Hilo de trabajo: trae velas nuevas y corre el motor. Devuelve (sym, resultados)."""
    last = s.eng.last_t
    now = int(time.time() * 1000)
    missed = int((now - last) // tf_ms) if last else cfg.WARMUP_BARS
    kl = bx.klines(s.name, cfg.TIMEFRAME, min(1000, max(3, missed + 2)))
    return s, s.feed(closed_only(kl, tf_ms))


def run_cycle(bx, syms, tf_ms, pool, trader, stats, ev_map):
    msgs = []
    futs = [pool.submit(process_symbol, bx, s, tf_ms) for s in list(syms.values())]
    for f, s in zip(futs, list(syms.values())):
        try:
            _, results = f.result()
            s.fails = 0
        except Exception as e:
            s.fails += 1
            stats["errors"] += 1
            log.warning("%s: %s", s.name, e)
            if s.fails >= 5:
                syms.pop(s.name, None)      # se recalienta en el próximo refresco de universo
            continue
        for r in results:
            stats["bars"] += 1
            for key, (bit, label) in ev_map.items():
                if r["sig"] & bit:
                    msgs.append(event_msg(s, r, label))
                    stats["events"] += 1
            if r["entry_now"] and r["outcome"] != W.DIR_NONE:
                m = handle_entry(s, r, trader, stats, tf_ms)
                if m:
                    msgs.append(m)
    for m in msgs:
        notifier.send(m)


def handle_entry(s, r, trader, stats, tf_ms):
    is_long = r["outcome"] == W.DIR_ACCUM
    if s.last_entry_t and r["t"] - s.last_entry_t < cfg.COOLDOWN_BARS * tf_ms:
        log.info("%s: entrada en cooldown", s.name)
        return None
    sl, tp1, tp2, rr2 = W.risk_plan(is_long, r["entryPrice"], r["rangeHigh"], r["rangeLow"], r["exc"],
                                    r["excPrice"], r["testPrice"], r["atr"], cfg.SL_BUFFER_ATR, s.tick)
    if any(map(lambda x: x != x or math.isinf(x), (sl, tp1, tp2, rr2))):
        log.warning("%s: plan inválido", s.name)
        return None
    sl_pct = abs(sl - r["entryPrice"]) / r["entryPrice"] * 100
    if rr2 < cfg.MIN_RR or sl_pct > cfg.MAX_SL_PCT:
        log.info("%s: señal filtrada (RR %.2f, SL %.2f%%)", s.name, rr2, sl_pct)
        stats["filtered"] += 1
        return None
    s.last_entry_t = r["t"]
    stats["signals"] += 1
    msg = entry_msg(s, r, (is_long, sl, tp1, tp2, rr2))
    if trader:
        try:
            msg += "\n⚙️ " + esc(trader.execute(s, is_long, r["entryPrice"], sl, tp1, tp2))
        except Exception as e:
            log.exception("ejecución %s", s.name)
            msg += f"\n❌ Ejecución falló: {esc(e)}"
    return msg


def sleep_until_next_close(tf_ms):
    nxt = (int(time.time() * 1000) // tf_ms + 1) * tf_ms + int(cfg.CLOSE_DELAY_S * 1000)
    while not STOP.is_set():
        left = nxt / 1000 - time.time()
        if left <= 0:
            return
        STOP.wait(min(left, 5))


def validate():
    errs = []
    if cfg.TIMEFRAME not in TF_MS:
        errs.append(f"TIMEFRAME inválido: {cfg.TIMEFRAME} (usa {', '.join(TF_MS)})")
    if cfg.STRICTNESS not in W.ENTRY_CONF:
        errs.append("STRICTNESS debe ser conservative | standard | aggressive")
    if cfg.AUTO_TRADE and not (cfg.BINGX_API_KEY and cfg.BINGX_API_SECRET):
        errs.append("AUTO_TRADE=1 requiere BINGX_API_KEY y BINGX_API_SECRET")
    if cfg.POSITION_MODE not in ("hedge", "oneway"):
        errs.append("POSITION_MODE debe ser hedge | oneway")
    return errs


def main():
    logging.basicConfig(level=getattr(logging, cfg.LOG_LEVEL, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    for sg in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sg, lambda *_: STOP.set())

    errs = validate()
    if errs:
        for e in errs:
            log.error(e)
        notifier.send("🛑 <b>Config inválida</b>\n" + "\n".join(esc(e) for e in errs))
        time.sleep(30)          # evita bucle de reinicios rápidos en Railway
        sys.exit(1)

    tf_ms = TF_MS[cfg.TIMEFRAME]
    bx = BingX(cfg.BINGX_API_KEY, cfg.BINGX_API_SECRET, cfg.POSITION_MODE)
    trader = Trader(bx) if cfg.AUTO_TRADE else None
    ev_map = active_events()
    stats = dict(bars=0, events=0, signals=0, filtered=0, errors=0)
    syms = {}
    pool = ThreadPoolExecutor(max_workers=max(1, cfg.WORKERS))

    # primer arranque con reintentos
    while not STOP.is_set():
        try:
            sync_universe(bx, syms, tf_ms, pool)
            if syms:
                break
            log.error("Universo vacío, reintento en 30s")
        except Exception as e:
            log.error("Arranque falló: %s", e)
        STOP.wait(30)
    if STOP.is_set():
        return

    notifier.send(
        f"🤖 <b>Bot Wyckoff activo</b>\n"
        f"{len(syms)} pares · TF {cfg.TIMEFRAME} · {cfg.STRICTNESS}\n"
        f"Eventos: {esc(', '.join(ev_map) or 'solo entradas')} · MIN_RR {cfg.MIN_RR}\n"
        f"Ejecución: {'AUTO (riesgo ' + str(cfg.RISK_PCT) + '%, x' + str(cfg.LEVERAGE) + ')' if trader else 'solo señales'}")

    next_refresh = time.time() + cfg.UNIVERSE_REFRESH_H * 3600
    next_beat = time.time() + cfg.HEARTBEAT_H * 3600 if cfg.HEARTBEAT_H > 0 else None
    last_err_alert = 0

    while not STOP.is_set():
        sleep_until_next_close(tf_ms)
        if STOP.is_set():
            break
        t0 = time.time()
        try:
            run_cycle(bx, syms, tf_ms, pool, trader, stats, ev_map)
            if time.time() >= next_refresh:
                sync_universe(bx, syms, tf_ms, pool)
                next_refresh = time.time() + cfg.UNIVERSE_REFRESH_H * 3600
            if next_beat and time.time() >= next_beat:
                notifier.send(f"💓 Bot vivo · {len(syms)} pares · señales {stats['signals']} · "
                              f"filtradas {stats['filtered']} · errores {stats['errors']}")
                next_beat = time.time() + cfg.HEARTBEAT_H * 3600
        except Exception as e:
            log.exception("ciclo falló")
            if time.time() - last_err_alert > 600:
                notifier.send(f"⚠️ Error en ciclo: {esc(e)}")
                last_err_alert = time.time()
        log.info("ciclo %.1fs · %d pares", time.time() - t0, len(syms))
    log.info("Detenido")


if __name__ == "__main__":
    main()
