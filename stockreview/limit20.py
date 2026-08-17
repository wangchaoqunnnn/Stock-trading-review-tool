# -*- coding: utf-8 -*-
"""20日涨停形态策略：最近20个交易日内封住涨停（东财涨停池口径），
且当前处于横盘震荡或上升趋势的个股。

- 封住涨停：以东方财富历史涨停池为准（封板到收盘），而非仅盘中触及。
- 上升趋势：收盘站上 MA20 且 MA20 走高。
- 横盘震荡：近10日振幅收敛、价格贴近走平的 MA20。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from . import em, net
from .analysis import STATE_LABELS, classify_state, is_sideways, is_uptrend, pct_5d
from .config import ALL_A_FS
from .market import fetch_market_context
from .utils import to_num

# 统计窗口：最近 N 个交易日（含当日）
WINDOW_DAYS = 20
# 日历日回溯上限（约覆盖 N 个交易日）
MAX_CALENDAR_DAYS = 45
# K线核对并发
CHECK_WORKERS = 24
# 输出上限（每个状态列表）
STOCK_LIMIT = 100

SCAN_FIELDS = "f2,f3,f6,f8,f10,f12,f14,f17,f18,f22,f62,f184,f100"


def _safe(name, fn):
    try:
        return name, fn()
    except Exception as exc:
        return name, {"error": f"{type(exc).__name__}: {exc}"}


def collect_limit_pools(days=WINDOW_DAYS, max_calendar=MAX_CALENDAR_DAYS):
    """抓取最近 days 个交易日的历史涨停池，返回 (交易日列表, code -> 涨停信息)。

    涨停信息保留最近一次涨停：limit_date(YYYYMMDD), name, industry, lbc。
    """
    now = datetime.now()
    calendar = [(now - timedelta(days=i)).strftime("%Y%m%d") for i in range(max_calendar)]

    def one(ds):
        try:
            return ds, em.fetch_ex_pool("getTopicZTPool", date=ds)
        except Exception:
            return ds, None

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(one, calendar))

    dates = []
    by_date = {}
    for ds, data in results:
        if data and data.get("tc"):
            dates.append(ds)
            by_date[ds] = data.get("pool") or []
    dates.sort()

    pool_by_code = {}
    for ds in dates[-days:]:
        for x in by_date.get(ds, []):
            code = str(x.get("c") or "")
            if not code or code == "000000":
                continue
            # 保留最近一次涨停信息
            pool_by_code[code] = {
                "limit_date": ds,
                "name": x.get("n"),
                "industry": x.get("hybk"),
                "lbc": int(x.get("lbc") or 0),
            }
    return dates[-days:], pool_by_code


def _classify_stock(row, info, date_index):
    """单只个股：K线分类当前状态，横盘/上升才返回结果。"""
    code = row.get("f12")
    if not code:
        return None
    hist = em.fetch_kline_hist(str(code))
    if len(hist) < 25:
        return None
    state = classify_state(hist)
    if state == "downtrend":
        return None
    limit_date = info["limit_date"]
    days_since = date_index.get(limit_date, 0)
    return {
        "code": str(code),
        "name": row.get("f14"),
        "state": state,
        "state_label": STATE_LABELS[state],
        "pct": to_num(row.get("f3")),
        "price": to_num(row.get("f2")),
        "amount_yi": round(to_num(row.get("f6")) / 100000000, 2),
        "turnover": to_num(row.get("f8")),
        "vol_ratio": to_num(row.get("f10")),
        "industry": row.get("f100") or info.get("industry"),
        "limit_date": f"{limit_date[:4]}-{limit_date[4:6]}-{limit_date[6:]}",
        "days_since": days_since,
        "lbc": info.get("lbc") or 0,
        "ma20": round(sum(h["close"] for h in hist[-20:]) / 20, 2),
        "pct_5d": pct_5d(hist),
    }


def fetch_limit20_scan():
    """20日涨停形态扫描主函数。"""
    errors = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "stocks": ex.submit(_safe, "stocks", lambda: net.fetch_paged(ALL_A_FS, SCAN_FIELDS, limit=6000)),
            "pools": ex.submit(_safe, "pools", collect_limit_pools),
        }
        results = {k: f.result() for k, f in futures.items()}
        context = ex.submit(fetch_market_context).result()
    errors.extend(context["errors"])

    stocks = results["stocks"][1] if not isinstance(results["stocks"], dict) else []
    dates, pool_by_code = results["pools"][1] if not isinstance(results["pools"], dict) else ([], {})
    for k in ("stocks", "pools"):
        v = results[k]
        if isinstance(v, dict) and "error" in v:
            errors.append(v["error"])

    date_index = {ds: (len(dates) - 1 - i) for i, ds in enumerate(dates)}  # 距今天数（0=最近交易日）
    code_map = {}
    for r in stocks:
        code = str(r.get("f12") or "")
        if code:
            code_map[code] = r

    def classify(code):
        info = pool_by_code[code]
        row = code_map.get(code)
        if row is None:
            return None
        return _classify_stock(row, info, date_index)

    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as ex:
        hits = list(ex.map(classify, list(pool_by_code.keys())))

    matched = [x for x in hits if x is not None]
    # 先统计（全量），再按状态分组排序截断输出
    uptrend_count = sum(1 for x in matched if x["state"] == "uptrend")
    sideways_count = sum(1 for x in matched if x["state"] == "sideways")
    uptrend_stocks = sorted([x for x in matched if x["state"] == "uptrend"],
                            key=lambda x: -x["amount_yi"])[:STOCK_LIMIT]
    sideways_stocks = sorted([x for x in matched if x["state"] == "sideways"],
                             key=lambda x: -x["amount_yi"])[:STOCK_LIMIT]

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "window_dates": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in dates],
        "universe": len(pool_by_code),
        "uptrend_count": uptrend_count,
        "sideways_count": sideways_count,
        "uptrend_stocks": uptrend_stocks,
        "sideways_stocks": sideways_stocks,
        "errors": errors,
    }
