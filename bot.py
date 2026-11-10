import os
import time
import base64
import datetime
import requests
import numpy as np
import pandas as pd

# --- 1. НАСТРОЙКИ ---
TG_TOKEN = "9255233645:AAFk5WNpiMgyRS50hKj1QE6xrNUMKDrr2vo"
TG_CHAT_ID = "531386055"

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "INJUSDT", 
    "SUIUSDT", "XRPUSDT", "AVAXUSDT", "TAOUSDT", 
    "HYPEUSDT", "ENAUSDT", "JTOUSDT", "AAVEUSDT"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json"
}

CB_BASE = base64.b64decode("aHR0cHM6Ly9hcGkuZXhjaGFuZ2UuY29pbmJhc2UuY29tL3Byb2R1Y3RzLw==").decode()
BV_URL = base64.b64decode("aHR0cHM6Ly9kYXRhLWFwaS5iaW5hbmNlLnZpc2lvbi9hcGkvdjMva2xpbmVz").decode()

# --- 2. ОТПРАВКА В TELEGRAM (ЗАЩИЩЕННЫЙ URL) ---
TG_API_BASE = base64.b64decode("aHR0cHM6Ly9hcGkudGVsZWdyYW0ub3JnL2JvdA==").decode()

def send_telegram(message):
    url = f"{TG_API_BASE}{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
        if r.status_code != 200:
            print(f"Ошибка Telegram API: {r.text}")
    except Exception as e:
        print(f"Сбой отправки в Telegram: {e}")

# --- 3. ПОЛУЧЕНИЕ ЧАСОВЫХ СВЕЧЕЙ (1H) ---
def get_1h_candles(symbol, limit=150):
    coin = symbol.replace("USDT", "")
    
    # Канал 1: Coinbase
    url_cb = f"{CB_BASE}{coin}-USD/candles"
    try:
        r = requests.get(url_cb, params={"granularity": 3600}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 60:
                df = pd.DataFrame(data[:limit], columns=['timestamp', 'low', 'high', 'open', 'close', 'volume'])
                df = df.iloc[::-1].reset_index(drop=True)
                for col in ['open', 'high', 'low', 'close']:
                    df[col] = df[col].astype(float)
                return df
    except Exception:
        pass

    # Канал 2: Зеркало Binance Vision
    try:
        r_bv = requests.get(BV_URL, params={"symbol": symbol, "interval": "1h", "limit": limit}, headers=HEADERS, timeout=10)
        if r_bv.status_code == 200:
            data_bv = r_bv.json()
            if isinstance(data_bv, list) and len(data_bv) > 60:
                df = pd.DataFrame([row[:6] for row in data_bv], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                for col in ['open', 'high', 'low', 'close']:
                    df[col] = df[col].astype(float)
                return df
    except Exception:
        pass

    return None

# --- 4. РАСЧЕТ MACD И ОБЛАКА ИШИМОКУ ---
def add_ichimoku_macd(df):
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    high_9 = df['high'].rolling(window=9).max()
    low_9 = df['low'].rolling(window=9).min()
    tenkan_sen = (high_9 + low_9) / 2

    high_26 = df['high'].rolling(window=26).max()
    low_26 = df['low'].rolling(window=26).min()
    kijun_sen = (high_26 + low_26) / 2

    df['senkou_a'] = ((tenkan_sen + kijun_sen) / 2).shift(26)
    
    high_52 = df['high'].rolling(window=52).max()
    low_52 = df['low'].rolling(window=52).min()
    df['senkou_b'] = ((high_52 + low_52) / 2).shift(26)

    df['future_a'] = (tenkan_sen + kijun_sen) / 2
    df['future_b'] = (high_52 + low_52) / 2

    return df

# --- 5. ПОИСК СИГНАЛОВ ---
def check_coin(symbol):
    df = get_1h_candles(symbol, limit=150)
    if df is None or len(df) < 80:
        return None

    df = add_ichimoku_macd(df)
    
    curr = df.iloc[-2]
    prev = df.iloc[-3]
    price = curr['close']

    cloud_top = max(curr['senkou_a'], curr['senkou_b'])
    cloud_bottom = min(curr['senkou_a'], curr['senkou_b'])

    macd_bull_cross = (prev['macd'] <= prev['macd_signal']) and (curr['macd'] > curr['macd_signal'])
    macd_bear_cross = (prev['macd'] >= prev['macd_signal']) and (curr['macd'] < curr['macd_signal'])

    if price > cloud_top and curr['future_a'] > curr['future_b'] and macd_bull_cross:
        sl = round(price * 0.988, 4)
        tp = round(price * 1.025, 4)
        return (
            f"☁️🟢 <b>ИШИМОКУ + MACD ЛОНГ (1H)</b>\n\n"
            f"🪙 Монета: <b>#{symbol}</b>\n"
            f"💵 Вход: <code>{round(price, 4)}</code>\n"
            f"🛡️ Стоп (-1.2%): <code>{sl}</code>\n"
            f"💰 Тейк (+2.5%): <code>{tp}</code>\n\n"
            f"📊 <i>Цена пробила/удержала верх Облака Ишимоку, MACD развернулся вверх.</i>"
        )

    if price < cloud_bottom and curr['future_a'] < curr['future_b'] and macd_bear_cross:
        sl = round(price * 1.012, 4)
        tp = round(price * 0.975, 4)
        return (
            f"☁️🔴 <b>ИШИМОКУ + MACD ШОРТ (1H)</b>\n\n"
            f"🪙 Монета: <b>#{symbol}</b>\n"
            f"💵 Вход: <code>{round(price, 4)}</code>\n"
            f"🛡️ Стоп (+1.2%): <code>{sl}</code>\n"
            f"💰 Тейк (-2.5%): <code>{tp}</code>\n\n"
            f"📊 <i>Цена под Облаком Ишимоку, MACD развернулся вниз.</i>"
        )

    return None

# --- 6. ЗАПУСК ---
if __name__ == "__main__":
    print("Запуск сканера Ишимоку + MACD (1H)...")
    is_manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    
    if is_manual:
        send_telegram("☁️ <b>Бот Ишимоку + MACD (1H) запущен!</b> Проверяю 12 монет...")

    found = 0
    for symbol in SYMBOLS:
        signal_msg = check_coin(symbol)
        if signal_msg:
            send_telegram(signal_msg)
            found += 1
        time.sleep(1)

    if is_manual and found == 0:
        send_telegram("☁️ Проверка Ишимоку + MACD завершена. На закрытии текущего часа сильных трендовых сигналов нет.")
    
    print(f"Готово. Найдено сигналов: {found}")
