import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime

TG_TOKEN = "9255233645:AAEyzaiaJbfUxSq0W0-E3jsi6ZHXig-F5h0"
TG_CHAT_ID = "531386055"

# Полный список из 26 волатильных монет для нового бота
MONETS_DIV = {
    'BTC': 'BTCUSDT', 'ETH': 'ETHUSDT', 'SOL': 'SOLUSDT',
    'ENA': 'ENAUSDT', 'CAKE': 'CAKEUSDT', 'ENJ': 'ENJUSDT', 'PENDLE': 'PENDLEUSDT',
    'INJ': 'INJUSDT', 'JTO': 'JTOUSDT', 'APT': 'APTUSDT', 'SUI': 'SUIUSDT',
    'PEPE': 'PEPEUSDT', 'TIA': 'TIAUSDT', 'ARB': 'ARBUSDT', 'HYPE': 'HYPEUSDT',
    'PUMP': 'PUMPUSDT', 'ZEC': 'ZECUSDT', 'AAVE': 'AAVEUSDT', 'XRP': 'XRPUSDT',
    'AVAX': 'AVAXUSDT', 'JUP': 'JUPUSDT', 'LDO': 'LDOUSDT', 'APE': 'APEUSDT',
    'ICP': 'ICPUSDT', 'ATOM': 'ATOMUSDT'
}

def send_telegram(message):
    url = f"https://telegram.org{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Ошибка TG: {e}")

def get_live_candles(symbol, limit=150):
    url = "https://bybit.com"
    try:
        r = requests.get(url, params={'category': 'linear', 'symbol': symbol, 'interval': '60', 'limit': limit}, timeout=10).json()
        if r.get('retCode') == 0 and r['result']['list']:
            rows = r['result']['list'][::-1]
            df = pd.DataFrame(rows, columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turn'])
            for c in ['open', 'high', 'low', 'close', 'vol']: df[c] = df[c].astype(float)
            df['datetime'] = pd.to_datetime(df['ts'].astype(int), unit='ms') + pd.Timedelta(hours=5)
            return df
    except Exception:
        pass
    return None

def calculate_indicators(df):
    if df is None or len(df) < 52: return None
    
    # 1. MACD (12, 26, 9)
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['signal_macd'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['hist'] = df['macd'] - df['signal_macd']
    
    # 2. ИШИМОКУ
    df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    df['senkou_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(26)
    df['senkou_b'] = ((df['high'].rolling(52).max() + df['low'].rolling(52).min()) / 2).shift(26)
    
    # 3. ВНУТРИДНЕВНОЙ VWAP
    tp = (df['high'] + df['low'] + df['close']) / 3
    df['vwap'] = (tp * df['vol']).rolling(24).sum() / df['vol'].rolling(24).sum()
    df['vwap'] = df['vwap'].fillna(df['close'].rolling(24).mean())
    return df

def scan_divergences(name, symbol):
    try:
        df = calculate_indicators(get_live_candles(symbol, limit=120))
        if df is None: return
        
        curr = df.iloc[-1]
        cp = curr['close']
        
        max_cloud = max(curr['senkou_a'], curr['senkou_b'])
        min_cloud = min(curr['senkou_a'], curr['senkou_b'])
        cloud_status = "🟢 Выше Облака" if cp > max_cloud else ("🔴 Ниже Облака" if cp < min_cloud else "🟡 Внутри Облака")
        
        p_curr = df.iloc[-1]
        p_prev_zone = df.iloc[-15:-3]
        if len(p_prev_zone) < 10: return
        
        min_price_prev = p_prev_zone['low'].min()
        idx_min_price = p_prev_zone['low'].idxmin()
        bull_div = (p_curr['low'] < min_price_prev) and (p_curr['macd'] > df.loc[idx_min_price, 'macd']) and (p_curr['macd'] < 0)
        
        max_price_prev = p_prev_zone['high'].max()
        idx_max_price = p_prev_zone['high'].idxmax()
        bear_div = (p_curr['high'] > max_price_prev) and (p_curr['macd'] < df.loc[idx_max_price, 'macd']) and (p_curr['macd'] > 0)
        
        if bull_div and cp < curr['vwap']:
            tp = round(curr['vwap'], 4)
            sl = round(p_curr['low'] * 0.993, 4)
            send_telegram(f"📊 <b>ДИВЕРГЕНЦИЯ: ЛОНГ #{name} (1H)</b>\n\n"
                          f"📉 Цена обновила дно, но продавцы MACD выдохлись!\n"
                          f"☁️ Ишимоку: {cloud_status}\n"
                          f"🛒 Вход: <code>{round(cp, 4)}</code>\n"
                          f"🛡️ Снайперский SL: <code>{sl}</code>\n"
                          f"💰 Цель фиксации (VWAP): <code>{tp}</code>")
        elif bear_div and cp > curr['vwap']:
            tp = round(curr['vwap'], 4)
            sl = round(p_curr['high'] * 1.007, 4)
            send_telegram(f"☄️ <b>ДИВЕРГЕНЦИЯ: ШОРТ #{name} (1H)</b>\n\n"
                          f"📈 Цена забросила хай, но объемы и MACD падают!\n"
                          f"☁️ Ишимоку: {cloud_status}\n"
                          f"🛒 Вход: <code>{round(cp, 4)}</code>\n"
                          f"🛡️ Снайперский SL: <code>{sl}</code>\n"
                          f"💰 Цель фиксации (VWAP): <code>{tp}</code>")
    except Exception as e:
        print(f"Ошибка {name}: {e}")

if __name__ == "__main__":
    for name, symbol in MONETS_DIV.items():
        scan_divergences(name, symbol)
