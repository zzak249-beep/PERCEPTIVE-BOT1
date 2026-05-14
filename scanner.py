"""
scanner.py — FIX: filtrar símbolos pausados (NCCO1OIL, WTI, etc.)
FIX: validar klines antes de añadir al top
FIX: blocklist ampliada con commodities y símbolos sintéticos
"""
import logging
import re
from typing import List, Dict
from bingx_client import BingXClient
from config import TOP_N_SYMBOLS, CANDLE_INTERVAL

logger = logging.getLogger(__name__)

# Patrones de símbolos problemáticos/pausados
BLOCKLIST_EXACT = {
    "LUNA-USDT", "LUNC-USDT", "SHIB-USDT",
}

# Prefijos bloqueados (commodities sintéticos, índices, etc.)
BLOCKLIST_PREFIX = ("NCCO", "WTI", "GOLD", "OIL", "GAS", "SILVER",)

# Mínimo volumen 24h (USDT) para considerar el par
MIN_VOL_USDT = 2_000_000   # 2M USDT — filtra pares sin liquidez real


def _is_blocked(symbol: str) -> bool:
    if symbol in BLOCKLIST_EXACT:
        return True
    base = symbol.replace("-USDT", "")
    for prefix in BLOCKLIST_PREFIX:
        if base.startswith(prefix):
            return True
    # Filtrar símbolos con números raros (sintéticos tipo NCCO1OILWTI2)
    if re.search(r'\d', base) and len(base) > 6:
        return True
    return False


class MarketScanner:
    def __init__(self, client: BingXClient):
        self.client   = client
        self._cached: List[Dict] = []
        self._paused: set = set()   # cache de símbolos pausados confirmados

    def get_top_symbols(self, n: int = TOP_N_SYMBOLS) -> List[Dict]:
        tickers = self.client.get_24h_tickers()
        if not tickers:
            logger.warning("Sin tickers — usando caché")
            return self._cached or []

        scored = []
        for t in tickers:
            symbol = t.get("symbol", "")

            if not symbol.endswith("-USDT"):
                continue
            if _is_blocked(symbol):
                continue
            if symbol in self._paused:
                continue

            try:
                price  = float(t.get("lastPrice", 0) or 0)
                vol    = float(t.get("quoteVolume", 0) or 0)
                change = float(t.get("priceChangePercent", 0) or 0)

                if price <= 0 or vol < MIN_VOL_USDT:
                    continue

                score = vol * (1 + abs(change) / 100)
                scored.append({
                    "symbol":      symbol,
                    "price":       price,
                    "change_pct":  round(change, 2),
                    "volume_usdt": round(vol, 0),
                    "score":       score,
                })
            except Exception:
                continue

        scored.sort(key=lambda x: x["score"], reverse=True)

        # Tomar el doble y validar klines para filtrar pausados
        top_raw = scored[:n * 2]
        top     = []
        for s in top_raw:
            if len(top) >= n:
                break
            if s["symbol"] in self._paused:
                continue
            df = self.client.get_klines(s["symbol"], CANDLE_INTERVAL, limit=5)
            if df.empty:
                logger.info(f"[Scanner] {s['symbol']} pausado — excluido")
                self._paused.add(s["symbol"])
                continue
            top.append(s)

        self._cached = top
        if top:
            logger.info(
                f"Scanner: {len(top)} pares válidos | "
                f"1º {top[0]['symbol']} vol=${top[0]['volume_usdt']/1e6:.1f}M | "
                f"Pausados conocidos: {len(self._paused)}"
            )
        return top

    def get_symbol_list(self) -> List[str]:
        return [s["symbol"] for s in self._cached]

    def mark_paused(self, symbol: str):
        """Llamar desde el tick cuando BingX devuelve 'is pause currently'."""
        if symbol not in self._paused:
            logger.info(f"[Scanner] Marcando {symbol} como pausado")
            self._paused.add(symbol)
            self._cached = [s for s in self._cached if s["symbol"] != symbol]

    def summary_text(self, top: List[Dict], n: int = 5) -> str:
        lines = []
        for i, s in enumerate(top[:n], 1):
            arrow = "🟢" if s["change_pct"] >= 0 else "🔴"
            lines.append(
                f"  {i}. {arrow} <b>{s['symbol']}</b> "
                f"{s['change_pct']:+.2f}%  "
                f"Vol ${s['volume_usdt']/1e6:.1f}M"
            )
        return "\n".join(lines)
