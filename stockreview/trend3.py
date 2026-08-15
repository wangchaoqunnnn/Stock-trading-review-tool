# -*- coding: utf-8 -*-
"""3日以上连续小幅放量阳线 + 上升趋势策略。

- 阳线：收盘 > 开盘
- 小幅放量：成交量较前一日放大 5%~150%（温和放量，非爆量）
- 连续 3 日及以上满足上述条件（从最新一日往前数）
- 上升趋势：收盘站上 MA20 且 MA20 走高
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .analysis import is_uptrend, pct_5d, yang_streak
from .config import ALL_A_FS
from .utils import to_num

# 全A扫描行情字段
SCAN_FIELDS = "f2,f3,f6,f8,f10,f12,f14,f17,f18,f22,f62,f184,f100"

MIN_STREAK = 3
# 预筛：今日量比（相对5日均量）的小幅放量区间
PRE_VOL_MIN = 1.0
PRE_VOL_MAX = 2.5
# 预筛：成交额下限（亿）
MIN_AMOUNT_YI = 3.0
# 个股K线核对上限
STOCK_CHECK_LIMIT = 300


def _safe(name, fn):
    try:
        return name, fn()
    except Exception as exc:
        return name, {"error": f"{type(exc).__name__}: {exc}"}


def _market_context():
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "indices": ex.submit(_safe, "indices", em.fetch_indices),
            "breadth": ex.submit(_safe, "breadth", em.fetch_breadth),
            "zt": ex.submit(_safe, "zt", em.fetch_zt_pool),
            "zb": ex.submit(_safe, "zb", em.fetch_zb_pool),
            "dt": ex.submit(_safe, "dt", em.fetch_dt_pool),
            "amount": ex.submit(_safe, "amount", em.fetch_market_amount),
        }
        results = {k: f.result() for k, f in futures.items()}

    def val(k, default):
        return results[k][1] if not isinstance(results[k], dict) else default

    from .analysis import compute_emotion
    zt = val("zt", {"tc": 0, "pool": []})
    zb = val("zb", {"tc": 0, "pool": []})
    dt = val("dt", {"tc": 0, "pool": []})
    emotion = compute_emotion(zt, zb, dt)
    errors = [str(v.get("error")) for v in results.values() if isinstance(v, dict) and "error" in v]
    return {
        "indices": val("indices", []),
        "breadth": val("breadth", {"up": 0, "down": 0, "flat": 0}),
        "emotion": emotion,
        "amount_yi": val("amount", None),
        "errors": errors,
    }


def _check_stock(row):
    """单只个股：K线核对连续放量阳线 + 上升趋势。"""
    code = row.get("f12")
    if not code:
        return None
    hist = em.fetch_kline_hist(str(code))
    if len(hist) < 25:
        return None
    days = yang_streak(hist)
    if days < MIN_STREAK or not is_uptrend(hist):
        return None
    return {
        "code": str(code),
        "name": row.get("f14"),
        "pct": to_num(row.get("f3")),
        "price": to_num(row.get("f2")),
        "vol_ratio": to_num(row.get("f10")),
        "amount_yi": round(to_num(row.get("f6")) / 100000000, 2),
        "turnover": to_num(row.get("f8")),
        "industry": row.get("f100"),
        "days": days,
        "ma20": round(sum(h["close"] for h in hist[-20:]) / 20, 2),
        "pct_5d": pct_5d(hist),
    }


def _check_board(b):
    """单只板块：K线核对连续放量阳线 + 上升趋势。"""
    code = b.get("code")
    if not code:
        return None
    hist = em.fetch_board_kline(str(code))
    if len(hist) < 25:
        return None
    days = yang_streak(hist)
    if days < MIN_STREAK or not is_uptrend(hist):
        return None
    return {
        "code": str(code),
        "name": b.get("name"),
        "pct": b.get("pct"),
        "flow_yi": b.get("flow_yi"),
        "vol_ratio": b.get("vol_ratio"),
        "days": days,
        "ma20": round(sum(h["close"] for h in hist[-20:]) / 20, 2),
        "pct_5d": pct_5d(hist),
    }


def fetch_trend3_scan():
    """连续放量阳线扫描主函数。"""
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "industry": ex.submit(_safe, "industry", em.fetch_industry_boards),
            "concept": ex.submit(_safe, "concept", em.fetch_concept_boards),
            "stocks": ex.submit(_safe, "stocks", lambda: net.fetch_paged(ALL_A_FS, SCAN_FIELDS, limit=6000)),
        }
        results = {k: f.result() for k, f in futures.items()}
        context = ex.submit(_market_context).result()

    errors = list(context["errors"])
    industry = results["industry"][1] if not isinstance(results["industry"], dict) else []
    concept = results["concept"][1] if not isinstance(results["concept"], dict) else []
    stocks = results["stocks"][1] if not isinstance(results["stocks"], dict) else []
    for k in ("industry", "concept", "stocks"):
        v = results[k]
        if isinstance(v, dict) and "error" in v:
            errors.append(v["error"])

    # ---- 个股预筛：今日阳线 + 温和放量 + 流动性 ----
    def pre_stock(r):
        pct = to_num(r.get("f3"))
        close = to_num(r.get("f2"))
        open_ = to_num(r.get("f17"))
        vr = to_num(r.get("f10"))
        amount = to_num(r.get("f6"))
        return (
            close > open_ and 0 < pct <= 7
            and PRE_VOL_MIN <= vr <= PRE_VOL_MAX
            and amount >= MIN_AMOUNT_YI * 100000000
        )
    stock_candidates = [r for r in stocks if pre_stock(r)]
    stock_candidates.sort(key=lambda r: -to_num(r.get("f10")))
    stock_candidates = stock_candidates[:STOCK_CHECK_LIMIT]
    with ThreadPoolExecutor(max_workers=16) as ex:
        stock_hits = list(ex.map(_check_stock, stock_candidates))
    stock_results = sorted([x for x in stock_hits if x is not None],
                           key=lambda x: (-x["days"], -x["pct_5d"] or 0))[:100]

    # ---- 板块预筛：今日阳线 + 温和放量 ----
    def pre_board(b):
        pct = to_num(b.get("pct"))
        vr = to_num(b.get("vol_ratio"))
        return pct > 0 and PRE_VOL_MIN <= vr <= PRE_VOL_MAX
    board_candidates = [b for b in (industry + concept) if pre_board(b)]
    with ThreadPoolExecutor(max_workers=12) as ex:
        board_hits = list(ex.map(_check_board, board_candidates))
    board_results = sorted([x for x in board_hits if x is not None],
                           key=lambda x: (-x["days"], -x["pct_5d"] or 0))[:60]

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "scanned_stocks": len(stock_candidates),
        "stocks": stock_results,
        "scanned_boards": len(board_candidates),
        "boards": board_results,
        "errors": errors,
    }
