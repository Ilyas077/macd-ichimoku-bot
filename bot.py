import time
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

# --- НАСТРОЙКИ ВАШЕГО ВТОРОГО БОТА (ТОКЕН С ФОТО) ---
TG_TOKEN = "9255233645:AAEyzaiaJbfUxSq0W0-E3jsi6ZHXig-F5h0"
TG_CHAT_ID = "531386055"

# ОПТИМАЛЬНЫЙ ТОП-12 ИЗ ВАШЕГО СПИСКА ДЛЯ СТАБИЛЬНОЙ РАБОТЫ 24/7
MONETS_DIV = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "INJ": "INJUSDT",
    "SUI": "SUIUSDT",
    "XRP": "XRPUSDT",
    "AVAX": "AVAXUSDT",
    "TAO": "TAOUSDT",
    "HYPE": "HYPEUSDT",
    "ENA": "ENAUSDT",
    "JTO": "JTOUSDT",
    "AAVE": "AAVEUSDT"
}

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
            return df
    except Exception:
        return None

def calculate_indicators(df):
    if df is None or df.empty: return None
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    denom_rsi = loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + (gain / denom_rsi)))
    
    low_14 = df['low'].rolling(window=14).min()
    high_14 = df['high'].rolling(window=14).max()
    denom_stoch = high_14 - low_14
    denom_stoch = denom_stoch.replace(0, np.nan)
    
    fast_k = 100 * (df['close'] - low_14) / denom_stoch
    df['stoch_k'] = fast_k.rolling(window=3).mean()
    df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
    return df

def scan_market_sniper(name, symbol):
    try:
        df_4h = calculate_indicators(get_live_candles(symbol, '4h', limit=150))
        df_1h = calculate_indicators(get_live_candles(symbol, '1h', limit=150))
        df_15m = calculate_indicators(get_live_candles(symbol, '15m', limit=200))
        
        if df_4h is None or df_1h is None or df_15m is None: return
        
        c4h = df_4h.iloc[-1]
        c1h = df_1h.iloc[-1]
        c15 = df_15m.iloc[-1]
        p15 = df_15m.iloc[-2]
        cp = c15['close']
        
        above_4h_200 = c4h['close'] > c4h['ema200']
        under_4h_200 = c4h['close'] < c4h['ema200']
        
        e_bull = (cp > c15['ema50']) and (c15['ema50'] > c15['ema100'] > c15['ema200'])
        e_bear = (cp < c15['ema50']) and (c15['ema50'] < c15['ema100'] < c15['ema200'])
        
        sk15, sd15 = c15['stoch_k'], c15['stoch_d']

        # ЛОНГ СИГНАЛ
        if above_4h_200 and e_bull and (abs(cp - c15['ema50']) / c15['ema50'] < 0.003) and (sk15 < 40 and sk15 > sd15):
            sl = round(c15['ema100'] * 0.995, 4)
            tp = round(cp * 1.012, 4)
            send_telegram(f"🚀 <b>СНАЙПЕР-ЛОНГ #{name} (15М)</b>\n\n"
                          f"🛒 Вход: <code>{round(cp, 4)}</code>\n"
                          f"🛡️ Стоп-лосс (SL): <code>{sl}</code>\n"
                          f"💰 Тейк-профит (TP): <code>{tp}</code>\n\n"
                          f"📈 <i>Стратегия: Быстрый забор импульса от EMA50 по тренду. Не пересиживать!</i>")
            return

        # ШОРТ СИГНАЛ
        elif under_4h_200 and e_bear and (abs(cp - c15['ema50']) / c15['ema50'] < 0.003) and (sk15 > 60 and sk15 < sd15):
            sl = round(c15['ema100'] * 1.005, 4)
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
    send_telegram("🤖 <b>Второй Бот Снайпер (4H + 1H + 15M) успешно запущен на отдельный токен 24/7!</b>\nМониторинг ТОП-12 монет в этот чат активен.")
    
    while True:
        for name, symbol in MONETS_DIV.items():
            scan_market_sniper(name, symbol)
            time.sleep(2)
        time.sleep(30)
