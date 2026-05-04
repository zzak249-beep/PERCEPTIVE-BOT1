import os

# ==========================================
# BINGX API
# ==========================================
BINGX_API_KEY    = os.getenv("BINGX_API_KEY", "")
BINGX_SECRET_KEY = os.getenv("BINGX_SECRET_KEY", "")
BASE_URL         = "https://open-api.bingx.com"

# ==========================================
# TELEGRAM
# ==========================================
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ==========================================
# ESTRATEGIA ZIGZAG ELITE V6
# ==========================================
PIVOT_LEN    = int(os.getenv("PIVOT_LEN", "5"))          # Profundidad ZigZag
VOL_MULT     = float(os.getenv("VOL_MULT", "1.5"))        # Multiplicador Vol. Institucional
ATR_LEN      = int(os.getenv("ATR_LEN", "14"))            # Periodo ATR
TP_MULT      = float(os.getenv("TP_MULT", "2.0"))         # RR ratio
TIMEFRAME    = os.getenv("TIMEFRAME", "1m")               # Temporalidad principal

# ==========================================
# GESTIÓN DE RIESGO
# ==========================================
LEVERAGE         = int(os.getenv("LEVERAGE", "10"))
RISK_PCT         = float(os.getenv("RISK_PCT", "1.5"))    # % balance por trade
MAX_POSITIONS    = int(os.getenv("MAX_POSITIONS", "5"))   # Posiciones simultáneas
MAX_DAILY_LOSS   = float(os.getenv("MAX_DAILY_LOSS", "5.0"))  # % drawdown diario máximo

# ==========================================
# SCANNER DE PARES EXPLOSIVOS
# ==========================================
TOP_PAIRS         = int(os.getenv("TOP_PAIRS", "20"))     # Top pares a tradear por día
SCAN_HOUR         = int(os.getenv("SCAN_HOUR", "0"))      # Hora UTC del re-scan diario
VOL_SURGE_MULT    = float(os.getenv("VOL_SURGE_MULT", "2.0"))   # Vol 24h vs 7d para detectar explosión
MOMENTUM_PERIODS  = int(os.getenv("MOMENTUM_PERIODS", "20"))     # Velas para momentum score
MIN_PRICE_USDT    = float(os.getenv("MIN_PRICE_USDT", "0.001"))  # Precio mínimo

# ==========================================
# TIMING
# ==========================================
CANDLE_SLEEP  = int(os.getenv("CANDLE_SLEEP", "30"))   # Segundos entre checks (30s para 1m candles)
KLINE_LIMIT   = int(os.getenv("KLINE_LIMIT", "100"))   # Velas a descargar por par
