import os
import time
import base64
import datetime
import requests
import pandas as pd

# --- 1. НАСТРОЙКИ ---
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = "531386055"

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", 
    "UNIUSDT", "AVAXUSDT", "SUIUSDT", "INJUSDT", 
    "AAVEUSDT", "JTOUSDT", "ENAUSDT", "TAOUSDT"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json"
}

BV_URL = base64.b64decode("aHR0cHM6Ly9kYXRhLWFwaS5iaW5hbmNlLnZpc2lvbi9hcGkvdjMva2xpbmVz").decode()
CB_BASE = base64.b64decode("aHR0cHM6Ly9hcGkuZXhjaGFuZ2UuY29pbmJhc2UuY29tL3Byb2R1Y3RzLw==").decode()
TG_API_BASE = base64.b64decode("aHR0cHM6Ly9hcGkudGVsZWdyYW0ub3JnL2JvdA==").decode()

# --- 2. ОТПРАВКА В TELEGRAM ---
def send_telegram(message):
    if not TG_TOKEN:
        print("ОШИБКА: TG_TOKEN пустой!")
        return
    token_clean = TG_TOKEN.strip()
    url = f"{TG_API_BASE}{token_clean}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
        print(f"СТАТУС ТЕЛЕГРАМ: {r.status_code} | ОТВЕТ: {r.text}")
    except Exception as e:
        print(f"СБОЙ СЕТИ: {e}")

# --- 3. ПОЛУЧЕНИЕ СВЕЧЕЙ (1h, 4h, 1d) ---
def get_candles(symbol, timeframe="1h", limit=150):
    try:
        r_bv = requests.get(BV_URL, params={"symbol": symbol, "interval": timeframe, "limit": limit}, headers=HEADERS, timeout=10)
        if r_bv.status_code == 200:
            data_bv = r_bv.json()
            if isinstance(data_bv, list) and len(data_bv) >= 8:
                df = pd.DataFrame([row[:6] for row in data_bv], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                for col in ['open', 'high', 'low', 'close']:
                    df[col] = df[col].astype(float)
                return df
    except Exception as e:
        print(f"BV error {symbol}: {e}")

    coin = symbol.replace("USDT", "")
    url_cb = f"{CB_BASE}{coin}-USD/candles"
    try:
        if timeframe in ["1h", "4h"]:
            req_limit = 300 if timeframe == "4h" else limit
            r = requests.get(url_cb, params={"granularity": 3600}, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) >= 15:
                    df = pd.DataFrame(data[:req_limit], columns=['timestamp', 'low', 'high', 'open', 'close', 'volume'])
                    df = df.iloc[::-1].reset_index(drop=True)
                    for col in ['open', 'high', 'low', 'close']:
                        df[col] = df[col].astype(float)
                    if timeframe == "1h":
                        return df
                    elif timeframe == "4h":
                        df['dt'] = pd.to_datetime(df['timestamp'], unit='s')
                        df.set_index('dt', inplace=True)
                        df_4h = df.resample('4h').agg({
                            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                        }).dropna().reset_index()
                        return df_4h
        elif timeframe == "1d":
            r = requests.get(url_cb, params={"granularity": 86400}, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) >= 8:
                    df = pd.DataFrame(data[:limit], columns=['timestamp', 'low', 'high', 'open', 'close', 'volume'])
                    df = df.iloc[::-1].reset_index(drop=True)
                    for col in ['open', 'high', 'low', 'close']:
                        df[col] = df[col].astype(float)
                    return df
    except Exception as e:
        print(f"CB error {symbol}: {e}")

    return None

# --- 4. РАСЧЕТ СУТОЧНОЙ (24H) И НЕДЕЛЬНОЙ (7D) ЛИКВИДНОСТИ ---
def get_liquidity_pools(symbol):
    df_1h = get_candles(symbol, timeframe="1h", limit=40)
    df_1d = get_candles(symbol, timeframe="1d", limit=12)

    if df_1h is None or len(df_1h) < 26 or df_1d is None or len(df_1d) < 8:
        return None

    price = df_1h.iloc[-1]['close']

    # Суточная ликвидность (за предыдущие 24 часа)
    day_window = df_1h.iloc[-26:-2]
    day_high = day_window['high'].max()
    day_low = day_window['low'].min()

    recent_2h_high = df_1h.iloc[-2:]['high'].max()
    recent_2h_low = df_1h.iloc[-2:]['low'].min()
    day_top_swept = recent_2h_high >= day_high
    day_bot_swept = recent_2h_low <= day_low

    # Недельная ликвидность (за предыдущие 7 закрытых дней)
    week_window = df_1d.iloc[-8:-1]
    week_high = week_window['high'].max()
    week_low = week_window['low'].min()

    today_high = df_1d.iloc[-1]['high']
    today_low = df_1d.iloc[-1]['low']
    week_top_swept = today_high >= week_high
    week_bot_swept = today_low <= week_low

    d_up_pct = round(((day_high - price) / price) * 100, 2)
    d_down_pct = round(((price - day_low) / price) * 100, 2)
    w_up_pct = round(((week_high - price) / price) * 100, 2)
    w_down_pct = round(((price - week_low) / price) * 100, 2)

    if day_top_swept and not day_bot_swept:
        priority = "SHORT"
        advice = f"⬆️ Суточный верх СНЯТ ({round(day_high, 4)}). Выгоднее идти ВНИЗ к суточному дну {round(day_low, 4)} (-{d_down_pct}%)."
    elif day_bot_swept and not day_top_swept:
        priority = "LONG"
        advice = f"⬇️ Суточный низ СНЯТ ({round(day_low, 4)}). Выгоднее идти ВВЕРХ к суточному пику {round(day_high, 4)} (+{d_up_pct}%)."
    elif abs(d_down_pct) < abs(d_up_pct):
        priority = "SHORT"
        advice = f"🧲 Ближе суточный НИЗ: идти <b>-{d_down_pct}%</b> до {round(day_low, 4)} (до верха +{d_up_pct}%)."
    else:
        priority = "LONG"
        advice = f"🧲 Ближе суточный ВЕРХ: идти <b>+{d_up_pct}%</b> до {round(day_high, 4)} (до низа -{d_down_pct}%)."

    return {
        "price": price,
        "day_high": day_high, "day_low": day_low,
        "d_up_pct": d_up_pct, "d_down_pct": d_down_pct,
        "day_top_swept": day_top_swept, "day_bot_swept": day_bot_swept,
        "week_high": week_high, "week_low": week_low,
        "w_up_pct": w_up_pct, "w_down_pct": w_down_pct,
        "week_top_swept": week_top_swept, "week_bot_swept": week_bot_swept,
        "priority": priority,
        "advice": advice
    }

# --- 5. ПРОВЕРКА СИГНАЛОВ ПО EMA 50/100 (1H И 4H) ---
def check_signals(symbol, liq, timeframe="1h"):
    df = get_candles(symbol, timeframe=timeframe, limit=130)
    if df is None or len(df) < 105:
        return None

    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()

    curr = df.iloc[-2]
    prev = df.iloc[-3]
    price = curr['close']

    ema_bull_cross = (prev['ema50'] <= prev['ema100']) and (curr['ema50'] > curr['ema100'])
    ema_bear_cross = (prev['ema50'] >= prev['ema100']) and (curr['ema50'] < curr['ema100'])
    tf_label = timeframe.upper()

    if ema_bull_cross and liq['priority'] == "LONG":
        tp = round(liq['day_high'], 4) if liq['d_up_pct'] >= 1.0 else round(liq['week_high'], 4)
        sl = round(min(curr['ema100'], liq['day_low']) * 0.995, 4)
        return (
            f"⚡🟢 <b>EMA 50/100 ({tf_label}) + ЛИКВИДНОСТЬ — ЛОНГ</b>\n\n"
            f"🪙 Монета: <b>#{symbol}</b>\n"
            f"💵 Вход: <code>{round(price, 4)}</code>\n"
            f"🎯 Цель (пул стопов): <code>{tp}</code>\n"
            f"🛡️ Стоп-лосс: <code>{sl}</code>\n\n"
            f"📊 <b>Анализ ликвидности:</b>\n{liq['advice']}\n"
            f"📅 Неделя (7D): Верх {round(liq['week_high'], 4)} (+{liq['w_up_pct']}%) | Низ {round(liq['week_low'], 4)} (-{liq['w_down_pct']}%)"
        )

    if ema_bear_cross and liq['priority'] == "SHORT":
        tp = round(liq['day_low'], 4) if liq['d_down_pct'] >= 1.0 else round(liq['week_low'], 4)
        sl = round(max(curr['ema100'], liq['day_high']) * 1.005, 4)
        return (
            f"⚡🔴 <b>EMA 50/100 ({tf_label}) + ЛИКВИДНОСТЬ — ШОРТ</b>\n\n"
            f"🪙 Монета: <b>#{symbol}</b>\n"
            f"💵 Вход: <code>{round(price, 4)}</code>\n"
            f"🎯 Цель (пул стопов): <code>{tp}</code>\n"
            f"🛡️ Стоп-лосс: <code>{sl}</code>\n\n"
            f"📊 <b>Анализ ликвидности:</b>\n{liq['advice']}\n"
            f"📅 Неделя (7D): Верх {round(liq['week_high'], 4)} (+{liq['w_up_pct']}%) | Низ {round(liq['week_low'], 4)} (-{liq['w_down_pct']}%)"
        )

    if liq['week_bot_swept'] and curr['ema50'] > curr['ema100'] and curr['close'] > liq['week_low']:
        return (
            f"🌊🟢 <b>СНЯТ МИНИМУМ НЕДЕЛИ + EMA ({tf_label}) — ЛОНГ</b>\n\n"
            f"🪙 Монета: <b>#{symbol}</b>\n"
            f"💵 Вход: <code>{round(price, 4)}</code>\n"
            f"🎯 Цель (суточный пик): <code>{round(liq['day_high'], 4)}</code> (+{liq['d_up_pct']}%)\n"
            f"🛡️ Стоп (за минимум недели): <code>{round(liq['week_low'] * 0.995, 4)}</code>"
        )

    if liq['week_top_swept'] and curr['ema50'] < curr['ema100'] and curr['close'] < liq['week_high']:
        return (
            f"🌊🔴 <b>СНЯТ МАКСИМУМ НЕДЕЛИ + EMA ({tf_label}) — ШОРТ</b>\n\n"
            f"🪙 Монета: <b>#{symbol}</b>\n"
            f"💵 Вход: <code>{round(price, 4)}</code>\n"
            f"🎯 Цель (суточное дно): <code>{round(liq['day_low'], 4)}</code> (-{liq['d_down_pct']}%)\n"
            f"🛡️ Стоп (за максимум недели): <code>{round(liq['week_high'] * 1.005, 4)}</code>"
        )

    return None

# --- 6. ЗАПУСК (ВРЕМЯ КАЗАХСТАН UTC+5) ---
if __name__ == "__main__":
    kz_tz = datetime.timezone(datetime.timedelta(hours=5))
    now_kz = datetime.datetime.now(kz_tz)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    time_str = now_kz.strftime("%d.%m.%Y %H:%M")
    current_hour_utc = now_utc.hour
    is_manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

    signals = []
    radar_lines = []

    for symbol in SYMBOLS:
