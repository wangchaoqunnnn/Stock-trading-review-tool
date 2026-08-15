# -*- coding: utf-8 -*-
"""策略选股：20日内涨停 + 上升趋势 + 缩量回踩不破涨停 + 市场热点。"""
import json
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
CACHE = {"ts": 0.0, "data": None}
TTL = 600


def http_get_json(url, headers=None, timeout=20, tries=3):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            last = exc
            time.sleep(1.0)
    raise last


def trading_dates(n=20):
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,60,qfq"
    data = http_get_json(url, headers={"Referer": "https://gu.qq.com/"})
    node = data.get("data", {}).get("sh000001", {})
    arr = node.get("qfqday") or node.get("day") or []
    return [item[0] for item in arr][-n:]


def fetch_zt_pool(date):
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": 0,
        "pagesize": 500,
        "sort": "fbt:asc",
        "date": date,
    }
    url = "https://push2ex.eastmoney.com/getTopicZTPool?" + urllib.parse.urlencode(params)
    data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/ztb/detail"})
    return data.get("data", {}).get("pool", [])


def symbol_of(code):
    if code.startswith(("6", "5", "9")):
        return "sh" + code
    if code.startswith(("0", "3")):
        return "sz" + code
    return None


def fetch_kline(symbol, lmt=60):
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{lmt},qfq"
    data = http_get_json(url, headers={"Referer": "https://gu.qq.com/"})
    node = data.get("data", {}).get(symbol, {})
    arr = node.get("qfqday") or node.get("day") or []
    rows = []
    for item in arr:
        rows.append(
            {
                "date": item[0],
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[3]),
                "low": float(item[4]),
                "vol": float(item[5]),
            }
        )
    return rows


def limit_threshold(code):
    if code.startswith(("300", "301", "688")):
        return 19.5
    if code.startswith(("4", "8", "9")):
        return 29.5
    return 9.8


def build():
    errors = []
    dates = []
    try:
        dates = trading_dates(20)
    except Exception as exc:
        errors.append(f"交易日历: {exc!r}")
        return {"errors": errors, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "stocks": []}
    if not dates:
        errors.append("交易日历为空")
        return {"errors": errors, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "stocks": []}

    pool_by_code = {}
    for date in dates:
        d = date.replace("-", "")
        try:
            pool = fetch_zt_pool(d)
        except Exception:
            continue
        for x in pool:
            code = str(x.get("c", "")).zfill(6)
            if not code or code == "000000":
                continue
            pool_by_code.setdefault(code, {"date": date, "name": x.get("n"), "sector": x.get("hybk")})

    codes = list(pool_by_code.keys())
    klines = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_kline, symbol_of(c)): c for c in codes if symbol_of(c)}
        for fut in as_completed(futs):
            code = futs[fut]
            try:
                rows = fut.result()
                if rows:
                    klines[code] = rows
            except Exception:
                pass

    sector_daily = defaultdict(Counter)
    for code, info in pool_by_code.items():
        sector_daily[info["date"]][info.get("sector", "")] += 1

    hot = set()
    if dates:
        last_date = dates[-1]
        for sector, cnt in sector_daily[last_date].items():
            if cnt >= 2:
                hot.add(sector)
    recent5 = dates[-5:] if len(dates) >= 5 else dates
    sector_5day = Counter()
    for date in recent5:
        for sector, cnt in sector_daily[date].items():
            sector_5day[sector] += cnt
    for sector, cnt in sector_5day.items():
        if cnt >= 5:
            hot.add(sector)

    stocks = []
    for code, rows in klines.items():
        if len(rows) < 25:
            continue
        closes = [r["close"] for r in rows]
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        ma20_prev = sum(closes[-25:-5]) / 20
        cur = rows[-1]
        prev = rows[-2] if len(rows) >= 2 else None
        today_pct = (cur["close"] / prev["close"] - 1) * 100 if prev and prev["close"] else 0.0

        if not (ma5 > ma10 > ma20 and ma20 > ma20_prev and cur["close"] > ma20):
            continue

        th = limit_threshold(code)
        window = rows[-20:] if len(rows) >= 20 else rows
        limit_days = []
        for i in range(1, len(window)):
            pc = window[i - 1]["close"]
            pct = (window[i]["close"] / pc - 1) * 100 if pc else 0.0
            if pct >= th:
                limit_days.append((i, window[i]))
        if not limit_days:
            continue
        li, lr = limit_days[-1]
        if li >= len(window) - 1:
            continue

        avg5_vol = sum(r["vol"] for r in window[-5:]) / 5
        if not (lr["vol"] > 0 and cur["vol"] < lr["vol"] * 0.8 and avg5_vol < lr["vol"]):
            continue
        if not (lr["open"] > 0 and cur["close"] >= lr["open"] and cur["close"] <= lr["close"] * 1.02):
            continue

        sector = pool_by_code.get(code, {}).get("sector", "")
        if sector not in hot:
            continue

        days_after = len(window) - 1 - li
        pullback = (cur["close"] / lr["close"] - 1) * 100
        vol_ratio = cur["vol"] / lr["vol"]
        stocks.append(
            {
                "code": code,
                "name": pool_by_code.get(code, {}).get("name", ""),
                "sector": sector,
                "price": round(cur["close"], 2),
                "today_pct": round(today_pct, 2),
                "limit_date": lr["date"],
                "limit_close": round(lr["close"], 2),
                "limit_open": round(lr["open"], 2),
                "days_after": days_after,
                "pullback": round(pullback, 2),
                "vol_ratio": round(vol_ratio, 2),
                "avg5_vol_ratio": round(avg5_vol / lr["vol"], 2),
                "ma": f"{ma5:.2f}/{ma10:.2f}/{ma20:.2f}",
            }
        )

    stocks.sort(key=lambda x: (x["days_after"], x["vol_ratio"]))
    return {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "window_dates": dates,
        "universe": len(codes),
        "hot_sectors": sorted(hot),
        "stocks": stocks,
        "errors": errors,
    }


def get_strategy():
    now = time.time()
    if CACHE["data"] and now - CACHE["ts"] < TTL:
        return CACHE["data"]
    data = build()
    CACHE["ts"] = now
    CACHE["data"] = data
    return data
