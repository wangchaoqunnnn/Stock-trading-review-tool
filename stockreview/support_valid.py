# -*- coding: utf-8 -*-
"""支撑位有效个股扫描（回测验证规则，胜率约78%）。

规则（scripts/backtest_support.py 回测：基线≈50%不可行，加确认后可行）：
- 支撑位：近 60 日最低价（箱体下沿/前低）。
- 信号日：盘中触及支撑（≤S×1.02）+ 收盘站稳（≥S×0.98）+ 缩量（≤前5日均量×0.9）。
- 确认日（次日）：放量阳线（收盘>开盘 且 量≥前5日均量）。
- 最近 3 个交易日内完成"信号日+确认日"的个股即为支撑位有效。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .analysis import is_confirm_day, is_pullback_signal, support_level
from .config import ALL_A_FS
from .market import fetch_market_context
from .utils import to_num

SCAN_FIELDS = "f2,f3,f5,f6,f8,f10,f12,f14,f17,f18,f22,f62,f100"
MIN_AMOUNT_YI = 2.0
CHECK_WORKERS = 24
STOCK_LIMIT = 100
MAX_LAG = 3


def _safe(name, fn):
    try:
        return name, fn()
    except Exception as exc:
        return name, {"error": f"{type(exc).__name__}: {exc}"}


def _check_stock(row, end_date=None):
    """单只个股：最近 3 日内完成缩量回踩支撑 + 次日放量阳线确认。"""
    code = row.get("f12")
    if not code:
        return None
    hist = em.fetch_long_kline(str(code), limit=250, end_date=end_date)
    if len(hist) < 70:
        return None
    hit = None
    for lag in range(1, MAX_LAG + 1):
        sig = len(hist) - 1 - lag
        cfm = sig + 1
        if sig < 1 or cfm >= len(hist):
            continue
        ok_s, S, shrink_r = is_pullback_signal(hist, sig)
        if not ok_s:
            continue
        ok_c, cfm_r = is_confirm_day(hist, cfm)
        if ok_c:
            hit = (sig, cfm, S, shrink_r, cfm_r)
            break
    if not hit:
        return None
    sig, cfm, S, shrink_r, cfm_r = hit
    cfm_row = hist[cfm]
    return {
        "code": str(code),
        "name": row.get("f14"),
        "support": round(S, 2),
        "signal_date": hist[sig]["date"],
        "confirm_date": hist[cfm]["date"],
        "price": round(to_num(row.get("f2")) or cfm_row["close"], 2),
        "pct": round(to_num(row.get("f3")), 2),
        "shrink_ratio": round(shrink_r, 2),
        "confirm_vol": round(cfm_r, 2),
        "vol_ratio": round(to_num(row.get("f10")), 2),
        "amount_yi": round(to_num(row.get("f6")) / 100000000, 2),
        "turnover": round(to_num(row.get("f8")), 2),
        "industry": row.get("f100"),
        "days_ago": len(hist) - 1 - cfm,
    }


def fetch_support_valid_scan(date=None):
    """支撑位有效扫描主函数。date 非空时为历史回放（K线截至该日期）。"""
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "stocks": ex.submit(_safe, "stocks", lambda: net.fetch_paged(ALL_A_FS, SCAN_FIELDS, limit=6000)),
        }
        results = {k: f.result() for k, f in futures.items()}
        context = ex.submit(fetch_market_context).result()

    errors = list(context["errors"])
    if date:
        errors.append(f"历史回放({date})：涨跌幅/量比/成交额为实时行情字段，支撑判定基于该日期K线")
    stocks = results["stocks"][1] if not isinstance(results["stocks"], dict) else []
    if isinstance(results["stocks"], dict) and "error" in results["stocks"]:
        errors.append(results["stocks"]["error"])

    seen = set()
    unique = []
    for r in stocks:
        c = str(r.get("f12") or "")
        if c in seen:
            continue
        seen.add(c)
        unique.append(r)
    stocks = unique

    candidates = [r for r in stocks if to_num(r.get("f6")) >= MIN_AMOUNT_YI * 100000000]
    candidates.sort(key=lambda r: -to_num(r.get("f6")))

    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as ex:
        hits = [x for x in ex.map(lambda r: _check_stock(r, date), candidates) if x]

    hits.sort(key=lambda x: (x["days_ago"], -x["amount_yi"]))
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "rule": "近60日低点支撑 + 缩量回踩 + 次日放量阳线确认（回测3日胜率78%）",
        "scanned": len(candidates),
        "count": len(hits),
        "stocks": hits[:STOCK_LIMIT],
        "errors": errors,
    }
