# -*- coding: utf-8 -*-
"""回踩支撑策略：上升趋势中回踩均线的股票。

- ① 上升趋势 + 回踩 5 日均线：盘中最低触及 MA5 附近，收盘未明显跌破。
- ② 上升趋势 + 回踩 10 日均线：盘中最低触及 MA10 附近，收盘未明显跌破。
- 上升趋势口径：收盘站上 MA20 且 MA20 走高（复用 is_uptrend）。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .analysis import is_uptrend, ma_of, pullback_to_ma
from .config import ALL_A_FS
from .market import fetch_market_context
from .utils import to_num

# 全A扫描行情字段
SCAN_FIELDS = "f2,f3,f5,f6,f8,f10,f12,f14,f17,f18,f22,f62,f100"

# 预筛：回踩日多为小幅波动，排除暴涨/大跌；流动性下限
MIN_AMOUNT_YI = 2.0
PCT_MIN = -6.0
PCT_MAX = 5.0
# K线核对并发与输出上限
CHECK_WORKERS = 24
STOCK_LIMIT = 120


def _safe(name, fn):
    try:
        return name, fn()
    except Exception as exc:
        return name, {"error": f"{type(exc).__name__}: {exc}"}


def _check_stock(row, end_date=None):
    """单只个股：判定上升趋势中回踩 5/10 日均线，命中返回结果列表。"""
    code = row.get("f12")
    if not code:
        return None
    hist = em.fetch_kline_hist(str(code), end_date=end_date)
    if len(hist) < 25 or not is_uptrend(hist):
        return None
    base = {
        "code": str(code),
        "name": row.get("f14"),
        "pct": round(to_num(row.get("f3")), 2),
        "price": round(to_num(row.get("f2")), 2),
        "ma5": round(ma_of(hist, 5), 2),
        "ma10": round(ma_of(hist, 10), 2),
        "ma20": round(ma_of(hist, 20), 2),
        "vol_ratio": round(to_num(row.get("f10")), 2),
        "amount_yi": round(to_num(row.get("f6")) / 100000000, 2),
        "turnover": round(to_num(row.get("f8")), 2),
        "industry": row.get("f100"),
    }
    today = hist[-1]
    out = []
    for n in (5, 10):
        ok, ma = pullback_to_ma(hist, n)
        if ok:
            out.append({
                **base,
                "kind": f"ma{n}",
                "ma": round(ma, 2),
                "touch_pct": round((today["low"] / ma - 1) * 100, 2),
                "close_pct": round((today["close"] / ma - 1) * 100, 2),
            })
    return out


def fetch_pullback_ma_scan(date=None):
    """回踩支撑扫描主函数。date 非空时为历史回放（K线截至该日期）。"""
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "stocks": ex.submit(_safe, "stocks", lambda: net.fetch_paged(ALL_A_FS, SCAN_FIELDS, limit=6000)),
        }
        results = {k: f.result() for k, f in futures.items()}
        context = ex.submit(fetch_market_context).result()

    errors = list(context["errors"])
    if date:
        errors.append(f"历史回放({date})：涨跌幅/量比/成交额为实时行情字段，回踩判定基于该日期K线")
    stocks = results["stocks"][1] if not isinstance(results["stocks"], dict) else []
    if isinstance(results["stocks"], dict) and "error" in results["stocks"]:
        errors.append(results["stocks"]["error"])

    # 按代码去重（clist 分页偶发重复行）
    seen = set()
    unique = []
    for r in stocks:
        c = str(r.get("f12") or "")
        if c in seen:
            continue
        seen.add(c)
        unique.append(r)
    stocks = unique

    candidates = [
        r for r in stocks
        if PCT_MIN <= to_num(r.get("f3")) <= PCT_MAX
        and to_num(r.get("f6")) >= MIN_AMOUNT_YI * 100000000
    ]
    candidates.sort(key=lambda r: -to_num(r.get("f6")))

    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as ex:
        hits = list(ex.map(lambda r: _check_stock(r, date), candidates))

    ma5_rows = []
    ma10_rows = []
    for row in hits:
        if not row:
            continue
        for item in row:
            if item["kind"] == "ma5":
                ma5_rows.append(item)
            else:
                ma10_rows.append(item)
    ma5_rows.sort(key=lambda x: -x["amount_yi"])
    ma10_rows.sort(key=lambda x: -x["amount_yi"])

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "scanned": len(candidates),
        "ma5": {"count": len(ma5_rows), "stocks": ma5_rows[:STOCK_LIMIT]},
        "ma10": {"count": len(ma10_rows), "stocks": ma10_rows[:STOCK_LIMIT]},
        "errors": errors,
    }
