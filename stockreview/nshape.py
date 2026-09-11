# -*- coding: utf-8 -*-
"""N型反转：策略选股版 N 字形态 + 板块共振。

技术图形特点（三段式 N 型，形态像字母 N）：
- 第一笔「上」：3-7 根阳线累计涨幅 ≥20%（强势启动、量能放大，确认活跃强势股）。
- 第二笔「下」：3-8 天缩量回调（均量 ≤ 前5日均量×0.9）、回踩不破第一波起涨低点
  （洗盘而非出货，N 字中间的下探段）。
- 第三笔「上」：放量阳线（量 ≥ 前5日均量×1.2）上穿 5 日线、收复回调跌幅——N 字成型、反转启动。

板块共振：信号股所属行业/概念板块当日走强（板块涨幅>0 且主力净流入>0 = 强共振；
仅涨幅>0 = 一般共振），确认 N 型反转有板块合力支撑而非个股独走。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .config import ALL_A_FS
from .utils import amount_floor, select_candidates, to_num

RISK_TEXT = "本文为策略选股研究参考，不构成任何投资建议。市场有风险，投资需谨慎。"

SCAN_FIELDS = "f2,f3,f6,f8,f10,f12,f14,f100"
MIN_AMOUNT_YI = 5.0
PCT_MIN, PCT_MAX = 0.5, 7.0   # 第三笔当日多为放量阳线（非涨停追高）
MAX_CHECK = 250

N_GAIN = 0.20       # 第一波累计涨幅 ≥20%
N_DAYS_MIN, N_DAYS_MAX = 3, 8  # 回调期 3-8 天
N_SHRINK = 0.9      # 回调期均量 ≤ 前5日均量×0.9（缩量洗盘）
N_VOL_MULT = 1.2    # 第三笔放量 ≥1.2 倍


def _ma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def _check_n_shape(hist):
    """三段式 N 型：返回信号 dict 或 None（参数见模块常量）。"""
    if len(hist) < 45:
        return None
    seg = hist[-31:-1]  # 不含今日
    low_i = min(range(len(seg)), key=lambda k: seg[k]["low"])
    L0 = seg[low_i]["low"]
    if L0 <= 0:
        return None
    after = seg[low_i + 1:]
    if not after:
        return None
    high_i = max(range(len(after)), key=lambda k: after[k]["high"])
    H0 = after[high_i]["high"]
    idx_h = len(hist) - 31 + low_i + 1 + high_i
    gain = H0 / L0 - 1
    if gain < N_GAIN:
        return None
    days = len(hist) - 1 - idx_h
    if not (N_DAYS_MIN <= days <= N_DAYS_MAX):
        return None
    base = hist[max(0, idx_h - 5):idx_h]
    avg5 = sum(x["volume"] for x in base) / len(base) if base else 0
    if avg5 <= 0:
        return None
    pull = hist[idx_h + 1:-1]
    if not pull or len(pull) != days - 1:
        return None
    pull_avg = sum(x["volume"] for x in pull) / len(pull)
    if pull_avg / avg5 > N_SHRINK:
        return None  # 回调期未缩量
    if min(x["low"] for x in pull) <= L0:
        return None  # 回调跌破起涨低点（N 型破坏）
    t = hist[-1]
    if not (t["close"] > t["open"] and t["close"] > hist[-2]["close"]):
        return None  # 第三笔需放量阳线收复
    closes = [x["close"] for x in hist[-6:]]
    ma5 = _ma(closes, 5)
    if ma5 is None or t["close"] < ma5:
        return None  # 上穿5日线
    vr = t["volume"] / avg5
    if vr < N_VOL_MULT:
        return None
    return {
        "gain": round(gain * 100, 1), "days": days, "vol_ratio": round(vr, 2),
        "ma5": round(ma5, 2), "support": round(L0, 2), "high": round(H0, 2),
    }


def _board_resonance(f100, industry, concept):
    """板块共振：个股 f100 行业匹配板块行情，判断共振级别。

    返回 {name, pct, flow_yi, level} 或 None。
    level: strong=强共振（涨幅>0 且资金流入） / normal=一般共振（仅涨幅>0）
    """
    if not f100 or f100 == "-":
        return None
    candidates = []
    for b in industry + concept:
        name = b.get("name") or ""
        if name == f100 or f100 in name or name in f100:
            candidates.append(b)
    if not candidates:
        return None
    b = max(candidates, key=lambda x: to_num(x.get("pct")))
    pct = to_num(b.get("pct"))
    flow = to_num(b.get("flow_yi"))
    if pct != pct or pct <= 0:
        return {"name": b.get("name"), "pct": round(pct, 2), "flow_yi": flow,
                "level": "weak", "note": "板块未走强，无共振"}
    if flow > 0:
        return {"name": b.get("name"), "pct": round(pct, 2), "flow_yi": flow,
                "level": "strong", "note": "板块走强且主力净流入，强共振"}
    return {"name": b.get("name"), "pct": round(pct, 2), "flow_yi": flow,
            "level": "normal", "note": "板块走强但资金未明显流入"}


def fetch_nshape(date=None):
    """N型反转实时选股主函数。date 忽略（板块/行情为实时口径）。"""
    errors = []
    if date:
        errors.append("N型反转为实时口径，不支持历史回放（date 参数已忽略）")

    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=5) as ex:
        f_stocks = ex.submit(safe, "stocks", lambda: net.fetch_paged(ALL_A_FS, SCAN_FIELDS, limit=6000))
        f_ind = ex.submit(safe, "industry", em.fetch_industry_boards)
        f_con = ex.submit(safe, "concept", em.fetch_concept_boards)
        r_stocks = f_stocks.result()[1]
        r_ind = f_ind.result()[1]
        r_con = f_con.result()[1]

    for r in (r_stocks, r_ind, r_con):
        if isinstance(r, dict) and "error" in r:
            errors.append(r.get("error"))
    stocks = r_stocks if not isinstance(r_stocks, dict) else []
    industry = r_ind if not isinstance(r_ind, dict) else []
    concept = r_con if not isinstance(r_con, dict) else []

    # 预筛：第三笔当日放量阳线（0.5~7%）+ 流动性
    candidates = []
    for r in stocks:
        pct = to_num(r.get("f3"))
        amount = to_num(r.get("f6"))
        turnover = to_num(r.get("f8"))
        if pct != pct or amount < amount_floor(r.get("f12"), MIN_AMOUNT_YI) * 100000000 or not (PCT_MIN <= pct <= PCT_MAX) or turnover < 3.0:
            continue
        candidates.append({
            "code": str(r.get("f12")), "name": r.get("f14"),
            "pct": round(pct, 2), "amount_yi": round(amount / 100000000, 2),
            "vol_ratio": round(to_num(r.get("f10")), 2),
            "industry": r.get("f100"),
        })
    candidates = select_candidates(candidates, MAX_CHECK, key=lambda x: x["amount_yi"])

    # K线核对 N 型
    def enrich(c):
        try:
            hist = em.fetch_kline_hist(c["code"])
            n = _check_n_shape(hist)
            if n:
                return {**c, **n}
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=24) as ex:
        hits = [x for x in ex.map(enrich, candidates) if x is not None]

    # 板块共振
    for h in hits:
        h["resonance"] = _board_resonance(h.get("industry"), industry, concept)

    hits.sort(key=lambda x: (0 if (x["resonance"] or {}).get("level") == "strong" else
                              1 if (x["resonance"] or {}).get("level") == "normal" else 2,
                              -x["amount_yi"]))
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rule": "N型反转：20%+拉升 → 3-8天缩量回调不破起涨点 → 放量阳线上穿5日线（第三笔启动）",
        "stocks": hits,
        "count": len(hits),
        "risk": RISK_TEXT,
        "errors": errors,
    }
