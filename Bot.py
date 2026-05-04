import ccxt
import pandas as pd
import pandas_ta as ta
import time
import os

# Configuración de BingX (Usa variables de entorno por seguridad)
API_KEY = os.getenv('BINGX_API_KEY')
SECRET_KEY = os.getenv('BINGX_SECRET_KEY')

exchange = ccxt.bingx({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'options': {'defaultType': 'swap'} # Operar en Futuros Perpetuos
})

def get_top_pairs():
    """Escanea y devuelve los 5 pares con más volumen en las últimas 24h"""
    tickers = exchange.fetch_tickers()
    df = pd.DataFrame.from_dict(tickers, orient='index')
    df['quoteVolume'] = pd.to_numeric(df['quoteVolume'])
    top_pairs = df[df.index.str.contains('/USDT')].nlargest(5, 'quoteVolume')
    return top_pairs.index.tolist()

def strategy(symbol):
    """Lógica HMA + ZigZag Breakout"""
    bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
    df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
    
    # 1. HMA (Hull Moving Average) - El filtro más rápido
    df['hma'] = ta.hma(df['c'], length=20)
    
    # 2. ZigZag (Simulado con Pivotes)
    df['peak'] = df['h'].rolling(window=5, center=True).max()
    df['valley'] = df['l'].rolling(window=5, center=True).min()
    
    last_c = df['c'].iloc[-1]
    last_hma = df['hma'].iloc[-1]
    last_peak = df['peak'].iloc[-5] # Pico confirmado
    last_valley = df['valley'].iloc[-5] # Valle confirmado

    # Lógica de Ejecución
    if last_c > last_peak and last_c > last_hma:
        return 'buy'
    elif last_c < last_valley and last_c < last_hma:
        return 'sell'
    return None

def run_bot():
    print("Iniciando Escáner de BingX...")
    while True:
        try:
            pairs = get_top_pairs()
            for symbol in pairs:
                signal = strategy(symbol)
                if signal:
                    print(f"Señal detectada en {symbol}: {signal}")
                    # Aquí iría la orden real: exchange.create_market_order(symbol, signal, amount)
            time.sleep(60) # Esperar 1 minuto
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run_bot()
