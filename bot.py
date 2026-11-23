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
        b_int = "1h" if interval == "60" else "4h"
        resp = requests.get(
            BINANCE_URL,
            params={"symbol": symbol, "interval": b_int, "limit": limit},
            timeout=10
        ).json()
        if isinstance(resp, list) and len(resp) > 205:
            candles = []
            for item in resp[:-1]:
                it = iter(item)
                candles.append({
                    "time": int(next(it)),
                    "open": float(next(it)),
                    "high": float(next(it)),
                    "low": float(next(it)),
                    "close": float(next(it)),
                    "volume": float(next(it))
                })
            return candles
    except Exception as e:
        print(f"Binance err {symbol}: {e}", flush=True)

    return []


def calc_ema(prices: list, period: int) -> float:
    if len(prices) < period:
        return sum(prices) / len(prices)
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema


def calc_atr(candles: list, period: int = 14) -> float:
    trs = []
    for i in range(1, len(candles)):
        h = candles[i].get("high")
        l = candles[i].get("low")
        pc = candles[i - 1].get("close")
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return 0.0
    atr = sum(trs[:period]) / min(len(trs), period)
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr
def analyze_timeframe(symbol: str, interval: str):
    candles = get_candles(symbol, interval=interval, limit=250)
    if len(candles) < 205:
        return None, None

    closes = [c.get("close") for c in candles]
    ema50 = calc_ema(closes, 50)
    ema200 = calc_ema(closes, 200)
    atr = calc_atr(candles, 14)

    ema50_prev = calc_ema(closes[:-1], 50)
    ema200_prev = calc_ema(closes[:-1], 200)

    prev = candles[-2]
    last = candles[-1]
    close_p = last.get("close")

    avg_vol = sum(c.get("volume") for c in candles[-11:-1]) / 10
    vol_ratio = round(last.get("volume") / avg_vol, 2) if avg_vol > 0 else 0
    high_vol = vol_ratio >= VOLUME_MULTIPLIER

    body = abs(close_p - last.get("open"))
    total_range = last.get("high") - last.get("low")
    if total_range == 0:
        return None, None

    upper_wick = last.get("high") - max(last.get("open"), close_p)
    lower_wick = min(last.get("open"), close_p) - last.get("low")
    prev_body = abs(prev.get("close") - prev.get("open"))
    change_pct = round(((close_p - last.get("open")) / last.get("open")) * 100, 2)

    events = []
    direction = None
    ref_ema = ema50

    if prev.get("close") <= ema200_prev and close_p > ema200:
        events.append("🔥 <b>ПРОБОЙ EMA 200 снизу вверх!</b>")
        direction, ref_ema = "LONG", ema200
    elif prev.get("close") >= ema200_prev and close_p < ema200:
        events.append("❄️ <b>ПРОБОЙ EMA 200 сверху вниз!</b>")
        direction, ref_ema = "SHORT", ema200

    if prev.get("close") <= ema50_prev and close_p > ema50:
        events.append("🚀 <b>Пробой EMA 50 снизу вверх</b>")
        if not direction:
            direction, ref_ema = "LONG", ema50
    elif prev.get("close") >= ema50_prev and close_p < ema50:
        events.append("🔻 <b>Пробой EMA 50 сверху вниз</b>")
        if not direction:
            direction, ref_ema = "SHORT", ema50

    if not events and high_vol:
        if last.get("low") <= ema50 <= last.get("high"):
            events.append("🎯 <b>Реакция на EMA 50 (объём)</b>")
            direction = "LONG" if close_p >= ema50 else "SHORT"
            ref_ema = ema50
        elif last.get("low") <= ema200 <= last.get("high"):
            events.append("🎯 <b>Реакция на EMA 200 (объём)</b>")
            direction = "LONG" if close_p >= ema200 else "SHORT"
            ref_ema = ema200

    if body <= total_range * 0.30 and high_vol:
        if lower_wick >= body * 2.2 and upper_wick <= total_range * 0.25 and close_p > ema200:
            events.append("🟢 <b>Бычий Пин-бар по тренду</b>")
            direction, ref_ema = "LONG", close_p
        elif upper_wick >= body * 2.2 and lower_wick <= total_range * 0.25 and close_p < ema200:
            events.append("🔴 <b>Медвежий Пин-бар по тренду</b>")
            direction, ref_ema = "SHORT", close_p

    if body > prev_body and high_vol:
        if (
            prev.get("close") < prev.get("open")
            and close_p > last.get("open")
            and close_p >= prev.get("open")
            and close_p > ema200
        ):
            events.append("🟢 <b>Бычье поглощение по тренду</b>")
            direction, ref_ema = "LONG", close_p
        elif (
            prev.get("close") > prev.get("open")
            and close_p < last.get("open")
            and close_p <= prev.get("open")
            and close_p < ema200
        ):
            events.append("🔴 <b>Медвежье поглощение по тренду</b>")
            direction, ref_ema = "SHORT", close_p

    if not events:
        pos = "выше EMA50" if close_p > ema50 else "ниже EMA50"
        short_info = f"{symbol.replace('USDT', '')} ({pos}, {change_pct}%)"
        return None, short_info

    # Расчёт тактического плана (ретест EMA + стоп/тейки по ATR)
    plan_txt = ""
    if direction and atr > 0:
        if direction == "LONG":
            entry_zone = (ref_ema + close_p) / 2 if close_p > ref_ema else close_p
            sl = entry_zone - atr * 1.5
            risk = max(entry_zone - sl, atr)
            tp1 = entry_zone + risk * 1.5
            tp2 = entry_zone + risk * 3.0
            plan_txt = (
                f"\n💡 <b>План LONG:</b> ретест <code>{fmt_price(entry_zone)}</code> | "
                f"SL <code>{fmt_price(sl)}</code> | TP1 <code>{fmt_price(tp1)}</code> | TP2 <code>{fmt_price(tp2)}</code>"
            )
        else:
            entry_zone = (ref_ema + close_p) / 2 if close_p < ref_ema else close_p
            sl = entry_zone + atr * 1.5
            risk = max(sl - entry_zone, atr)
            tp1 = entry_zone - risk * 1.5
            tp2 = entry_zone - risk * 3.0
            plan_txt = (
                f"\n💡 <b>План SHORT:</b> ретест <code>{fmt_price(entry_zone)}</code> | "
                f"SL <code>{fmt_price(sl)}</code> | TP1 <code>{fmt_price(tp1)}</code> | TP2 <code>{fmt_price(tp2)}</code>"
            )

    card = (
        f"🚨 <b>{symbol}.P</b> | Цена: <code>{fmt_price(close_p)}</code> ({change_pct}%)\n"
        + "\n".join(events)
        + f"\n📏 EMA50: <code>{fmt_price(ema50)}</code> | EMA200: <code>{fmt_price(ema200)}</code> | Объём: <b>{vol_ratio}x</b>"
        + plan_txt
    )
    return card, None


def run_hourly_cycle():
    wait_for_hour_close()
    now_alm = datetime.now(ALMATY_TZ)
    time_str = now_alm.strftime("%d.%m %H:%M")

    is_manual = (os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch")
    is_4h_close = (now_alm.hour % 4 == 1) or is_manual

    alerts_1h = []
    for sym in SYMBOLS:
        try:
            card, _ = analyze_timeframe(sym, interval="60")
            if card:
                alerts_1h.append(card)
        except Exception as e:
            print(f"Ошибка 1H {sym}: {e}", flush=True)

    if alerts_1h:
        msg_1h = f"⚡️ <b>Сигналы 1H (Алматы {time_str})</b>\n\n" + "\n\n".join(alerts_1h)
        send_telegram(msg_1h)

    if is_4h_close:
        active_4h = []
        calm_4h = []
        for sym in SYMBOLS:
            try:
                card, short_info = analyze_timeframe(sym, interval="240")
                if card:
                    active_4h.append(card)
                elif short_info:
                    calm_4h.append(short_info)
            except Exception as e:
                print(f"Ошибка 4H {sym}: {e}", flush=True)

        parts = [f"🕓 <b>Главный отчёт 4H (Алматы {time_str})</b>"]
        if active_4h:
            parts.append("\n\n".join(active_4h))
        if calm_4h:
            parts.append("💤 <b>Без пробоев:</b> " + ", ".join(calm_4h))

        send_telegram("\n\n".join(parts))


if __name__ == "__main__":
    run_hourly_cycle()
