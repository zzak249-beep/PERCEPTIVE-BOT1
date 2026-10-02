"""Configuración 100% por variables de entorno (Railway -> Variables)."""
import os

_TRUE = ("1", "true", "yes", "on", "si", "sí")


def _s(name, default=""):
    return os.getenv(name, str(default)).strip()


def _b(name, default=False):
    return _s(name, "1" if default else "0").lower() in _TRUE


def _i(name, default):
    try:
        return int(float(_s(name, default)))
    except ValueError:
        return int(default)


def _f(name, default):
    try:
        return float(_s(name, default))
    except ValueError:
        return float(default)


def _l(name, default=""):
    return [x.strip() for x in _s(name, default).replace(";", ",").split(",") if x.strip()]


class Cfg:
    # --- Telegram ---
    TELEGRAM_TOKEN = _s("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = _s("TELEGRAM_CHAT_ID")

    # --- Escáner ---
    TIMEFRAME = _s("TIMEFRAME", "15m")
    STRICTNESS = _s("STRICTNESS", "standard").lower()   # conservative | standard | aggressive
    TOP_N = _i("TOP_N", 0)                              # 0 = TODOS los pares; si no, top-N por volumen 24h
    MIN_QUOTE_VOL = _f("MIN_QUOTE_VOL", 0)              # volumen 24h mínimo en USDT (0 = sin filtro)
    SYMBOLS = [x.upper() for x in _l("SYMBOLS")]        # lista fija (anula TOP_N). Ej: BTC-USDT,ETH-USDT
    EXCLUDE = [x.upper() for x in _l("EXCLUDE")]
    WARMUP_BARS = _i("WARMUP_BARS", 500)
    WORKERS = _i("WORKERS", 6)
    REQ_INTERVAL = _f("REQ_INTERVAL", 0.11)             # seg entre peticiones a BingX (límite ~100 req/10s)
    CLOSE_DELAY_S = _f("CLOSE_DELAY_S", 3)
    UNIVERSE_REFRESH_H = _f("UNIVERSE_REFRESH_H", 6)

    # --- Señales ---
    SL_BUFFER_ATR = _f("SL_BUFFER_ATR", 0.25)
    MIN_RR = _f("MIN_RR", 1.5)                          # RR mínimo (a TP2) para emitir señal
    MAX_SL_PCT = _f("MAX_SL_PCT", 8.0)                  # descarta señales con SL más lejos de este %
    COOLDOWN_BARS = _i("COOLDOWN_BARS", 8)              # velas de enfriamiento por símbolo
    ALERT_EVENTS = [x.lower() for x in _l("ALERT_EVENTS", "spring,utad,sos,sow")]  # "all" | "none" | lista
    HEARTBEAT_H = _f("HEARTBEAT_H", 12)                 # 0 = desactivado

    # --- BingX ---
    BINGX_API_KEY = _s("BINGX_API_KEY")
    BINGX_API_SECRET = _s("BINGX_API_SECRET")
    POSITION_MODE = _s("POSITION_MODE", "hedge").lower()  # hedge | oneway

    # --- Ejecución automática (OFF por defecto) ---
    AUTO_TRADE = _b("AUTO_TRADE", False)
    RISK_PCT = _f("RISK_PCT", 1.0)                      # % de equity arriesgado por operación
    LEVERAGE = _i("LEVERAGE", 5)
    MARGIN_TYPE = _s("MARGIN_TYPE", "ISOLATED").upper()
    MAX_POSITIONS = _i("MAX_POSITIONS", 3)
    TP1_FRAC = _f("TP1_FRAC", 0.5)                      # fracción cerrada en TP1 (resto a TP2)

    LOG_LEVEL = _s("LOG_LEVEL", "INFO").upper()


cfg = Cfg()
