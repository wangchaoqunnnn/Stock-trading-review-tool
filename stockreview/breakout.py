# -*- coding: utf-8 -*-
"""突破新高策略：突破短期高点（近20日）与突破历史高点（可得历史/约250交易日）。

- 突破判定：今日最高价 > 此前窗口内最高价。
- 预筛：全A 今日上涨且成交额 ≥ 2 亿（控制 K 线核对数量）。
- 输出：涨幅、成交量(万手)、量比、成交额、突破幅度、前高等。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .analysis import breakout_hist, breakout_short
from .config import ALL_A_FS
from .market import fetch_market_context
from .utils import to_num

# 全A扫描行情字段
SCAN_FIELDS = "f2,f3,f5,f6,f8,f10,f12,f14,f15,f16,f17,f18,f62,f100"

# 短期窗口（交易日）
SHORT_WINDOW = 20
# 长历史目标窗口（交易日，实际以可得数据为准）
HIST_LIMIT = 250
# 预筛：成交额下限（亿）
MIN_AMOUNT_YI = 2.0
# K线核对并发与输出上限
CHECK_WORKERS = 24
STOCK_LIMIT = 100


def _safe(name, fn):
    try:
        return name, fn()
    except Exception as exc:
        return name, {"error": f"{type(exc).__name__}: {exc}"}


def _check_stock(row, end_date=None):
    """单只个股：抓长K线并判定短期/历史突破，命中返回结果 dict。"""
    code = row.get("f12")
    if not code:
        return None
    hist = em.fetch_long_kline(str(code), limit=HIST_LIMIT, end_date=end_date)
    if len(hist) < SHORT_WINDOW + 2:
        return None
    today = hist[-1]
    price = to_num(row.get("f2")) or today["close"]
    pct = to_num(row.get("f3"))
    base = {
        "code": str(code),
        "name": row.get("f14"),
        "pct": pct,
        "price": round(price, 2),
        "amount_yi": round(to_num(row.get("f6")) / 100000000, 2),
        "vol_wan": round(to_num(row.get("f5")) / 10000, 0),
        "vol_ratio": round(to_num(row.get("f10")), 2),
        "industry": row.get("f100"),
        "hist_days": len(hist),
    }
    out = []
    short = breakout_short(hist, SHORT_WINDOW)
    if short and short[0]:
        prev = short[1]
        out.append({**base, "kind": "short", "prev_high": round(prev, 2),
                    "break_pct": round((today["high"] / prev - 1) * 100, 2)})
    hist_break = breakout_hist(hist)
    if hist_break and hist_break[0]:
        prev = hist_break[1]
        out.append({**base, "kind": "hist", "prev_high": round(prev, 2),
                    "break_pct": round((today["high"] / prev - 1) * 100, 2)})
    return out


def fetch_breakout_scan(date=None):
    """突破新高扫描主函数。date 非空时为历史回放（K线截至该日期）。"""
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "stocks": ex.submit(_safe, "stocks", lambda: net.fetch_paged(ALL_A_FS, SCAN_FIELDS, limit=6000)),
        }
        results = {k: f.result() for k, f in futures.items()}
        context = ex.submit(fetch_market_context).result()

    errors = list(context["errors"])
    if date:
        errors.append(f"历史回放({date})：涨跌幅/量比/成交额为实时行情字段，突破判定基于该日期K线")
    stocks = results["stocks"][1] if not isinstance(results["stocks"], dict) else []
    if isinstance(results["stocks"], dict) and "error" in results["stocks"]:
        errors.append(results["stocks"]["error"])

    # 预筛：今日上涨 + 流动性（历史模式预筛用实时行情近似）
    candidates = [
        r for r in stocks
        if to_num(r.get("f3")) > 0 and to_num(r.get("f6")) >= MIN_AMOUNT_YI * 100000000
    ]
    candidates.sort(key=lambda r: -to_num(r.get("f6")))

    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as ex:
        hits = list(ex.map(lambda r: _check_stock(r, date), candidates))

    short_rows = []
    hist_rows = []
    for row in hits:
        if not row:
            continue
        for item in row:
            if item["kind"] == "short":
                short_rows.append(item)
            else:
                hist_rows.append(item)
    short_rows.sort(key=lambda x: -x["break_pct"])
    hist_rows.sort(key=lambda x: -x["break_pct"])

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "short_window": SHORT_WINDOW,
        "hist_window": HIST_LIMIT,
        "scanned": len(candidates),
        "short": {"count": len(short_rows), "stocks": short_rows[:STOCK_LIMIT]},
        "hist": {"count": len(hist_rows), "stocks": hist_rows[:STOCK_LIMIT]},
        "errors": errors,
    }
