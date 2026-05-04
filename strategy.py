"""
ZigZag Institutional Elite V6 — Strategy engine
Bugs corregidos:
  1. closes[-1] era vela incompleta → usar closes[-2] (última cerrada)
  2. find_pivots usaba == (float) → usar >= / <=
  3. peak/valley podían estar 50+ velas atrás → filtro proximidad ATR
  4. parse_klines no manejaba formato lista de BingX
  5. Volumen de vela incompleta → usar vol[-2]
  6. Solo 1 pivot nivel chequeado → todos los pivots recientes
"""
import logging
import numpy as np
from typing import Optional, Tuple, List
import config

log = logging.getLogger("strategy")


# ─────────────────────────────────────────────────────────────────────
# 1. KLINE PARSER — robusto para dict Y lista
# ─────────────────────────────────────────────────────────────────────
def parse_klines(raw: list) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    BingX puede devolver:
      - list of dicts: {"open":..., "high":..., "low":..., "close":..., "volume":...}
      - list of lists: [ts, open, high, low, close, volume, ...]
    """
    if not raw:
        return (np.array([]),) * 5

    opens, highs, lows, closes, volumes = [], [], [], [], []

    for k in raw:
        try:
            if isinstance(k, dict):
                o = float(k.get("open",   k.get("o", 0)))
                h = float(k.get("high",   k.get("h", 0)))
                l = float(k.get("low",    k.get("l", 0)))
                c = float(k.get("close",  k.get("c", 0)))
                v = float(k.get("volume", k.get("v", 0)))
            elif isinstance(k, (list, tuple)) and len(k) >= 6:
                o, h, l, c, v = float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])
            else:
                continue

            if h < l or c <= 0 or h <= 0:
                continue

            opens.append(o); highs.append(h); lows.append(l)
            closes.append(c); volumes.append(v)
        except (TypeError, ValueError):
            continue

    return (
        np.array(opens,   dtype=float),
        np.array(highs,   dtype=float),
        np.array(lows,    dtype=float),
        np.array(closes,  dtype=float),
        np.array(volumes, dtype=float),
    )


# ─────────────────────────────────────────────────────────────────────
# 2. ATR (Wilder)
# ─────────────────────────────────────────────────────────────────────
def calc_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:]  - closes[:-1])
        )
    )
    atr_val = np.mean(tr[:period])
    for i in range(period, len(tr)):
        atr_val = (atr_val * (period - 1) + tr[i]) / period
    return float(atr_val)


# ─────────────────────────────────────────────────────────────────────
# 3. PIVOT DETECTION — usa >= y <= (no ==)
# ─────────────────────────────────────────────────────────────────────
def find_pivots(highs: np.ndarray, lows: np.ndarray, pivot_len: int):
    """
    Devuelve listas de (valor, índice) de pivots confirmados.
    Usa >= y <= para evitar fallos con floats.
    """
    n = len(highs)
    ph_list: List[Tuple[float, int]] = []
    pl_list: List[Tuple[float, int]] = []

    for i in range(pivot_len, n - pivot_len):
        window_h = highs[i - pivot_len: i + pivot_len + 1]
        window_l = lows[i  - pivot_len: i + pivot_len + 1]

        if highs[i] >= np.max(window_h):   # FIX: >= no ==
            ph_list.append((float(highs[i]), i))
        if lows[i] <= np.min(window_l):     # FIX: <= no ==
            pl_list.append((float(lows[i]), i))

    return ph_list, pl_list


# ─────────────────────────────────────────────────────────────────────
# 4. SIGNAL ENGINE
# ─────────────────────────────────────────────────────────────────────
class ZigZagSignal:

    def compute(
        self,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray,
    ) -> Optional[dict]:

        n = len(closes)
        min_bars = config.PIVOT_LEN * 2 + config.ATR_LEN + 2
        if n < min_bars:
            log.debug(f"  ✗ Pocas velas: {n} < {min_bars}")
            return None

        # ── CRÍTICO: ignorar la última vela (abierta en BingX) ───────
        # closes[-2] = última vela CERRADA
        # closes[-3] = penúltima vela cerrada
        H = highs[:-1]
        L = lows[:-1]
        C = closes[:-1]
        O = opens[:-1]
        V = volumes[:-1]

        if len(C) < 3:
            return None

        # ── ATR ──────────────────────────────────────────────────────
        atr = calc_atr(H, L, C, config.ATR_LEN)
        if atr == 0:
            log.debug("  ✗ ATR = 0")
            return None

        # ── Volumen institucional (última vela CERRADA) ───────────────
        vol_ma    = np.mean(V[-20:]) if len(V) >= 20 else np.mean(V)
        vol_ratio = V[-1] / vol_ma if vol_ma > 0 else 0.0
        institucional = V[-1] > (vol_ma * config.VOL_MULT)

        # ── Pivots sobre todas las velas cerradas ─────────────────────
        ph_list, pl_list = find_pivots(H, L, config.PIVOT_LEN)

        if not ph_list or not pl_list:
            log.debug("  ✗ Sin pivots encontrados")
            return None

        # ── Última vela cerrada ───────────────────────────────────────
        close      = C[-1]
        prev_close = C[-2]
        is_bull    = close > O[-1]
        is_bear    = close < O[-1]

        # Proximidad: el pivot debe estar dentro de 4×ATR del precio actual
        proximity = atr * 4.0

        # ─── LONG: busca pivot high cruzado por la última vela ────────
        for peak_val, _ in reversed(ph_list):
            if abs(peak_val - close) > proximity:
                continue
            if prev_close <= peak_val < close:
                if institucional and is_bull:
                    valleys_below = [v for v, _ in pl_list if v < close]
                    sl = valleys_below[-1] if valleys_below else close - atr * 2
                    tp = close + (close - sl) * config.TP_MULT
                    if tp > close > sl > 0:
                        log.info(f"  ✅ LONG: close={close:.6g} cruzó peak={peak_val:.6g} vol={vol_ratio:.2f}x")
                        return {"side": "BUY", "entry": close, "sl": sl, "tp": tp,
                                "atr": atr, "peak": peak_val, "valley": sl, "vol_ratio": vol_ratio}
                else:
                    log.debug(f"  ✗ LONG cruce peak={peak_val:.6g} | vol_ok={institucional} bull={is_bull}")

        # ─── SHORT: busca pivot low cruzado por la última vela ────────
        for valley_val, _ in reversed(pl_list):
            if abs(valley_val - close) > proximity:
                continue
            if prev_close >= valley_val > close:
                if institucional and is_bear:
                    peaks_above = [v for v, _ in ph_list if v > close]
                    sl = peaks_above[-1] if peaks_above else close + atr * 2
                    tp = close - (sl - close) * config.TP_MULT
                    if tp < close < sl:
                        log.info(f"  ✅ SHORT: close={close:.6g} cruzó valley={valley_val:.6g} vol={vol_ratio:.2f}x")
                        return {"side": "SELL", "entry": close, "sl": sl, "tp": tp,
                                "atr": atr, "peak": sl, "valley": valley_val, "vol_ratio": vol_ratio}
                else:
                    log.debug(f"  ✗ SHORT cruce valley={valley_val:.6g} | vol_ok={institucional} bear={is_bear}")

        return None


# ─────────────────────────────────────────────────────────────────────
# 5. EXPLOSION SCORER
# ─────────────────────────────────────────────────────────────────────
class ExplosionScorer:

    def score(self, ticker: dict, daily_klines: list) -> float:
        try:
            price_change = abs(float(ticker.get("priceChangePercent", 0)))
            quote_vol    = float(ticker.get("quoteVolume", 0))

            vol_score = 1.0
            if len(daily_klines) >= 2:
                def _vol(k):
                    if isinstance(k, dict):
                        return float(k.get("volume", 0))
                    return float(k[5]) if isinstance(k, (list, tuple)) and len(k) > 5 else 0.0

                recent_vol = _vol(daily_klines[-1])
                avg_vol    = np.mean([_vol(k) for k in daily_klines[:-1]])
                vol_score  = (recent_vol / avg_vol) if avg_vol > 0 else 1.0

            return (
                price_change * 2.0 +
                vol_score    * 3.0 +
                min(quote_vol / 1e7, 5.0)
            )
        except Exception:
            return 0.0
