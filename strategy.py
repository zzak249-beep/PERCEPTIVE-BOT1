"""
strategy.py — V35 Golden Equilibrium
Port exacto del Pine Script a Python.
EMA 7/17/21 + Pivot High/Low + Vol 1.5x + ADX > 20
"""
import logging
import numpy as np
import pandas as pd
import pandas_ta as pta

from config import (
    EMA_FAST, EMA_MID, EMA_SLOW,
    PIVOT_LEN, VOL_MULT, ADX_MIN, ATR_SL_MULT,
)

logger = logging.getLogger(__name__)


class StrategyV35:
    """
    Replica fiel de //@version=6 Sniper Bot V35: Golden Equilibrium.

    Señal LONG:  crossover(EMA7, EMA17) AND low < valley AND vol > 1.5x AND ADX > 20
    Señal SHORT: crossunder(EMA7, EMA17) AND high > peak AND vol > 1.5x AND ADX > 20
    SL:  valley - ATR*0.5  (long) | peak + ATR*0.5 (short)
    TP:  EMA21
    """

    # ──────────────────────────────────────────────────────
    # Indicadores
    # ──────────────────────────────────────────────────────
    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # EMAs
        df["ema7"]  = pta.ema(df["close"], length=EMA_FAST)
        df["ema17"] = pta.ema(df["close"], length=EMA_MID)
        df["ema21"] = pta.ema(df["close"], length=EMA_SLOW)

        # Volume filter
        df["vol_ma"]      = pta.sma(df["volume"], length=20)
        df["is_inst_vol"] = df["volume"] > (df["vol_ma"] * VOL_MULT)

        # ADX
        adx_df = pta.adx(df["high"], df["low"], df["close"], length=14)
        if adx_df is not None and "ADX_14" in adx_df.columns:
            df["adx"] = adx_df["ADX_14"]
        else:
            df["adx"] = np.nan

        # ATR
        df["atr"] = pta.atr(df["high"], df["low"], df["close"], length=14)

        # Pivot High / Pivot Low (equivalente a ta.pivothigh / ta.pivotlow de Pine)
        df["raw_peak"]   = self._pivot_high(df["high"], PIVOT_LEN)
        df["raw_valley"] = self._pivot_low(df["low"], PIVOT_LEN)

        # var float peak = na  →  forward-fill (como Pine Script)
        df["peak"]   = df["raw_peak"].ffill()
        df["valley"] = df["raw_valley"].ffill()

        return df

    @staticmethod
    def _pivot_high(series: pd.Series, n: int) -> pd.Series:
        result = pd.Series(np.nan, index=series.index)
        arr = series.to_numpy()
        for i in range(n, len(arr) - n):
            window = arr[i - n: i + n + 1]
            if arr[i] == window.max() and list(window).count(arr[i]) == 1:
                result.iloc[i] = arr[i]
        return result

    @staticmethod
    def _pivot_low(series: pd.Series, n: int) -> pd.Series:
        result = pd.Series(np.nan, index=series.index)
        arr = series.to_numpy()
        for i in range(n, len(arr) - n):
            window = arr[i - n: i + n + 1]
            if arr[i] == window.min() and list(window).count(arr[i]) == 1:
                result.iloc[i] = arr[i]
        return result

    # ──────────────────────────────────────────────────────
    # Señal principal
    # ──────────────────────────────────────────────────────
    def get_signal(self, df: pd.DataFrame, adx_override: float = None) -> dict:
        """
        Evalúa la última vela cerrada.
        Retorna dict con keys: signal, sl, tp, entry, adx, strength, peak, valley, atr
        signal ∈ {"LONG", "SHORT", "NONE"}
        """
        NONE = {"signal": "NONE"}

        if len(df) < 60:
            return NONE

        df = self._add_indicators(df)

        # Necesitamos al menos 2 filas válidas
        required = ["ema7", "ema17", "ema21", "adx", "atr", "peak", "valley", "vol_ma"]
        last = df.iloc[-1]
        prev = df.iloc[-2]

        for col in required:
            if pd.isna(last[col]) or pd.isna(prev[col]):
                return NONE

        # Umbrales (pueden ser sobreescritos por el motor de aprendizaje)
        adx_threshold = adx_override if adx_override else ADX_MIN

        # ── Filtros compartidos ──
        vol_ok = bool(last["is_inst_vol"])
        adx_ok = last["adx"] > adx_threshold

        if not (vol_ok and adx_ok):
            return NONE

        # ── EMA crossover (Pine: ta.crossover / ta.crossunder) ──
        ema_cross_up   = (prev["ema7"] <= prev["ema17"]) and (last["ema7"] > last["ema17"])
        ema_cross_down = (prev["ema7"] >= prev["ema17"]) and (last["ema7"] < last["ema17"])

        # ── Rotura de estructura ──
        low_lt_valley  = last["low"]  < last["valley"]
        high_gt_peak   = last["high"] > last["peak"]

        signal = "NONE"
        if ema_cross_up   and low_lt_valley:
            signal = "LONG"
        elif ema_cross_down and high_gt_peak:
            signal = "SHORT"

        if signal == "NONE":
            return NONE

        entry = float(last["close"])
        atr   = float(last["atr"])

        # SL / TP idénticos al Pine Script
        if signal == "LONG":
            sl = float(last["valley"]) - (atr * ATR_SL_MULT)
            tp = float(last["ema21"])
        else:
            sl = float(last["peak"])  + (atr * ATR_SL_MULT)
            tp = float(last["ema21"])

        # Validar que sl/tp tienen sentido
        if signal == "LONG"  and (sl >= entry or tp <= entry):
            return NONE
        if signal == "SHORT" and (sl <= entry or tp >= entry):
            return NONE

        return {
            "signal":   signal,
            "entry":    round(entry, 8),
            "sl":       round(sl, 8),
            "tp":       round(tp, 8),
            "atr":      round(atr, 8),
            "adx":      round(float(last["adx"]), 2),
            "strength": self._strength(last),
            "peak":     round(float(last["peak"]), 8),
            "valley":   round(float(last["valley"]), 8),
            "vol_ratio": round(float(last["volume"] / last["vol_ma"]), 2),
        }

    # ──────────────────────────────────────────────────────
    # Fuerza de señal 0–100 (dashboard)
    # ──────────────────────────────────────────────────────
    @staticmethod
    def _strength(row) -> float:
        score = 0.0
        # ADX (0–40)
        score += min(40.0, (float(row["adx"]) / 50.0) * 40.0)
        # Volumen (0–30)
        if row["vol_ma"] > 0:
            ratio = float(row["volume"]) / float(row["vol_ma"])
            score += min(30.0, (ratio / 3.0) * 30.0)
        # Alineación EMA (0–30)
        e7, e17, e21 = float(row["ema7"]), float(row["ema17"]), float(row["ema21"])
        if (e7 > e17 > e21) or (e7 < e17 < e21):
            score += 30.0
        elif e7 != e17:
            score += 15.0
        return round(score, 1)
