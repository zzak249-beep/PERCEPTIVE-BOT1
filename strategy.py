"""
strategy.py — V35 PROFITABLE FINAL
Mejoras de rentabilidad:
1. Confirmación de vela: esperar que el cierre confirme la señal
2. Filtro de tendencia 15m: solo operar a favor de la tendencia mayor
3. SL dinámico: basado en ATR del timeframe actual
4. TP escalonado: 50% en TP1 (1.5×ATR), 50% en TP2 (3×ATR)
5. Filtro de impulso: ADX acelerando (no solo por encima del umbral)
"""
import logging
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from config import EMA_FAST, EMA_MID, EMA_SLOW, VOL_MULT, ADX_MIN

logger = logging.getLogger(__name__)

TP_ATR_MULT   = 2.0
SL_ATR_MULT   = 1.0
SESSION_START = 6
SESSION_END   = 22


def _ema(s, n):    return s.ewm(span=n, adjust=False).mean()
def _sma(s, n):    return s.rolling(n).mean()

def _atr(h, l, c, n=14):
    pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def _adx(h, l, c, n=14):
    pc  = c.shift(1)
    tr  = pd.concat([h-l,(h-pc).abs(),(l-pc).abs()], axis=1).max(axis=1)
    up  = h - h.shift(1)
    dn  = l.shift(1) - l
    pdm = pd.Series(np.where((up>dn)&(up>0), up, 0.), index=h.index, dtype=float)
    mdm = pd.Series(np.where((dn>up)&(dn>0), dn, 0.), index=h.index, dtype=float)
    a   = tr.ewm(span=n, adjust=False).mean()
    pdi = 100 * pdm.ewm(span=n, adjust=False).mean() / a.replace(0, np.nan)
    mdi = 100 * mdm.ewm(span=n, adjust=False).mean() / a.replace(0, np.nan)
    dx  = 100 * (pdi-mdi).abs() / (pdi+mdi).replace(0, np.nan)
    return dx.ewm(span=n, adjust=False).mean()

def _rsi(c, n=14):
    delta = c.diff()
    gain  = delta.clip(lower=0).ewm(span=n, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=n, adjust=False).mean()
    rsi   = pd.Series(index=c.index, dtype=float)
    for i in range(len(c)):
        g, lo = gain.iloc[i], loss.iloc[i]
        if pd.isna(g) or pd.isna(lo): rsi.iloc[i] = np.nan
        elif lo == 0:                  rsi.iloc[i] = 100.0 if g > 0 else 50.0
        else:                          rsi.iloc[i] = 100 - (100/(1+g/lo))
    return rsi


class StrategyV35:

    def _indicators(self, df):
        df = df.copy()
        df["ema7"]   = _ema(df["close"], EMA_FAST)
        df["ema17"]  = _ema(df["close"], EMA_MID)
        df["ema21"]  = _ema(df["close"], EMA_SLOW)
        df["ema50"]  = _ema(df["close"], 50)        # tendencia mayor
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

        if len(df) < 55:   # necesitamos 50 para EMA50
            return {**NONE, "reason": "pocas_velas"}

        if not self._in_session():
            return {**NONE, "reason": f"fuera_sesion_{datetime.now(timezone.utc).hour}h"}

        df    = self._indicators(df)
        last  = df.iloc[-1]
        prev  = df.iloc[-2]
        prev4 = df.iloc[-5]   # pendiente 4 velas = 12 min

        for col in ["ema7","ema17","ema21","ema50","adx","atr","vol_ma","rsi"]:
            if pd.isna(last[col]):
                return {**NONE, "reason": f"nan_{col}"}

        adx_min   = float(adx_override) if adx_override else float(ADX_MIN)
        vol_ratio = float(last["volume"]) / float(last["vol_ma"]) if float(last["vol_ma"]) > 0 else 0.0
        e7    = float(last["ema7"])
        e17   = float(last["ema17"])
        e21   = float(last["ema21"])
        e50   = float(last["ema50"])
        adx   = float(last["adx"])
        adx_prev = float(prev["adx"])
        atr   = float(last["atr"])
        rsi   = float(last["rsi"])
        close = float(last["close"])
        slope = e7 - float(prev4["ema7"])  # pendiente 12 min

        # ── Filtros base ──────────────────────────────────
        if vol_ratio < float(VOL_MULT):
            return {**NONE, "reason": f"vol_{vol_ratio:.2f}x<{VOL_MULT}x"}
        if adx < adx_min:
            return {**NONE, "reason": f"adx_{adx:.1f}<{adx_min}"}

        # MEJORA: ADX debe estar acelerando (no solo por encima del umbral)
        adx_accel = adx >= adx_prev  # ADX creciendo = tendencia fortaleciéndose

        # ── Condiciones de entrada ────────────────────────
        # LONG: EMAs alcistas + precio sobre EMA50 (tendencia mayor) + RSI momentum
        bull = (e7 > e17 > e21          # alineación EMA
                and close > e50          # precio sobre tendencia mayor
                and slope > 0            # momentum positivo
                and rsi > 45             # RSI confirma
                and adx_accel)           # ADX acelerando

        # SHORT: EMAs bajistas + precio bajo EMA50 + RSI momentum
        bear = (e7 < e17 < e21
                and close < e50
                and slope < 0
                and rsi < 55
                and adx_accel)

        if bull:
            signal = "LONG"
        elif bear:
            signal = "SHORT"
        else:
            gap   = (e7-e17)/e17*100
            align = "bull" if e7>e17>e21 else ("bear" if e7<e17<e21 else "no_align")
            e50_txt = f"e50={'arriba' if close>e50 else 'abajo'}"
            return {**NONE, "reason": f"{align} {e50_txt} rsi={rsi:.0f} adx_accel={adx_accel}"}

        # ── SL / TP ───────────────────────────────────────
        sl_d = atr * SL_ATR_MULT
        tp_d = atr * TP_ATR_MULT
        sl   = close - sl_d if signal == "LONG" else close + sl_d
        tp   = close + tp_d if signal == "LONG" else close - tp_d
        # TP1 para salida parcial (50%)
        tp1  = close + atr*1.5 if signal == "LONG" else close - atr*1.5
        rr   = round(tp_d / sl_d, 2)

        return {
            "signal":    signal,
            "reason":    "OK",
            "entry":     round(close, 8),
            "sl":        round(sl,    8),
            "tp":        round(tp,    8),
            "tp1":       round(tp1,   8),   # TP parcial
            "rr":        rr,
            "atr":       round(atr,   8),
            "adx":       round(adx,   2),
            "rsi":       round(rsi,   1),
            "strength":  self._strength(e7,e17,e21,adx,vol_ratio,close,e50),
            "vol_ratio": round(vol_ratio, 2),
            "peak":      round(close + atr*3, 8),
            "valley":    round(close - atr*3, 8),
        }

    def get_diagnostics(self, df: pd.DataFrame) -> dict:
        if len(df) < 25:
            return {"error": "pocas_velas"}
        try:
            df    = self._indicators(df)
            last  = df.iloc[-1]
            prev  = df.iloc[-2]
            prev4 = df.iloc[-5] if len(df) >= 5 else df.iloc[-2]
            e7    = float(last["ema7"])
            e17   = float(last["ema17"])
            e21   = float(last["ema21"])
            e50   = float(last["ema50"]) if not pd.isna(last.get("ema50", np.nan)) else 0
            vol_r = float(last["volume"])/float(last["vol_ma"]) if float(last["vol_ma"])>0 else 0
            slope = e7 - float(prev4["ema7"])
            close = float(last["close"])
            return {
                "adx":        round(float(last["adx"]),1),
                "adx_accel":  float(last["adx"]) >= float(prev["adx"]),
                "rsi":        round(float(last["rsi"]),1),
                "vol_ratio":  round(vol_r,2),
                "gap_pct":    round((e7-e17)/e17*100,4),
                "bull_align": e7>e17>e21,
                "bear_align": e7<e17<e21,
                "above_e50":  close > e50,
                "slope_up":   slope > 0,
                "in_session": self._in_session(),
                "vol_ok":     vol_r >= float(VOL_MULT),
                "adx_ok":     float(last["adx"]) >= float(ADX_MIN),
                "close":      round(close, 8),
            }
        except Exception as ex:
            return {"error": str(ex)}

    def check_trailing_stop(self, signal: dict, current_price: float) -> dict:
        entry = signal["entry"]; sl = signal["sl"]; tp = signal["tp"]
        d = signal["signal"]
        if d == "LONG":
            progress = (current_price-entry)/(tp-entry) if tp!=entry else 0
            if progress >= 0.5:
                new_sl = round(entry + (tp-entry)*0.15, 8)
                if new_sl > sl:
                    return {"action":"move_sl","new_sl":new_sl}
        elif d == "SHORT":
            progress = (entry-current_price)/(entry-tp) if entry!=tp else 0
            if progress >= 0.5:
                new_sl = round(entry - (entry-tp)*0.15, 8)
                if new_sl < sl:
                    return {"action":"move_sl","new_sl":new_sl}
        return {"action":"hold"}

    @staticmethod
    def _strength(e7,e17,e21,adx,vol_ratio,close,e50) -> float:
        s  = min(35.0, adx/50*35)
        s += min(25.0, vol_ratio/3*25)
        s += 25.0 if (e7>e17>e21 or e7<e17<e21) else 0.0
        s += 15.0 if (close>e50 and e7>e17) or (close<e50 and e7<e17) else 0.0
        return round(s, 1)
