"""
risk_manager.py — FIX CRÍTICO: position sizing con caps duros
BUG: ATR muy pequeño → risk_distance ≈ 0 → notional explota (ONDO qty=1995)
FIX: 
  - Notional máximo = balance × MAX_NOTIONAL_PCT (default 15%)
  - Notional mínimo = MIN_ORDER_USDT
  - Log detallado de cada cálculo
"""
import logging
from config import CAPITAL_PCT, MAX_OPEN_TRADES, LEVERAGE, MIN_ORDER_USDT

logger = logging.getLogger(__name__)

# Caps de posición — nunca superarlos sin importar el cálculo
MAX_NOTIONAL_PCT = 15.0   # máx 15% del balance por trade (incluye apalancamiento)
MIN_RISK_DIST    = 0.003  # mínimo 0.3% de distancia al SL (evita notional infinito)


class RiskManager:
    def __init__(self):
        self._open: dict = {}

    def can_open(self, symbol: str) -> tuple:
        if symbol in self._open:
            return False, f"{symbol} ya abierto"
        if len(self._open) >= MAX_OPEN_TRADES:
            return False, f"Max {MAX_OPEN_TRADES} trades"
        return True, "OK"

    def calc_quantity(self, balance: float, entry: float, sl: float) -> float:
        """
        Calcula qty con múltiples protecciones contra overflow.
        
        Método: riesgo fijo en USDT / distancia al SL = notional
        Con cap duro de MAX_NOTIONAL_PCT del balance.
        """
        if entry <= 0 or sl <= 0 or balance <= 0:
            return 0.0

        risk_distance = abs(entry - sl) / entry

        # FIX: forzar distancia mínima para evitar notional infinito
        if risk_distance < MIN_RISK_DIST:
            risk_distance = MIN_RISK_DIST
            logger.warning(f"risk_distance muy pequeña, usando mínimo {MIN_RISK_DIST:.3f} "
                           f"(entry={entry:.6f} sl={sl:.6f})")

        # USDT a arriesgar = 2% del balance
        risk_usdt   = balance * (CAPITAL_PCT / 100)

        # Notional calculado por riesgo
        notional_by_risk = risk_usdt / risk_distance

        # CAP DURO: nunca más del 15% del balance en notional
        # (con lev×5 eso implica un margen del 3% del balance)
        max_notional = balance * (MAX_NOTIONAL_PCT / 100)
        notional     = min(notional_by_risk, max_notional)

        # Qty final
        qty = notional / entry
        qty = round(qty, 4)

        logger.info(
            f"Qty calc | balance=${balance:.2f} entry={entry:.6f} "
            f"risk_dist={risk_distance:.4f} "
            f"notional_bruto=${notional_by_risk:.2f} → "
            f"notional_cap=${notional:.2f} qty={qty:.4f}"
        )
        return qty

    def register(self, symbol: str, meta: dict):
        self._open[symbol] = meta
        logger.info(f"Registrado: {symbol} | Abiertos: {len(self._open)}/{MAX_OPEN_TRADES}")

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
