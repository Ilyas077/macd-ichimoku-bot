import os
import time
import base64
import requests
from datetime import datetime, timezone, timedelta

# ================= НАСТРОЙКИ =================
TELEGRAM_TOKEN = "".join((os.environ.get("TG_TOKEN") or "").split())
CHAT_ID = "".join((os.environ.get("TG_CHAT_ID") or "").split())

SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "LTCUSDT", "DASHUSDT", "AVAXUSDT", "UNIUSDT", "AAVEUSDT",
    "SUIUSDT", "TAOUSDT"
)
VOLUME_MULTIPLIER = 1.25
ALMATY_TZ = timezone(timedelta(hours=5))
# =============================================

TG_API = base64.b64decode("aHR0cHM6Ly9hcGkudGVsZWdyYW0ub3JnL2JvdA==").decode()
BYBIT_URL = base64.b64decode("aHR0cHM6Ly9hcGkuYnliaXQuY29tL3Y1L21hcmtldC9rbGluZQ==").decode()
BINANCE_URL = base64.b64decode("aHR0cHM6Ly9kYXRhLWFwaS5iaW5hbmNlLnZpc2lvbi9hcGkvdjMva2xpbmVz").decode()


def wait_for_hour_close():
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return
    now = time.time()
    rem = 3600 - (now % 3600)
    if 0 < rem <= 150:
        print(f"Ждём закрытия часовой свечи: {round(rem, 1)} сек...", flush=True)
        time.sleep(rem + 3.0)


def fmt_price(val: float) -> str:
    if val >= 100:
        return f"{val:.2f}"
    elif val >= 1:
        return f"{val:.4f}"
    return f"{val:.5f}"


def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Ошибка: не заданы TG_TOKEN или TG_CHAT_ID", flush=True)
        return
    url = f"{TG_API}{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"TG {r.status_code}: {r.text[:80]}", flush=True)
    except Exception as e:
        print(f"Ошибка Telegram: {e}", flush=True)


def get_candles(symbol: str, interval: str, limit: int = 250):
    try:
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        resp = requests.get(BYBIT_URL, params=params, timeout=10).json()
        raw_list = resp.get("result", {}).get("list", [])
        if len(raw_list) > 205:
            candles = []
            for item in reversed(raw_list[1:]):
                candles.append({
                    "time": int(item),
                    "open": float(item),
                    "high": float(item),
                    "low": float(item),
                    "close": float(item),
                    "volume": float(item)
                })
            return candles
    except Exception as e:
        print(f"Bybit err {symbol}: {e}", flush=True)

    try:
        b_int = "1h" if interval == "60" else "4h"
        resp = requests.get(
            BINANCE_URL,
            params={"symbol": symbol, "interval": b_int, "limit": limit},
            timeout=10
        ).json()
        if isinstance(resp, list) and len(resp) > 205:
            candles = []
            for item in resp[:-1]:
                candles.append({
                    "time": int(item),
                    "open": float(item),
                    "high": float(item),
                    "low": float(item),
                    "close": float(item),
                    "volume": float(item)
                })
            return candles
    except Exception as e:
        print(f"Binance backup err {symbol}: {e}", flush=True)

    return []


def calc_ema(prices: list, period: int) -> float:
    if len(prices) < period:
        return sum(prices) / len(prices)
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema
def analyze_timeframe(symbol: str, interval: str, force_report: bool = False):
    candles = get_candles(symbol, interval=interval, limit=250)
    if len(candles) < 205:
        return None

    closes = [c.get("close") for c in candles]
    ema50 = calc_ema(closes, 50)
    ema200 = calc_ema(closes, 200)

    ema50_prev = calc_ema(closes[:-1], 50)
    ema200_prev = calc_ema(closes[:-1], 200)

    prev = candles[-2]
    last = candles[-1]

    avg_vol = sum(c.get("volume") for c in candles[-11:-1]) / 10
    vol_ratio = round(last.get("volume") / avg_vol, 2) if avg_vol > 0 else 0
    high_vol = vol_ratio >= VOLUME_MULTIPLIER

    body = abs(last.get("close") - last.get("open"))
    total_range = last.get("high") - last.get("low")
    if total_range == 0:
        return None

    upper_wick = last.get("high") - max(last.get("open"), last.get("close"))
    lower_wick = min(last.get("open"), last.get("close")) - last.get("low")
    prev_body = abs(prev.get("close") - prev.get("open"))
    change_pct = round(((last.get("close") - last.get("open")) / last.get("open")) * 100, 2)

    events = []

    if prev.get("close") <= ema200_prev and last.get("close") > ema200:
        events.append("🔥 <b>ПРОБОЙ EMA 200 снизу вверх!</b>")
    elif prev.get("close") >= ema200_prev and last.get("close") < ema200:
        events.append("❄️ <b>ПРОБОЙ EMA 200 сверху вниз!</b>")

    if prev.get("close") <= ema50_prev and last.get("close") > ema50:
        events.append("🚀 <b>Пробой EMA 50 снизу вверх</b> (выход из коррекции)")
    elif prev.get("close") >= ema50_prev and last.get("close") < ema50:
        events.append("🔻 <b>Пробой EMA 50 сверху вниз</b>")

    if not events and high_vol:
        if last.get("low") <= ema50 <= last.get("high"):
            events.append("🎯 <b>Реакция на EMA 50 (объём)</b>")
        if last.get("low") <= ema200 <= last.get("high"):
            events.append("🎯 <b>Реакция на EMA 200 (объём)</b>")

    if body <= total_range * 0.30 and high_vol:
        if lower_wick >= body * 2.2 and upper_wick <= total_range * 0.25 and last.get("close") > ema200:
            events.append("🟢 <b>Бычий Пин-бар (Молот) по тренду</b>")
        elif upper_wick >= body * 2.2 and lower_wick <= total_range * 0.25 and last.get("close") < ema200:
            events.append("🔴 <b>Медвежий Пин-бар (Падающая звезда) по тренду</b>")

    if body > prev_body and high_vol:
        if (
            prev.get("close") < prev.get("open")
            and last.get("close") > last.get("open")
            and last.get("close") >= prev.get("open")
            and last.get("close") > ema200
        ):
            events.append("🟢 <b>Бычье поглощение по тренду</b>")
        elif (
            prev.get("close") > prev.get("open")
            and last.get("close") < last.get("open")
            and last.get("close") <= prev.get("open")
            and last.get("close") < ema200
        ):
            events.append("🔴 <b>Медвежье поглощение по тренду</b>")

    if not force_report and not events:
        return None

    dist_ema50 = round(((ema50 - last.get("close")) / last.get("close")) * 100, 2)
    sign = "+" if dist_ema50 > 0 else ""

    status_icon = "🚨" if events else "⚪️"
    events_text = "\n" + "\n".join(events) if events else "\n💤 Спокойная свеча без пробоев и паттернов"

    card = (
        f"{status_icon} <b>{symbol}.P</b> | Закрытие: <code>{fmt_price(last.get('close'))}</code> ({change_pct}%)"
        f"{events_text}\n"
        f"📏 EMA50: <code>{fmt_price(ema50)}</code> ({sign}{dist_ema50}%) | EMA200: <code>{fmt_price(ema200)}</code> | Объём: <b>{vol_ratio}x</b>"
    )
    return card


def run_hourly_cycle():
    wait_for_hour_close()
    now_alm = datetime.now(ALMATY_TZ)
    time_str = now_alm.strftime("%d.%m %H:%M")

    is_manual = (os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch")
    is_4h_close = (now_alm.hour % 4 == 1) or is_manual

    alerts_1h = []
    for sym in SYMBOLS:
        try:
            res = analyze_timeframe(sym, interval="60", force_report=False)
            if res:
                alerts_1h.append(res)
        except Exception as e:
            print(f"Ошибка 1H {sym}: {e}", flush=True)

    if alerts_1h:
        msg_1h = f"⚡️ <b>Ранний сигнал 1H (Алматы {time_str})</b>\n\n" + "\n\n".join(alerts_1h)
        send_telegram(msg_1h)

    if is_4h_close:
        reports_4h = []
        for sym in SYMBOLS:
            try:
                res = analyze_timeframe(sym, interval="240", force_report=True)
                if res:
                    reports_4h.append(res)
            except Exception as e:
                print(f"Ошибка 4H {sym}: {e}", flush=True)

        if reports_4h:
            msg_4h = f"🕓 <b>Главный отчёт 4H (Алматы {time_str})</b>\n\n" + "\n\n".join(reports_4h)
            send_telegram(msg_4h)


if __name__ == "__main__":
    run_hourly_cycle()
