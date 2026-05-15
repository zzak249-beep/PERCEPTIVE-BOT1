"""
risk_manager.py — MEJORA: filtro de correlación
No abrir más de 1 LONG y 1 SHORT simultáneamente.
Los mercados crypto están 80%+ correlacionados — 3 SHORTs = 1 trade con 3x pérdida.
"""
import logging
from config import CAPITAL_PCT, MAX_OPEN_TRADES, LEVERAGE, MIN_ORDER_USDT

logger = logging.getLogger(__name__)

MAX_NOTIONAL_PCT = 15.0
MIN_RISK_DIST    = 0.005  # 0.5% mínimo — en 15m es normal
MAX_PER_DIRECTION = 1   # máximo 1 LONG y 1 SHORT abiertos simultáneamente


class RiskManager:
    def __init__(self):
        self._open: dict = {}

    def can_open(self, symbol: str, direction: str = None) -> tuple:
        if symbol in self._open:
            return False, f"{symbol} ya abierto"
        if len(self._open) >= MAX_OPEN_TRADES:
            return False, f"Max {MAX_OPEN_TRADES} trades simultáneos"

        # Filtro de correlación: max 1 por dirección
        if direction:
            same_dir = [s for s,t in self._open.items()
                        if t.get("direction") == direction]
            if len(same_dir) >= MAX_PER_DIRECTION:
                return False, f"Ya hay {len(same_dir)} {direction} abierto(s) — correlación alta"

        return True, "OK"

    def calc_quantity(self, balance: float, entry: float, sl: float) -> float:
        if entry <= 0 or sl <= 0 or balance <= 0:
            return 0.0

        risk_distance = abs(entry - sl) / entry
        if risk_distance < MIN_RISK_DIST:
            risk_distance = MIN_RISK_DIST
            logger.warning(f"risk_distance pequeña, usando mínimo {MIN_RISK_DIST} "
                           f"(entry={entry:.6f} sl={sl:.6f})")

        risk_usdt    = balance * (CAPITAL_PCT / 100)
        notional_raw = risk_usdt / risk_distance
        max_notional = balance * (MAX_NOTIONAL_PCT / 100)
        notional     = min(notional_raw, max_notional)
        qty          = round(notional / entry, 4)

        logger.info(f"Qty | bal=${balance:.2f} entry={entry:.6f} "
                    f"risk_dist={risk_distance:.4f} "
                    f"notional_bruto=${notional_raw:.2f} → "
                    f"notional_cap=${notional:.2f} qty={qty:.4f}")
        return qty

    def register(self, symbol: str, meta: dict):
        self._open[symbol] = meta
        dirs = {t.get("direction","?") for t in self._open.values()}
        logger.info(f"Registrado: {symbol} | Abiertos: {len(self._open)}/{MAX_OPEN_TRADES} | Dirs: {dirs}")

    def close(self, symbol: str) -> dict | None:
        trade = self._open.pop(symbol, None)
        if trade:
            logger.info(f"Cerrado: {symbol} | Abiertos: {len(self._open)}/{MAX_OPEN_TRADES}")
        return trade

    def is_open(self, symbol: str) -> bool:
        return symbol in self._open

    def get_open(self) -> dict:
        return dict(self._open)

    def open_count(self) -> int:
        return len(self._open)

    def direction_count(self, direction: str) -> int:
        return sum(1 for t in self._open.values() if t.get("direction") == direction)
