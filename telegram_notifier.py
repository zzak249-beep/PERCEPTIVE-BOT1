import asyncio
import aiohttp
from datetime import datetime
import config

TELEGRAM_API = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"


async def send(session: aiohttp.ClientSession, text: str, parse_mode: str = "HTML"):
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        print(f"[TG-OFF] {text}")
        return
    try:
        async with session.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }) as r:
            pass
    except Exception as e:
        print(f"[TG-ERROR] {e}")


async def bot_start(session):
    await send(session,
        "🤖 <b>ZigZag Institutional Elite V6</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "✅ Bot iniciado correctamente\n"
        f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"📊 Timeframe: <code>{config.TIMEFRAME}</code>\n"
        f"⚡ Leverage: <code>{config.LEVERAGE}x</code>\n"
        f"💰 Riesgo/trade: <code>{config.RISK_PCT}%</code>\n"
        f"🎯 Max posiciones: <code>{config.MAX_POSITIONS}</code>"
    )


async def scanner_result(session, pairs: list, balance: float):
    pairs_str = "\n".join([f"  • <code>{p}</code>" for p in pairs[:20]])
    await send(session,
        f"🔭 <b>SCAN DIARIO — PARES EXPLOSIVOS</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Balance: <code>{balance:.2f} USDT</code>\n"
        f"🏆 Top {len(pairs)} pares seleccionados:\n"
        f"{pairs_str}"
    )


async def trade_entry(session, symbol: str, side: str, entry: float,
                      sl: float, tp: float, qty: float, balance: float,
                      rr: float, atr: float):
    emoji = "🟢 LONG" if side == "BUY" else "🔴 SHORT"
    sl_pct = abs(entry - sl) / entry * 100
    tp_pct = abs(tp - entry) / entry * 100
    await send(session,
        f"{emoji} <b>ENTRADA</b> — <code>{symbol}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💲 Precio entrada: <code>{entry:.6g}</code>\n"
        f"🛑 Stop Loss:      <code>{sl:.6g}</code>  (-{sl_pct:.2f}%)\n"
        f"🎯 Take Profit:    <code>{tp:.6g}</code>  (+{tp_pct:.2f}%)\n"
        f"📦 Cantidad:       <code>{qty:.4f}</code>\n"
        f"⚖️ RR Ratio:       <code>1:{rr:.1f}</code>\n"
        f"🌊 ATR:            <code>{atr:.6g}</code>\n"
        f"💵 Balance:        <code>{balance:.2f} USDT</code>\n"
        f"⏰ {datetime.utcnow().strftime('%H:%M:%S')} UTC"
    )


async def trade_exit(session, symbol: str, side: str, entry: float,
                     exit_price: float, pnl: float, pnl_pct: float,
                     reason: str):
    if pnl >= 0:
        emoji = "✅"
        result = "GANANCIA"
    else:
        emoji = "❌"
        result = "PÉRDIDA"
    dir_emoji = "🟢" if side == "BUY" else "🔴"
    await send(session,
        f"{emoji} <b>CIERRE — {result}</b> — <code>{symbol}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"{dir_emoji} Dirección: <code>{'LONG' if side=='BUY' else 'SHORT'}</code>\n"
        f"💲 Entrada:  <code>{entry:.6g}</code>\n"
        f"💲 Salida:   <code>{exit_price:.6g}</code>\n"
        f"💰 PnL:      <code>{pnl:+.4f} USDT ({pnl_pct:+.2f}%)</code>\n"
        f"📋 Motivo:   <code>{reason}</code>\n"
        f"⏰ {datetime.utcnow().strftime('%H:%M:%S')} UTC"
    )


async def signal_detected(session, symbol: str, side: str, close: float, peak: float, valley: float, vol_ratio: float):
    emoji = "🟢" if side == "BUY" else "🔴"
    await send(session,
        f"{emoji} <b>SEÑAL DETECTADA</b> — <code>{symbol}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Tipo:       <code>{'LONG BREAKOUT' if side=='BUY' else 'SHORT BREAKOUT'}</code>\n"
        f"💲 Close:      <code>{close:.6g}</code>\n"
        f"📈 Peak:       <code>{peak:.6g}</code>\n"
        f"📉 Valley:     <code>{valley:.6g}</code>\n"
        f"📊 Vol ratio:  <code>{vol_ratio:.2f}x</code>"
    )


async def daily_summary(session, total_trades: int, wins: int, pnl: float, balance: float):
    wr = (wins / total_trades * 100) if total_trades else 0
    await send(session,
        f"📊 <b>RESUMEN DIARIO</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📈 Trades hoy:  <code>{total_trades}</code>\n"
        f"✅ Wins:        <code>{wins}</code>  ({wr:.1f}%)\n"
        f"❌ Losses:      <code>{total_trades - wins}</code>\n"
        f"💰 PnL neto:    <code>{pnl:+.4f} USDT</code>\n"
        f"💵 Balance:     <code>{balance:.2f} USDT</code>\n"
        f"⏰ {datetime.utcnow().strftime('%Y-%m-%d')} UTC"
    )


async def error_alert(session, msg: str):
    await send(session,
        f"⚠️ <b>ERROR</b>\n"
        f"<code>{msg[:500]}</code>\n"
        f"⏰ {datetime.utcnow().strftime('%H:%M:%S')} UTC"
    )


async def daily_loss_limit(session, daily_pnl: float, limit: float, balance: float):
    await send(session,
        f"🚨 <b>LÍMITE PÉRDIDA DIARIA ALCANZADO</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📉 PnL hoy:    <code>{daily_pnl:+.4f} USDT</code>\n"
        f"🛑 Límite:     <code>-{limit:.1f}%</code>\n"
        f"💵 Balance:    <code>{balance:.2f} USDT</code>\n"
        f"⏸️ Trading PAUSADO hasta mañana"
    )
