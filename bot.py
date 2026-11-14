import os, time, datetime, requests
import pandas as pd

TG_TOKEN = "".join((os.environ.get("TG_TOKEN") or "").split())
TG_CHAT_ID = "".join((os.environ.get("TG_CHAT_ID") or "531386055").split())

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT",
    "UNIUSDT", "AVAXUSDT", "SUIUSDT", "INJUSDT",
    "AAVEUSDT", "JTOUSDT", "ENAUSDT", "TAOUSDT"
]

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
BV_URL = "https:" + "//data-api.binance.vision" + "/api/v3/klines"
CB_BASE = "https:" + "//://coinbase.com" + "/products/"
TG_API = "https:" + "//api.telegram.org" + "/bot"

def send_telegram(message):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("ОШИБКА: не заданы секреты TG_TOKEN / TG_CHAT_ID")
        return
    try:
        r = requests.post(TG_API + TG_TOKEN + "/sendMessage", json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
        print(f"TG {r.status_code}: {r.text[:80]}")
    except Exception as e:
        print(f"СБОЙ СЕТИ TG: {e}")

def get_candles(symbol, timeframe="1h", limit=150):
    try:
        r_bv = requests.get(BV_URL, params={"symbol": symbol, "interval": timeframe, "limit": limit}, headers=HEADERS, timeout=10)
        if r_bv.status_code == 200 and isinstance(r_bv.json(), list) and len(r_bv.json()) >= 15:
            df = pd.DataFrame([row[:6] for row in r_bv.json()], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in ['open', 'high', 'low', 'close']: df[col] = df[col].astype(float)
            return df
    except Exception: pass

    coin = symbol.replace("USDT", "")
    url_cb = f"{CB_BASE}{coin}-USD/candles"
    try:
        if timeframe in ["1h", "4h"]:
            req_limit = 300 if timeframe == "4h" else limit
            r = requests.get(url_cb, params={"granularity": 3600}, headers=HEADERS, timeout=10)
            if r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 20:
                df = pd.DataFrame(r.json()[:req_limit], columns=['timestamp', 'low', 'high', 'open', 'close', 'volume']).iloc[::-1].reset_index(drop=True)
                for col in ['open', 'high', 'low', 'close']: df[col] = df[col].astype(float)
                if timeframe == "1h": return df
                df['dt'] = pd.to_datetime(df['timestamp'], unit='s')
                return df.set_index('dt').resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna().reset_index()
        elif timeframe == "1d":
            r = requests.get(url_cb, params={"granularity": 86400}, headers=HEADERS, timeout=10)
            if r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 8:
                df = pd.DataFrame(r.json()[:limit], columns=['timestamp', 'low', 'high', 'open', 'close', 'volume']).iloc[::-1].reset_index(drop=True)
                for col in ['open', 'high', 'low', 'close']: df[col] = df[col].astype(float)
                return df
    except Exception: pass
    return None

def add_indicators(df):
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema100'] = df['close'].ewm(span=100, adjust=False).mean()
    delta = df['close'].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    return df

def get_btc_trend():
    df1 = get_candles("BTCUSDT", "1h", 120)
    if df1 is None or len(df1) < 105: return "NEUTRAL", "⚪ BTC: нет данных"
    df1 = add_indicators(df1)
    c = df1.iloc[-1]
    if c['close'] > c['ema100'] and c['ema50'] > c['ema100']: return "BULL", f"🟢 BTC (${round(c['close'], 1)}): Бычий"
    if c['close'] < c['ema100'] and c['ema50'] < c['ema100']: return "BEAR", f"🔴 BTC (${round(c['close'], 1)}): Медвежий"
    return "NEUTRAL", f"🟡 BTC (${round(c['close'], 1)}): Флэт"

def analyze_coin(symbol, btc_code, btc_txt):
    df_1h = get_candles(symbol, "1h", 130)
    df_1d = get_candles(symbol, "1d", 12)
    if df_1h is None or len(df_1h) < 105 or df_1d is None or len(df_1d) < 8: return [], None

    df_1h = add_indicators(df_1h)
    curr, prev = df_1h.iloc[-2], df_1h.iloc[-3]
    live_p = df_1h.iloc[-1]['close']

    day_high, day_low = df_1h.iloc[-26:-2]['high'].max(), df_1h.iloc[-26:-2]['low'].min()
    week_high, week_low = df_1d.iloc[-8:-1]['high'].max(), df_1d.iloc[-8:-1]['low'].min()

    d_up_pct = round(((day_high - live_p) / live_p) * 100, 2)
    d_dn_pct = round(((live_p - day_low) / live_p) * 100, 2)
    min_dist = min(abs(d_up_pct), abs(d_dn_pct))
    near_side = f"до верха {d_up_pct}%" if abs(d_up_pct) < abs(d_dn_pct) else f"до низа {d_dn_pct}%"
    radar_item = (min_dist, f"• <b>{symbol.replace('USDT', '')}</b> (${round(live_p, 4)}): {near_side} | RSI {round(curr['rsi'], 1)}")

    found = []
    # 1. РАЗВОРОТНЫЕ СИГНАЛЫ (Снятие ликвидности 24H / 7D + возврат + RSI)
    swept_24h_top = (curr['high'] >= day_high) and (curr['close'] < day_high) and (curr['rsi'] > 66)
    swept_7d_top = (df_1d.iloc[-1]['high'] >= week_high) and (curr['close'] < week_high) and (curr['rsi'] > 65)
    if (swept_24h_top or swept_7d_top) and (symbol == "BTCUSDT" or btc_code != "BULL"):
        lvl = round(week_high if swept_7d_top else day_high, 4)
        tag = "7D НЕДЕЛИ" if swept_7d_top else "24H СУТОК"
        sl = round(max(curr['high'], lvl) * 1.005, 4)
        found.append(f"🌊🔴 <b>СНЯТ МАКСИМУМ {tag} — ШОРТ</b>\n🪙 <b>#{symbol}</b> | RSI: {round(curr['rsi'], 1)}\n💵 Вход: <code>{round(live_p, 4)}</code>\n🎯 Цель: <code>{round(day_low, 4)}</code>\n🛡️ Стоп: <code>{sl}</code>\n🚂 {btc_txt}")

    swept_24h_bot = (curr['low'] <= day_low) and (curr['close'] > day_low) and (curr['rsi'] < 34)
    swept_7d_bot = (df_1d.iloc[-1]['low'] <= week_low) and (curr['close'] > week_low) and (curr['rsi'] < 35)
    if (swept_24h_bot or swept_7d_bot) and (symbol == "BTCUSDT" or btc_code != "BEAR"):
        lvl = round(week_low if swept_7d_bot else day_low, 4)
        tag = "7D НЕДЕЛИ" if swept_7d_bot else "24H СУТОК"
        sl = round(min(curr['low'], lvl) * 0.995, 4)
        found.append(f"🌊🟢 <b>СНЯТ МИНИМУМ {tag} — ЛОНГ</b>\n🪙 <b>#{symbol}</b> | RSI: {round(curr['rsi'], 1)}\n💵 Вход: <code>{round(live_p, 4)}</code>\n🎯 Цель: <code>{round(day_high, 4)}</code>\n🛡️ Стоп: <code>{sl}</code>\n🚂 {btc_txt}")

    # 2. ТРЕНДОВЫЕ СИГНАЛЫ (Пересечение EMA 50/100 на 1H и 4H)
    for tf in ("1h", "4h"):
        df_tf = df_1h if tf == "1h" else get_candles(symbol, "4h", 130)
        if df_tf is None or len(df_tf) < 105: continue
        if tf == "4h": df_tf = add_indicators(df_tf)
        c, p = df_tf.iloc[-2], df_tf.iloc[-3]
        if (p['ema50'] <= p['ema100']) and (c['ema50'] > c['ema100']) and (symbol == "BTCUSDT" or btc_code != "BEAR"):
            tp = round(day_high, 4) if d_up_pct >= 1.2 else round(week_high, 4)
            sl = round(min(c['ema100'], day_low) * 0.995, 4)
            found.append(f"⚡🟢 <b>ТРЕНД EMA 50/100 ({tf.upper()}) — ЛОНГ</b>\n🪙 <b>#{symbol}</b>\n💵 Вход: <code>{round(live_p, 4)}</code>\n🎯 Цель: <code>{tp}</code>\n🛡️ Стоп: <code>{sl}</code>\n🚂 {btc_txt}")
        elif (p['ema50'] >= p['ema100']) and (c['ema50'] < c['ema100']) and (symbol == "BTCUSDT" or btc_code != "BULL"):
            tp = round(day_low, 4) if d_dn_pct >= 1.2 else round(week_low, 4)
            sl = round(max(c['ema100'], day_high) * 1.005, 4)
            found.append(f"⚡🔴 <b>ТРЕНД EMA 50/100 ({tf.upper()}) — ШОРТ</b>\n🪙 <b>#{symbol}</b>\n💵 Вход: <code>{round(live_p, 4)}</code>\n🎯 Цель: <code>{tp}</code>\n🛡️ Стоп: <code>{sl}</code>\n🚂 {btc_txt}")

    return found, radar_item

if __name__ == "__main__":
    btc_code, btc_txt = get_btc_trend()
    all_signals, radar = [], []

    for sym in SYMBOLS:
        sigs, r_item = analyze_coin(sym, btc_code, btc_txt)
        all_signals.extend(sigs)
        if r_item: radar.append(r_item)
        time.sleep(0.5)

    for s in all_signals:
        send_telegram(s)
        time.sleep(0.5)

    # Радар в 09:00 и 21:00 по Алматы (04:00 и 16:00 UTC) или при ручном запуске
    utc_hour = datetime.datetime.now(datetime.timezone.utc).hour
    is_manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if is_manual or utc_hour in (4, 16):
        radar.sort(key=lambda x: x[0])
        top_radar = "\n".join([x[1] for x in radar[:6]])
        send_telegram(f"📡 <b>РАДАР ЛИКВИДНОСТИ (24H / 7D)</b>\n{btc_txt}\n\nБлиже всего к снятию уровней:\n{top_radar}")
