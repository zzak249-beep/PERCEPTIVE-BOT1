"""
strategy.py — V35 FINAL CORREGIDO
BUGS ELIMINADOS:
  1. RSI NaN cuando loss=0 (tendencia pura) — bloqueaba todas las señales
  2. RSI_OB=78 bloqueaba tendencias fuertes legítimas
  3. Lógica RSI invertida — ahora es confirmación de momentum no filtro de extremos

LÓGICA FINAL (limpia, probada, sin bugs):
  LONG:  EMA7 > EMA17 > EMA21  (alineación alcista)
       + EMA7 pendiente > 0     (momentum)
       + ADX >= 15              (hay tendencia)
       + Vol >= 0.9x media      (actividad real)
       + RSI > 45               (momentum positivo confirmado)

  SHORT: EMA7 < EMA17 < EMA21  (alineación bajista)
       + EMA7 pendiente < 0
       + ADX >= 15
       + Vol >= 0.9x media
       + RSI < 55               (momentum negativo confirmado)

  SL = ATR × 1.5  |  TP = ATR × 3.0  |  R:R = 2.0
  Sesión: 06-22 UTC
"""
import logging
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from config import EMA_FAST, EMA_MID, EMA_SLOW, VOL_MULT, ADX_MIN

logger = logging.getLogger(__name__)

TP_ATR_MULT   = 3.0
SL_ATR_MULT   = 1.5
SESSION_START = 6
SESSION_END   = 22


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def _sma(s, n):
    return s.rolling(n).mean()

def _atr(h, l, c, n=14):
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def _adx(h, l, c, n=14):
    pc  = c.shift(1)
    tr  = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    up  = h - h.shift(1)
    dn  = l.shift(1) - l
    pdm = pd.Series(np.where((up > dn) & (up > 0),   up, 0.), index=h.index, dtype=float)
    mdm = pd.Series(np.where((dn > up) & (dn > 0),   dn, 0.), index=h.index, dtype=float)
    a   = tr.ewm(span=n, adjust=False).mean()
    pdi = 100 * pdm.ewm(span=n, adjust=False).mean() / a.replace(0, np.nan)
    mdi = 100 * mdm.ewm(span=n, adjust=False).mean() / a.replace(0, np.nan)
    dx  = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(span=n, adjust=False).mean()

def _rsi(c, n=14):
    """RSI sin bug NaN — cuando loss=0 devuelve 100, cuando gain=0 devuelve 0."""
    delta = c.diff()
    gain  = delta.clip(lower=0).ewm(span=n, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=n, adjust=False).mean()
    # FIX: fillna(0) en loss antes de dividir, luego manejar el caso
    rsi   = pd.Series(index=c.index, dtype=float)
    for i in range(len(c)):
        g = gain.iloc[i]
        lo = loss.iloc[i]
        if pd.isna(g) or pd.isna(lo):
            rsi.iloc[i] = np.nan
        elif lo == 0:
            rsi.iloc[i] = 100.0 if g > 0 else 50.0
        else:
            rs = g / lo
            rsi.iloc[i] = 100 - (100 / (1 + rs))
    return rsi


class StrategyV35:

    def _indicators(self, df):
        df = df.copy()
        df["ema7"]   = _ema(df["close"], EMA_FAST)
        df["ema17"]  = _ema(df["close"], EMA_MID)
        df["ema21"]  = _ema(df["close"], EMA_SLOW)
        df["vol_ma"] = _sma(df["volume"], 20)
        df["adx"]    = _adx(df["high"], df["low"], df["close"], 14)
        df["atr"]    = _atr(df["high"], df["low"], df["close"], 14)
        df["rsi"]    = _rsi(df["close"], 14)
        return df

    def _in_session(self):
        h = datetime.now(timezone.utc).hour
        return SESSION_START <= h < SESSION_END

    def get_signal(self, df: pd.DataFrame, adx_override=None) -> dict:
        NONE = {"signal": "NONE", "reason": ""}

        if len(df) < 25:
            return {**NONE, "reason": "pocas_velas"}

        if not self._in_session():
            return {**NONE, "reason": f"fuera_sesion_{datetime.now(timezone.utc).hour}h"}

        df    = self._indicators(df)
        last  = df.iloc[-1]
        prev3 = df.iloc[-4]   # pendiente de 4 velas (12 min)

        # NaN guard
        for col in ["ema7", "ema17", "ema21", "adx", "atr", "vol_ma", "rsi"]:
            if pd.isna(last[col]):
                return {**NONE, "reason": f"nan_{col}"}

        adx_min   = float(adx_override) if adx_override else float(ADX_MIN)
        vol_ratio = float(last["volume"]) / float(last["vol_ma"]) if float(last["vol_ma"]) > 0 else 0.0
        e7    = float(last["ema7"])
        e17   = float(last["ema17"])
        e21   = float(last["ema21"])
        adx   = float(last["adx"])
        atr   = float(last["atr"])
        rsi   = float(last["rsi"])
        close = float(last["close"])
        slope = e7 - float(prev3["ema7"])  # pendiente 12 min

        # ── Filtros base ──────────────────────────────────
        if vol_ratio < float(VOL_MULT):
            return {**NONE, "reason": f"vol_{vol_ratio:.2f}x<{VOL_MULT}x"}
        if adx < adx_min:
            return {**NONE, "reason": f"adx_{adx:.1f}<{adx_min}"}

        # ── Condición de entrada ──────────────────────────
        bull = e7 > e17 > e21 and slope > 0 and rsi > 45
        bear = e7 < e17 < e21 and slope < 0 and rsi < 55

        if bull:
            signal = "LONG"
        elif bear:
            signal = "SHORT"
        else:
            gap = (e7 - e17) / e17 * 100
            align = "bull" if e7 > e17 > e21 else ("bear" if e7 < e17 < e21 else "no_align")
            return {**NONE, "reason": f"{align} rsi={rsi:.0f} slope={'↑' if slope > 0 else '↓'} gap={gap:.3f}%"}

        # ── SL / TP ───────────────────────────────────────
        sl_d = atr * SL_ATR_MULT
        tp_d = atr * TP_ATR_MULT
        sl   = close - sl_d if signal == "LONG" else close + sl_d
        tp   = close + tp_d if signal == "LONG" else close - tp_d
        rr   = round(tp_d / sl_d, 2)

        logger.debug(f"Señal {signal}: close={close:.6f} sl={sl:.6f} tp={tp:.6f} R:R={rr}")

        return {
            "signal":    signal,
            "reason":    "OK",
            "entry":     round(close, 8),
            "sl":        round(sl,    8),
            "tp":        round(tp,    8),
            "rr":        rr,
            "atr":       round(atr,   8),
            "adx":       round(adx,   2),
            "rsi":       round(rsi,   1),
            "strength":  self._strength(e7, e17, e21, adx, vol_ratio),
            "vol_ratio": round(vol_ratio, 2),
            "peak":      round(close + atr * 3, 8),
            "valley":    round(close - atr * 3, 8),
        }

    def get_diagnostics(self, df: pd.DataFrame) -> dict:
        if len(df) < 25:
            return {"error": "pocas_velas"}
        try:
            df    = self._indicators(df)
            last  = df.iloc[-1]
            prev3 = df.iloc[-4]
            e7    = float(last["ema7"])
            e17   = float(last["ema17"])
            e21   = float(last["ema21"])
            vol_r = float(last["volume"]) / float(last["vol_ma"]) if float(last["vol_ma"]) > 0 else 0
            slope = e7 - float(prev3["ema7"])
            return {
                "adx":        round(float(last["adx"]), 1),
                "rsi":        round(float(last["rsi"]), 1),
                "vol_ratio":  round(vol_r, 2),
                "gap_pct":    round((e7 - e17) / e17 * 100, 4),
                "bull_align": e7 > e17 > e21,
                "bear_align": e7 < e17 < e21,
                "slope_up":   slope > 0,
                "in_session": self._in_session(),
                "vol_ok":     vol_r >= float(VOL_MULT),
                "adx_ok":     float(last["adx"]) >= float(ADX_MIN),
                "close":      round(float(last["close"]), 8),
            }
        except Exception as ex:
            return {"error": str(ex)}

    def check_trailing_stop(self, signal: dict, current_price: float) -> dict:
        entry = signal["entry"]; sl = signal["sl"]; tp = signal["tp"]
        d = signal["signal"]
        if d == "LONG":
            progress = (current_price - entry) / (tp - entry) if tp != entry else 0
            if progress >= 0.5:
                new_sl = round(entry + (tp - entry) * 0.1, 8)
                if new_sl > sl:
                    return {"action": "move_sl", "new_sl": new_sl}
        elif d == "SHORT":
            progress = (entry - current_price) / (entry - tp) if entry != tp else 0
            if progress >= 0.5:
                new_sl = round(entry - (entry - tp) * 0.1, 8)
                if new_sl < sl:
                    return {"action": "move_sl", "new_sl": new_sl}
        return {"action": "hold"}

    @staticmethod
    def _strength(e7, e17, e21, adx, vol_ratio) -> float:
        s  = min(40.0, adx / 50 * 40)
        s += min(30.0, vol_ratio / 3 * 30)
        s += 30.0 if (e7 > e17 > e21 or e7 < e17 < e21) else 0.0
        return round(s, 1)
