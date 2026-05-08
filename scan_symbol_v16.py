#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  SCAN_SYMBOL V16 — WIN RATE EDITION                                 ║
║                                                                      ║
║  MEJORAS vs V15:                                                     ║
║    · Filtro de régimen de mercado (trending vs lateral)             ║
║    · Timing pullback: no entra tarde en impulsos estirados          ║
║    · Filtro spike: evita entrar tras velas de momentum extremo      ║
║    · SL por estructura de mercado (swing highs/lows)                ║
║    · Volume delta: mide presión compradora/vendedora real           ║
║    · Ponderación horaria: mayor score en horas de alta liquidez     ║
║    · Indicadores de confluencia descorelacionados                   ║
╚══════════════════════════════════════════════════════════════════════╝

INSTRUCCIONES DE INTEGRACIÓN:
  1. Copia las funciones auxiliares nuevas (calc_volume_delta,
     is_trending, find_structure_sl, get_hour_mult) al bloque
     de INDICADORES del bot original (después de calc_vwap).
  2. Reemplaza la función scan_symbol completa por la de abajo.
  3. El resto del bot (main, Telegram, BingX API) no cambia.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timezone

# ── Importa desde tu bot original ────────────────────────────────────
# from bot import (
#     calc_atr, calc_ema, calc_ema_angle, calc_adx, calc_rsi,
#     calc_supertrend, calc_heikin_ashi, calc_vwap, calc_squeeze_off,
#     analyze_h1, detect_candle_pattern, get_klines,
#     TIMEFRAME, EMA_FAST, EMA_SLOW, EMA_TREND, SLOPE_LIMIT, SLOPE_LOOK,
#     ADX_LEN, ADX_MIN, RSI_LEN, RSI_OB, RSI_OS, VOL_MULT,
#     ST_PERIOD, ST_MULT, TP_MULT, SL_ATR_MULT, MIN_DIST_PCT,
#     MIN_RR, ATR_MAX_PCT, MIN_SCORE, MIN_CONFLUENCES,
#     COOLDOWN_MINS, sl_cooldown, h1_cache, log
# )

# ══════════════════════════════════════════════════════════════════════
#  NUEVAS FUNCIONES AUXILIARES — añadir al bloque de INDICADORES
# ══════════════════════════════════════════════════════════════════════

def calc_volume_delta(df, period=3):
    """
    Mide la presión neta compradora/vendedora.
    Retorna Serie normalizada [-1, +1]:
      > 0  → presión compradora dominante
      < 0  → presión vendedora dominante
    Descorelacionado de EMAs/ADX → confluencia real.
    """
    bull_vol = df["volume"] * (df["close"] > df["open"]).astype(float)
    bear_vol = df["volume"] * (df["close"] < df["open"]).astype(float)
    total    = df["volume"].replace(0, np.nan)
    delta    = (bull_vol - bear_vol) / total
    return delta.rolling(period).mean()


def is_trending(high, low, close, period=20, threshold=1.0):
    """
    Detecta si el mercado está en tendencia real vs lateral.
    Compara el rango del período con el ATR acumulado:
      ratio > threshold → tendencia → True
      ratio <= threshold → lateral → False

    La mayoría de SL se tocan en mercado lateral. Este filtro
    es la mejora de win rate más impactante del sistema.
    """
    atr_s  = calc_atr(high, low, close, period)
    rng    = close.rolling(period).max() - close.rolling(period).min()
    # Normalizamos por √period para hacer el ratio estable
    ratio  = rng / (atr_s * (period ** 0.5))
    return ratio > threshold


def find_structure_sl(high, low, close, i, direction, atr_val, lookback=15):
    """
    SL basado en estructura de mercado (swing highs/lows reales)
    en vez de ATR fijo. El mercado respeta soportes/resistencias,
    no valores de ATR arbitrarios.

    - LONG:  SL debajo del swing low más reciente - buffer
    - SHORT: SL encima del swing high más reciente + buffer
    """
    start = max(0, i - lookback)

    if direction == "LONG":
        swing_low = float(low.iloc[start:i].min())
        sl_struct = swing_low - atr_val * 0.2
        sl_atr    = float(close.iloc[i]) - atr_val * SL_ATR_MULT
        return min(sl_struct, sl_atr)   # el más conservador
    else:
        swing_high = float(high.iloc[start:i].max())
        sl_struct  = swing_high + atr_val * 0.2
        sl_atr     = float(close.iloc[i]) + atr_val * SL_ATR_MULT
        return max(sl_struct, sl_atr)


def get_hour_mult():
    """
    Pondera el score según la hora UTC.
    Las mejores horas en cripto son apertura Londres (8-11h)
    y apertura Nueva York (14-17h). Madrugada asiática = peor calidad.
    """
    hour = datetime.now(timezone.utc).hour
    if   8 <= hour < 11:   return 1.15   # apertura Londres
    elif 14 <= hour < 17:  return 1.15   # apertura Nueva York
    elif 11 <= hour < 14:  return 1.05   # solape Londres-NY
    elif 17 <= hour < 22:  return 1.00   # tarde NY
    elif 22 <= hour or hour < 1: return 0.90  # cierre NY / transición
    else:                  return 0.80   # madrugada asiática (1-8h)


# ══════════════════════════════════════════════════════════════════════
#  SCAN_SYMBOL V16 — reemplaza la función completa del bot
# ══════════════════════════════════════════════════════════════════════

def scan_symbol(symbol):
    # ── Cooldown ──────────────────────────────────────────────────────
    if symbol in sl_cooldown:
        elapsed = (datetime.now(timezone.utc) - sl_cooldown[symbol]).total_seconds() / 60
        if elapsed < COOLDOWN_MINS:
            return None

    try:
        # ── Datos 5m ─────────────────────────────────────────────────
        df = get_klines(symbol, 200)
        if df.empty or len(df) < 100:
            return None

        h, l, c, o = df["high"], df["low"], df["close"], df["open"]

        # Indicadores base
        atr_s   = calc_atr(h, l, c, 14)
        ema_f   = calc_ema(c, EMA_FAST)
        ema_s   = calc_ema(c, EMA_SLOW)
        ema_t   = calc_ema(c, EMA_TREND)
        angle   = calc_ema_angle(ema_f, atr_s, SLOPE_LOOK)
        di_p, di_m, adx_s = calc_adx(h, l, c, ADX_LEN)
        rsi_s   = calc_rsi(c, RSI_LEN)
        vol_ma  = df["volume"].rolling(20).mean()
        sqz_off = calc_squeeze_off(h, l, c, 20, 2.0, 1.5)
        vwap_s  = calc_vwap(df)
        st_dir  = calc_supertrend(h, l, c, ST_PERIOD, ST_MULT)
        ha      = calc_heikin_ashi(df)

        # ── NUEVOS indicadores V16 ────────────────────────────────────
        vol_delta  = calc_volume_delta(df, period=3)
        trending_s = is_trending(h, l, c, period=20, threshold=1.0)

        i = len(df) - 2
        if i < 80:
            return None

        # Valores escalares
        close_now  = float(c.iloc[i])
        atr_val    = float(atr_s.iloc[i])
        if atr_val <= 0:
            return None

        atr_pct    = atr_val / close_now * 100
        if atr_pct > ATR_MAX_PCT:
            return None

        angle_now  = float(angle.iloc[i])
        adx_now    = float(adx_s.iloc[i])
        di_p_now   = float(di_p.iloc[i])
        di_m_now   = float(di_m.iloc[i])
        rsi_now    = float(rsi_s.iloc[i])
        vol_now    = float(df["volume"].iloc[i])
        vma        = float(vol_ma.iloc[i])
        sqz_ok     = bool(sqz_off.iloc[i])
        vwap_now   = float(vwap_s.iloc[i])
        st_now     = int(st_dir.iloc[i])
        ha_bull    = float(ha["ha_close"].iloc[i]) > float(ha["ha_open"].iloc[i])
        ha_bear    = not ha_bull
        vratio     = round(vol_now / vma, 2) if vma > 0 else 0.0
        ema_f_now  = float(ema_f.iloc[i])
        ema_s_now  = float(ema_s.iloc[i])
        ema_t_now  = float(ema_t.iloc[i])
        delta_now  = float(vol_delta.iloc[i]) if not np.isnan(float(vol_delta.iloc[i])) else 0.0
        trending_now = bool(trending_s.iloc[i])

        if any(np.isnan(x) for x in [angle_now, adx_now, rsi_now, atr_val,
                                      ema_f_now, ema_s_now, ema_t_now]):
            return None

        # ══ FILTRO 1: RÉGIMEN DE MERCADO ════════════════════════════
        # El filtro más impactante en win rate: no operar en lateral.
        # Si el mercado no tiene tendencia real → descarte duro.
        if not trending_now:
            return None

        # ── Dirección por EMA ─────────────────────────────────────────
        if ema_f_now > ema_s_now:
            direction = "LONG"
        elif ema_f_now < ema_s_now:
            direction = "SHORT"
        else:
            return None

        # ── RSI extremo — descarte duro ───────────────────────────────
        if direction == "LONG"  and rsi_now > RSI_OB: return None
        if direction == "SHORT" and rsi_now < RSI_OS: return None

        # ── EMA TREND filter (EMA50) ──────────────────────────────────
        if direction == "LONG"  and close_now < ema_t_now: return None
        if direction == "SHORT" and close_now > ema_t_now: return None

        # ══ FILTRO 2: SPIKE ANTERIOR ════════════════════════════════
        # Evita entrar justo después de una vela de momentum extremo
        # (suelen revertir el 60-70% del movimiento a continuación).
        prev_body = abs(float(c.iloc[i-1]) - float(o.iloc[i-1]))
        if prev_body > atr_val * 2.5:
            return None

        # ══ FILTRO 3: TIMING — PULLBACK ═════════════════════════════
        # No entrar cuando el precio está demasiado estirado desde
        # el extremo reciente. Mejor esperar retroceso mínimo.
        if direction == "LONG":
            recent_high = float(h.iloc[max(0, i-6):i].max())
            stretch     = (recent_high - close_now) / atr_val
            # Si el precio no ha retrocedido nada (stretch < 0.2),
            # estamos comprando el techo del impulso → esperar
            if stretch < 0.15:
                return None
        else:
            recent_low  = float(l.iloc[max(0, i-6):i].min())
            stretch     = (close_now - recent_low) / atr_val
            if stretch < 0.15:
                return None

        # ══ SISTEMA DE CONFLUENCIAS V16 — 7 FILTROS, MÍNIMO 4 ═══════
        # C1-C6: igual que V15. C7: Volume Delta (nuevo, descorelacionado)
        confluences = 0
        conf_detail = {}

        # C1: Slope EMA (ángulo)
        ang_ok = angle_now >= SLOPE_LIMIT if direction == "LONG" else angle_now <= -SLOPE_LIMIT
        if ang_ok: confluences += 1
        conf_detail["slope"] = f"{'✅' if ang_ok else '❌'}{angle_now:.1f}°"

        # C2: ADX con DI
        adx_ok = adx_now >= ADX_MIN and (
            (di_p_now > di_m_now and direction == "LONG") or
            (di_m_now > di_p_now and direction == "SHORT")
        )
        if adx_ok: confluences += 1
        conf_detail["adx"] = f"{'✅' if adx_ok else '❌'}{adx_now:.0f}"

        # C3: SuperTrend 5m
        st_ok = (st_now == 1 and direction == "LONG") or (st_now == -1 and direction == "SHORT")
        if st_ok: confluences += 1
        conf_detail["ST"] = f"{'✅' if st_ok else '❌'}{'▲' if st_now==1 else '▼'}"

        # C4: Heikin Ashi confirma
        ha_ok = (ha_bull and direction == "LONG") or (ha_bear and direction == "SHORT")
        if ha_ok: confluences += 1
        conf_detail["HA"] = "✅" if ha_ok else "❌"

        # C5: Volumen
        vol_ok = vratio >= VOL_MULT
        if vol_ok: confluences += 1
        conf_detail["vol"] = f"{'✅' if vol_ok else '❌'}{vratio:.1f}x"

        # C6: Squeeze OFF (mercado expandido)
        if sqz_ok: confluences += 1
        conf_detail["sqz"] = "✅OFF" if sqz_ok else "❌ON"

        # C7: Volume Delta — NUEVO (descorelacionado de EMAs)
        # Mide si el dinero real fluye en la dirección de la señal
        delta_ok = (delta_now > 0.1 and direction == "LONG") or \
                   (delta_now < -0.1 and direction == "SHORT")
        if delta_ok: confluences += 1
        conf_detail["Δvol"] = f"{'✅' if delta_ok else '❌'}{delta_now:+.2f}"

        if confluences < MIN_CONFLUENCES:
            return None

        # ── H1 alignment — NEUTRAL permitido, CONTRARIO descarta ─────
        h1_ctx   = analyze_h1(symbol)
        h1_trend = h1_ctx["h1_trend"] if h1_ctx else "NEUTRAL"
        h1_bonus = 0

        if h1_ctx:
            if h1_trend == "BULL" and direction == "LONG":
                h1_bonus = 20
            elif h1_trend == "BEAR" and direction == "SHORT":
                h1_bonus = 20
            elif h1_trend == "NEUTRAL":
                h1_bonus = 5
            else:
                return None   # H1 contra señal → descarte

        # ── Patrón de vela ────────────────────────────────────────────
        pat_name, pat_score, sl_candle = detect_candle_pattern(df, i, direction, atr_val)

        # ══ SL V16: ESTRUCTURA DE MERCADO ═══════════════════════════
        sl_price = find_structure_sl(h, l, c, i, direction, atr_val, lookback=15)

        # Respetar SL de vela si es más conservador
        if direction == "LONG":
            if sl_candle and sl_candle > 0:
                sl_price = min(sl_price, sl_candle)
            sl_price = min(sl_price, close_now * (1 - MIN_DIST_PCT / 100))
            if sl_price >= close_now:
                return None
            tp_price = close_now + (close_now - sl_price) * TP_MULT
        else:
            if sl_candle and sl_candle > 0:
                sl_price = max(sl_price, sl_candle)
            sl_price = max(sl_price, close_now * (1 + MIN_DIST_PCT / 100))
            if sl_price <= close_now:
                return None
            tp_price = close_now - (sl_price - close_now) * TP_MULT

        dist     = abs(close_now - sl_price)
        dist_pct = dist / close_now * 100
        if dist_pct < MIN_DIST_PCT:
            return None

        rr = abs(tp_price - close_now) / dist
        if rr < MIN_RR:
            return None

        # ══ SCORING V16 ══════════════════════════════════════════════
        # Añadimos: hour_mult (pondera calidad horaria)
        #           delta_bonus (presión de volumen confirma)
        #           trending_bonus (ya es hard filter, bonus extra si muy claro)
        hour_mult     = get_hour_mult()
        delta_bonus   = min(abs(delta_now) * 20, 8)  # max 8 pts
        trending_val  = float((h.iloc[max(0,i-20):i].max() - l.iloc[max(0,i-20):i].min()) /
                              (float(atr_s.iloc[i]) * (20 ** 0.5) + 1e-10))
        trend_bonus   = min((trending_val - 1.0) * 5, 7)  # max 7 pts si muy trending

        score  = (confluences / 7) * 30          # max 30  (ahora sobre 7)
        score += h1_bonus                         # max 20
        score += min(pat_score / 7, 12)           # max 12
        score += min((adx_now - ADX_MIN) / ADX_MIN * 10, 10)  # max 10
        score += min(abs(angle_now) / SLOPE_LIMIT * 8, 8)     # max 8
        score += min(vratio * 4, 8)               # max 8
        score += min((rr - MIN_RR) * 2, 5)        # max 5
        score += delta_bonus                       # max 8
        score += trend_bonus                       # max 7

        # Ponderación horaria: multiplica el score final
        score = round(score * hour_mult, 1)

        if score < MIN_SCORE:
            return None

        quality_mult = round(min(max(0.7 + (score - MIN_SCORE) / 55 * 0.6, 0.7), 1.3), 2)

        return {
            "symbol":       symbol,
            "signal":       direction,
            "pattern":      pat_name,
            "close":        close_now,
            "sl":           round(sl_price, 6),
            "tp":           round(tp_price, 6),
            "atr":          atr_val,
            "atr_pct":      round(atr_pct, 2),
            "vol_ratio":    vratio,
            "vol_delta":    round(delta_now, 3),
            "angle":        round(angle_now, 1),
            "adx":          round(adx_now, 1),
            "rsi":          round(rsi_now, 1),
            "score":        score,
            "rr":           round(rr, 2),
            "dist_pct":     round(dist_pct, 3),
            "confluences":  confluences,
            "conf_detail":  conf_detail,
            "h1_trend":     h1_trend,
            "pat_score":    round(pat_score, 1),
            "quality_mult": quality_mult,
            "trending":     round(trending_val, 2),
            "hour_mult":    hour_mult,
        }

    except Exception as e:
        log.debug(f"Scan {symbol}: {e}")
        return None
