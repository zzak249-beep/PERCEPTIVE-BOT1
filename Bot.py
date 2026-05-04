import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os

# ==========================================
# 1. CONFIGURACIÓN DEL EXCHANGE Y API
# ==========================================
API_KEY = os.getenv('BINGX_API_KEY')
SECRET_KEY = os.getenv('BINGX_SECRET_KEY')

# Inicializar BingX en modo Futuros Perpetuos
exchange = ccxt.bingx({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

# ==========================================
# 2. MOTOR DE DECISIÓN (EL CEREBRO)
# ==========================================
def check_order_book(symbol, side):
    """Analiza la liquidez real. Evita entrar contra muros de ballenas."""
    ob = exchange.fetch_order_book(symbol, limit=20)
    
    # Sumamos el volumen de las 20 mejores posiciones
    total_bids = sum([order[1] for order in ob['bids']]) # Compradores
    total_asks = sum([order[1] for order in ob['asks']]) # Vendedores
    
    # Si queremos comprar (Largo), necesitamos que haya un 20% más de fuerza compradora
    if side == 'buy' and total_bids > (total_asks * 1.2):
        return True
    # Si queremos vender (Corto), necesitamos que haya un 20% más de fuerza vendedora
    elif side == 'sell' and total_asks > (total_bids * 1.2):
        return True
        
    return False

def strategy(symbol):
    """Estrategia de Ruptura HMA + Validación de Liquidez"""
    try:
        # Extraer velas de 15 minutos
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        
        # Filtro 1: HMA Rápida para momentum
        df['hma'] = ta.hma(df['c'], length=20)
        
        # Filtro 2: Detección de Vértices (ZigZag)
        df['peak'] = df['h'].rolling(window=5, center=True).max()
        df['valley'] = df['l'].rolling(window=5, center=True).min()
        
        # Filtro 3: Volumen Relativo Institucional
        df['vol_ma'] = df['v'].rolling(window=20).mean()
        
        last_c = df['c'].iloc[-1]
        last_hma = df['hma'].iloc[-1]
        last_peak = df['peak'].iloc[-5] 
        last_valley = df['valley'].iloc[-5]
        last_v = df['v'].iloc[-1]
        vol_avg = df['vol_ma'].iloc[-1]

        # CONDICIONES DE ENTRADA
        is_volume_spike = last_v > (vol_avg * 1.5)
        
        if last_c > last_peak and last_c > last_hma and is_volume_spike:
            # Validar con el Order Book antes de confirmar
            if check_order_book(symbol, 'buy'):
                return 'buy'
                
        elif last_c < last_valley and last_c < last_hma and is_volume_spike:
            if check_order_book(symbol, 'sell'):
                return 'sell'
                
        return None
    except Exception as e:
        print(f"Error analizando {symbol}: {e}")
        return None

# ==========================================
# 3. EJECUCIÓN CONTINUA
# ==========================================
def get_top_pairs():
    """Busca los 5 pares con más dinero inyectado en las últimas 24h"""
    tickers = exchange.fetch_tickers()
    df = pd.DataFrame.from_dict(tickers, orient='index')
    df['quoteVolume'] = pd.to_numeric(df['quoteVolume'])
    top_pairs = df[df.index.str.contains('/USDT')].nlargest(5, 'quoteVolume')
    return top_pairs.index.tolist()

def run_bot():
    print("🚀 Iniciando Bot V7 Institucional en BingX...")
    while True:
        try:
            pairs = get_top_pairs()
            print(f"🔍 Escaneando liquidez en: {', '.join(pairs)}")
            
            for symbol in pairs:
                signal = strategy(symbol)
                if signal:
                    print(f"🔥 ALERTA DE TRADE CONFIRMADA: {signal.upper()} en {symbol}")
                    # exchange.create_market_order(symbol, signal, cantidad_calculada) # <-- Línea de ejecución real
                    
            print("Esperando cierre de siguiente vela...")
            time.sleep(300) # Escanea cada 5 minutos para no saturar la API
            
        except ccxt.NetworkError as e:
            print(f"Error de red: {e}. Reintentando en 10s...")
            time.sleep(10)
        except Exception as e:
            print(f"Fallo general del bot: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run_bot()
