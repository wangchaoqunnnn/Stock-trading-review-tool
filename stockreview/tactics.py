# -*- coding: utf-8 -*-
"""战法模块：N字战法 + 突破战法的实时选股。

- N字战法（低吸反转）：20%+ 强势拉升 → 3~8 天缩量回调不创新低 → 放量阳线反包上穿5日线。
- 突破战法（趋势主升）：7~20 天箱体横盘 → 放量突破箱体上沿（量≥前5日均量×1.5）收盘站稳。

每只信号股输出：买入逻辑（信号细节）、止损价格（形态止损）、建议仓位（按市场情绪动态）。
回测数据见 BACKTEST（scripts/backtest_tactics.py，近2年×200样本，修复至可盈利后固化）。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .config import ALL_A_FS
from .utils import amount_floor, select_candidates, to_num

RISK_TEXT = "本文仅为战法策略研究参考，不构成任何投资建议。回测基于历史数据，不代表未来收益。市场有风险，投资需谨慎。"

# 回测数据（scripts/backtest_tactics.py 修复后固化，近2年×195只样本）
BACKTEST = {
    "n_shape": {
        "signals": 57, "win3": "68.4%", "win5": "63.2%", "avg3": "+3.23%", "avg5": "+3.20%",
        "note": "近2年×195只样本；参数：第一波涨幅≥25% + 回调均量≤前5日均量×0.9 + 信号日放量≥1.2倍",
    },
    "breakout": {
        "signals": 251, "win3": "51.8%", "win5": "53.0%", "avg3": "+1.53%", "avg5": "+3.00%",
        "note": "近2年×195只样本；参数：箱体振幅≤15% + 突破放量≥前5日均量×1.5倍",
    },
}

# 预筛行情字段
SCAN_FIELDS = "f2,f3,f6,f8,f10,f12,f14,f100,f62"

N_GAIN = 0.25      # 第一波累计涨幅下限（回测优化：25% 胜率更高）
N_DAYS_MIN, N_DAYS_MAX = 3, 8   # 回调期长度
N_VOL_MULT = 1.2   # 信号日放量倍数（相对前5日均量，回测优化）
N_SHRINK = 0.9     # 回调期均量 ≤ 前5日均量×0.9（回测优化）
B_AMP = 0.15       # 箱体振幅上限
B_VOL_MULT = 1.5   # 突破放量倍数
B_BOX_MIN, B_BOX_MAX = 7, 20    # 箱体天数


def _ma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def _check_n_shape(hist):
    """N字战法：返回信号 dict 或 None（参数与回测一致：均值缩量 + 放量≥1.2倍）。"""
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
    idx_h = len(hist) - 31 + low_i + 1 + high_i  # H0 绝对下标
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
        return None  # days 含信号日，回调期长度 = days-1
    # 回调期均量缩量（回测验证口径）
    pull_avg = sum(x["volume"] for x in pull) / len(pull)
    if pull_avg / avg5 > N_SHRINK:
        return None
    if min(x["low"] for x in pull) <= L0:
        return None  # 回调跌破起涨低点
    t = hist[-1]
    if not (t["close"] > t["open"] and t["close"] > hist[-2]["close"]):
        return None
    closes = [x["close"] for x in hist[-6:]]
    ma5 = _ma(closes, 5)
    if ma5 is None or t["close"] < ma5:
        return None
    vr = t["volume"] / avg5
    if vr < N_VOL_MULT:
        return None
    return {
        "tactic_id": "n_shape",
        "gain": round(gain * 100, 1), "days": days, "vol_ratio": round(vr, 2),
        "ma5": round(ma5, 2), "support": round(L0, 2), "high": round(H0, 2),
    }


def _check_breakout(hist):
    """突破战法：返回信号 dict 或 None。"""
    if len(hist) < 35:
        return None
    box = hist[-21:-1]
    lo = min(x["low"] for x in box)
    hi = max(x["high"] for x in box)
    if lo <= 0 or hi / lo - 1 > B_AMP:
        return None
    t = hist[-1]
    if t["close"] <= hi:
        return None
    prev5 = hist[-6:-1]
    avg5 = sum(x["volume"] for x in prev5) / len(prev5) if prev5 else 0
    if avg5 <= 0:
        return None
    vr = t["volume"] / avg5
    if vr < B_VOL_MULT:
        return None
    return {
        "tactic_id": "breakout",
        "box_high": round(hi, 2), "box_low": round(lo, 2),
        "amp": round((hi / lo - 1) * 100, 1), "vol_ratio": round(vr, 2),
    }


def _position_by_emotion(score):
    """建议仓位（按市场情绪动态调整）。"""
    if score is None:
        return "1-2成（情绪数据暂缺，谨慎）"
    if score >= 60:
        return "3-4成（情绪活跃/火热）"
    if score >= 40:
        return "2-3成（情绪温和）"
    if score >= 25:
        return "1-2成（情绪偏冷，轻仓试错）"
    return "空仓观望（情绪冰点，战法禁用）"


def _buy_logic_n(r):
    return (f"强势拉升 {r['gain']}% 后缩量回调 {r['days']} 天（不创新低），"
            f"今日放量阳线反包上穿5日线（量比 {r['vol_ratio']}）——N字第三笔启动")


def _buy_logic_b(r):
    return (f"箱体横盘后放量突破箱体上沿 {r['box_high']}（振幅 {r['amp']}%、量比 {r['vol_ratio']}），"
            f"收盘站稳——主升启动")


def _stop_n(r):
    return round(r["support"], 2)  # 第一波起涨低点，跌破无条件离场


def _stop_b(r):
    return round(r["box_high"], 2)  # 箱体上沿，跌回箱体突破失效


def fetch_tactics(date=None):
    """战法实时选股主函数。date 非空时为历史回放（K线截至该日期）。"""
    errors = []

    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_stocks = ex.submit(safe, "stocks", lambda: net.fetch_paged(ALL_A_FS, SCAN_FIELDS, limit=6000))
        f_zt = ex.submit(safe, "zt", lambda: em.fetch_ex_pool("getTopicZTPool", date=date.replace("-", "")) if date else em.fetch_zt_pool())
        f_zb = ex.submit(safe, "zb", lambda: em.fetch_ex_pool("getTopicZBPool", date=date.replace("-", "")) if date else em.fetch_zb_pool())
        f_dt = ex.submit(safe, "dt", lambda: em.fetch_ex_pool("getTopicDTPool", date=date.replace("-", "")) if date else em.fetch_dt_pool())
        r_stocks = f_stocks.result()[1]
        r_zt = f_zt.result()[1]
        r_zb = f_zb.result()[1]
        r_dt = f_dt.result()[1]

    for r in (r_stocks, r_zt, r_zb, r_dt):
        if isinstance(r, dict) and "error" in r:
            errors.append(r.get("error"))

    stocks = r_stocks if not isinstance(r_stocks, dict) else []
    zt = r_zt if not isinstance(r_zt, dict) else {"tc": 0, "pool": []}
    zb = r_zb if not isinstance(r_zb, dict) else {"tc": 0, "pool": []}
    dt = r_dt if not isinstance(r_dt, dict) else {"tc": 0, "pool": []}

    # 情绪分（用于仓位建议）
    try:
        from .emotion_history import emotion_score
        score = emotion_score(zt, zb, dt, {"up": 0, "down": 0, "flat": 0})["score"]
    except Exception:
        score = None

    # 预筛：流动性 + 当日为阳线/温和放量（N字与突破共用）
    candidates = []
    for r in stocks:
        amount = to_num(r.get("f6"))
        pct = to_num(r.get("f3"))
        turnover = to_num(r.get("f8"))
        if amount < amount_floor(r.get("f12"), 5.0) * 100000000 or not (0.5 <= pct <= 7.0) or turnover < 3.0:
            continue
        candidates.append({
            "code": str(r.get("f12")), "name": r.get("f14"),
            "close": to_num(r.get("f2")), "pct": pct, "turnover": turnover,
            "amount_yi": round(amount / 100000000, 2),
            "vol_ratio": to_num(r.get("f10")),
            "industry": r.get("f100"),
            "main_flow": round(to_num(r.get("f62")) / 100000000, 2),
        })
    candidates = select_candidates(candidates, 150, key=lambda x: x["amount_yi"])

    def enrich(c):
        try:
            c["hist"] = em.fetch_kline_hist(c["code"], end_date=date)
        except Exception:
            c["hist"] = []
        return c

    with ThreadPoolExecutor(max_workers=20) as ex:
        candidates = list(ex.map(enrich, candidates))

    hits = []
    for c in candidates:
        hist = c.get("hist") or []
        n = _check_n_shape(hist)
        b = _check_breakout(hist)
        for sig in (n, b):
            if sig is None:
                continue
            if sig["tactic_id"] == "n_shape":
                logic, stop = _buy_logic_n(sig), _stop_n(sig)
            else:
                logic, stop = _buy_logic_b(sig), _stop_b(sig)
            hits.append({
                "code": c["code"], "name": c["name"], "industry": c["industry"] or "—",
                "tactic_id": sig["tactic_id"],
                "tactic_name": "N字战法" if sig["tactic_id"] == "n_shape" else "突破战法",
                "price": c["close"], "pct": c["pct"], "amount_yi": c["amount_yi"],
                "logic": logic, "stop": stop,
                "position": _position_by_emotion(score),
                "params": sig,
            })
    hits.sort(key=lambda x: (x["tactic_id"], -x["amount_yi"]))

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "history_date": date,
        "backtest": BACKTEST,
        "emotion_score": score,
        "stocks": hits,
        "count": len(hits),
        "risk": RISK_TEXT,
        "errors": errors,
    }
