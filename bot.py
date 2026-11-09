import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime

TG_TOKEN = "9255233645:AAEyzaiaJbfUxSq0W0-E3jsi6ZHXig-F5h0"
TG_CHAT_ID = "531386055"

# Список из 26 волатильных монет для жесткого Снайпер-режима
MONETS_DIV = {
    'BTC': 'BTCUSDT', 'ETH': 'ETHUSDT', 'SOL': 'SOLUSDT',
    'ENA': 'ENAUSDT', 'CAKE': 'CAKEUSDT', 'ENJ': 'ENJUSDT', 'PENDLE': 'PENDLEUSDT',
    'INJ': 'INJUSDT', 'JTO': 'JTOUSDT', 'APT': 'APTUSDT', 'SUI': 'SUIUSDT',
    'PEPE': 'PEPEUSDT', 'TIA': 'TIAUSDT', 'ARB': 'ARBUSDT', 'HYPE': 'HYPEUSDT',
    'PUMP': 'PUMPUSDT', 'ZEC': 'ZECUSDT', 'AAVE': 'AAVEUSDT', 'XRP': 'XRPUSDT',
    'AVAX': 'AVAXUSDT', 'JUP': 'JUPUSDT', 'LDO': 'LDOUSDT', 'APE': 'APEUSDT',
    'ICP': 'ICPUSDT', 'ATOM': 'ATOMUSDT'
}

WINDOW_4H = 4   
WINDOW_15M = 6  

def send_telegram(message):
    url = f"https://telegram.org{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Ошибка TG: {e}")

def get_live_candles(symbol, interval, limit=300):
    bybit_map = {'4h': '240', '1h': '60', '15m': '15'}
    url = "https://bybit.com"
    try:
        r = requests.get(url, params={'category': 'linear', 'symbol': symbol, 'interval': bybit_map[interval], 'limit': limit}, timeout=10).json()
        if r.get('retCode') == 0 and r['result']['list']:
            rows = r['result']['list'][::-1]
            df = pd.DataFrame(rows, columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turn'])
            for c in ['open', 'high', 'low', 'close']: df[c] = df[c].astype(float)
            df['datetime'] = pd.to_datetime(df['ts'].astype(int), unit='ms') + pd.Timedelta(hours=5)
            return df
    except Exception:
        pass
    return None

def calculate_indicators(df):
    if df is None: return None
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    
    low_14 = df['low'].rolling(window=14).min()
    high_14 = df['high'].rolling(window=14).max()
    fast_k = 100 * (df['close'] - low_14) / (high_14 - low_14)
    df['stoch_k'] = fast_k.rolling(window=3).mean()
    df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
    return df

def get_wave_pivots(df, window):
    pivots = []
    for i in range(window, len(df) - window):
        is_high = df['high'].iloc[i] == df['high'].iloc[i-window:i+window+1].max()
        is_low = df['low'].iloc[i] == df['low'].iloc[i-window:i+window+1].min()
        c_date = df['datetime'].iloc[i].strftime('%d.%m %H:%M')
        if is_high: pivots.append({'type': 'HIGH', 'price': df['high'].iloc[i], 'date': c_date})
        elif is_low: pivots.append({'type': 'LOW', 'price': df['low'].iloc[i], 'date': c_date})
    clean = []
    for p in pivots:
        if not clean or clean[-1]['type'] != p['type']: clean.append(p)
    return clean

def scan_market_sniper(name, symbol):
    try:
        df_4h = calculate_indicators(get_live_candles(symbol, '4h', limit=150))
        df_1h = calculate_indicators(get_live_candles(symbol, '1h', limit=150))
        df_15m = calculate_indicators(get_live_candles(symbol, '15m', limit=200))
        
        if df_4h is None or df_1h is None or df_15m is None: return
        
        c4h = df_4h.iloc[-1]
        c1h = df_1h.iloc[-1]
        c15 = df_15m.iloc[-1]
        cp = c15['close']
        
        above_4h_200 = c4h['close'] > c4h['ema200']
        under_4h_200 = c4h['close'] < c4h['ema200']
        
        e_bull = (cp > c15['ema50']) and (c15['ema50'] > c15['ema100'] > c15['ema200'])
        e_bear = (cp < c15['ema50']) and (c15['ema50'] < c15['ema100'] < c15['ema200'])
        
        sk15, sd15 = c15['stoch_k'], c15['stoch_d']

        # ЛОНГ СИГНАЛ (Отскок EMA50 по Бычьему тренду 4Н)
        if above_4h_200 and e_bull and (abs(cp - c15['ema50']) / c15['ema50'] < 0.003) and (sk15 < 40 and sk15 > sd15):
            sl = round(c15['ema100'] * 0.995, 4)
            # Тейк-профит для быстрого скальпинга: забираем короткое движение 1.2% от входа
            tp = round(cp * 1.012, 4)
            send_telegram(f"🚀 <b>СНАЙПЕР-ЛОНГ #{name} (15М)</b>\n\n"
                          f"🛒 Вход: <code>{round(cp, 4)}</code>\n"
                          f"🛡️ Стоп-лосс (SL): <code>{sl}</code>\n"
                          f"💰 Тейк-профит (TP): <code>{tp}</code>\n\n"
                          f"📈 <i>Стратегия: Быстрый забор импульса от EMA50 по тренду. Не пересиживать!</i>")
            return

        # ШОРТ СИГНАЛ (Отбой EMA50 по Медвежьему тренду 4Н — то, что косило ночью!)
        elif under_4h_200 and e_bear and (abs(cp - c15['ema50']) / c15['ema50'] < 0.003) and (sk15 > 60 and sk15 < sd15):
            sl = round(c15['ema100'] * 1.005, 4)
            # Тейк-профит для быстрого скальпинга: забираем короткое движение 1.2% на падение
            tp = round(cp * 0.988, 4)
            send_telegram(f"🔴 <b>СНАЙПЕР-ШОРТ #{name} (15М)</b>\n\n"
                          f"🛒 Вход: <code>{round(cp, 4)}</code>\n"
                          f"🛡️ Стоп-лосс (SL): <code>{sl}</code>\n"
                          f"💰 Тейк-профит (TP): <code>{tp}</code>\n\n"
                          f"📉 <i>Стратегия: Быстрый забор импульса от EMA50 по тренду. Не пересиживать!</i>")
            return
            
    except Exception as e:
        print(f"Ошибка {name}: {e}")

if __name__ == "__main__":
    for name, symbol in MONETS_DIV.items():
        scan_market_sniper(name, symbol)
