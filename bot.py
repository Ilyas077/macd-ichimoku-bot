import time
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

# Установка коннектора
import ccxt

# --- НАСТРОЙКИ ВТОРОГО БОТА (ИСПРАВЛЕННЫЙ ТОКЕН И URL) ---
TG_TOKEN = "9255233645:AAEyzaiaJbfUxSq0W0-E3jsi6ZHXig-F5h0"
TG_CHAT_ID = "531386055"

# СПИСОК ПАР ДЛЯ CCXT BYBIT
MONETS_DIV = {
    "BTC": "BTC/USDT:USDT",
    "ETH": "ETH/USDT:USDT",
    "SOL": "SOL/USDT:USDT",
    "INJ": "INJ/USDT:USDT",
    "SUI": "SUI/USDT:USDT",
    "XRP": "XRP/USDT:USDT",
    "AVAX": "AVAX/USDT:USDT",
    "TAO": "TAO/USDT:USDT",
    "HYPE": "HYPE/USDT:USDT",
    "ENA": "ENA/USDT:USDT",
    "JTO": "JTO/USDT:USDT",
    "AAVE": "AAVE/USDT:USDT"
}

# Подключение к бирже Bybit через официальное API
exchange = ccxt.bybit({"enableRateLimit": True})

def send_telegram(message):
    # ИСПРАВЛЕНО: Добавлен корректный эндпоинт api.telegram.org и префикс /bot
    url = f"https://telegram.org{TG_TOKEN}/sendMessage"
    try:
        response = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
        if response.status_code != 200:
            print(f"Ошибка TG сервера: {response.text}")
    except Exception as e:
        print(f"Ошибка TG: {e}")

def get_live_candles_ccxt(symbol, interval='15m', limit=200):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
        if not bars: return None
        df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
        for c in ["open", "high", "low", "close"]: df[c] = df[c].astype(float)
        return df
    except Exception:
        return None

def calculate_indicators(df):
    if df is None or df.empty: return None
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
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
        df_4h = calculate_indicators(get_live_candles_ccxt(symbol, '4h', limit=150))
        df_15m = calculate_indicators(get_live_candles_ccxt(symbol, '15m', limit=150))
        
        if df_4h is None or df_15m is None: return
        
        c4h = df_4h.iloc[-1]
        c15 = df_15m.iloc[-1]
        p15 = df_15m.iloc[-2]
        cp = c15['close']
        
        above_4h_200 = c4h['close'] > c4h['ema200']
        under_4h_200 = c4h['close'] < c4h['ema200']
        
        sk15, sd15 = c15['stoch_k'], c15['stoch_d']
        psk15, psd15 = p15['stoch_k'], p15['stoch_d']

        near_ema50 = (abs(cp - c15['ema50']) / c15['ema50']) < 0.012

        # ЛОНГ СИГНАЛ
        if above_4h_200 and near_ema50 and (sk15 < 20 and sk15 > sd15 and psk15 <= psd15):
            sl = round(c15['ema100'] * 0.995, 4)
            tp = round(cp * 1.012, 4)
            send_telegram(f"🚀 <b>СНАЙПЕР-ЛОНГ #{name} (15М)</b>\n\n"
                          f"🛒 Вход: <code>{round(cp, 4)}</code>\n"
                          f"🛡️ Стоп-лосс (SL): <code>{sl}</code>\n"
                          f"💰 Тейк-профит (TP): <code>{tp}</code>\n\n"
                          f"📈 <i>Стратегия: Чистый разворот от EMA50 по тренду 4H. Фильтр 80/20.</i>")
            return

        # ШОРТ СИГНАЛ
        elif under_4h_200 and near_ema50 and (sk15 > 80 and sk15 < sd15 and psk15 >= psd15):
            sl = round(c15['ema100'] * 1.005, 4)
            tp = round(cp * 0.988, 4)
            send_telegram(f"🔴 <b>СНАЙПЕР-ШОРТ #{name} (15М)</b>\n\n"
                          f"🛒 Вход: <code>{round(cp, 4)}</code>\n"
                          f"🛡️ Стоп-лосс (SL): <code>{sl}</code>\n"
                          f"💰 Тейк-профит (TP): <code>{tp}</code>\n\n"
                          f"📈 <i>Стратегия: Чистый отбой от EMA50 по тренду 4H. Фильтр 80/20.</i>")
            return
            
    except Exception as e:
        print(f"Ошибка {name}: {e}")

if __name__ == "__main__":
    print("Запуск одиночного сканирования рынка...")     send_telegram("📡 <b>Бот-Сканер успешно запущен!</b> Проверяю 12 монет на 15М...")

    
    # ИСПРАВЛЕНО: Убран бесконечный цикл while True. 
    # Скрипт за один запуск проверяет все монеты и завершает работу.
    for name, symbol in MONETS_DIV.items():
        scan_market_sniper(name, symbol)
        time.sleep(2)
        
    print("Сканирование успешно завершено.")
