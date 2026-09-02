# -*- coding: utf-8 -*-
"""上升趋势 V 字洗盘：实时选股。

满足条件：
1. 上升趋势：站上 MA20 且 MA20 走高（均线多头向上）。
2. 当日分时深 V：盘中有一段明显下跌（V 底深度 >=2%），随后放量拉回收复过半跌幅。
3. 量能配合：下跌段（到 V 底）缩量、回升段（V 底后）放量。
4. 股价处于 20 日线之上（第 1 条已含）。

数据源：东财全市场 clist 预筛 + 日K（MA20/趋势）+ 分时 trends2（深 V 与量能）。
"""
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .config import ALL_A_FS, INDEX_UT
from .utils import to_num

RISK_TEXT = "本文为策略选股研究参考，不构成任何投资建议。市场有风险，投资需谨慎。"

SCAN_FIELDS = "f2,f3,f6,f8,f10,f12,f14,f100"
MIN_AMOUNT_YI = 8.0     # 预筛成交额下限（亿）
PCT_MIN, PCT_MAX = -5.0, 5.0   # 预筛当日涨跌幅区间（深V当日多为小幅波动）
MAX_CHECK = 250         # K线核对上限
MAX_TICK = 80           # 分时核对上限（K线通过者中取）
V_DEPTH_MIN = 0.02      # V 底深度（高点→低点跌幅）≥2%
RECOVER_MIN = 0.5       # 收盘收复跌幅 ≥50%（深V拉回）
VOL_UP_RATIO = 1.15     # 回升段均量 / 下跌段均量 ≥1.15（上涨放量）


def _ma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def _check_trend(hist):
    """K线核对：站上 MA20 且 MA20 走高（上升趋势）。"""
    if len(hist) < 30:
        return None
    closes = [h["close"] for h in hist]
    ma20 = _ma(closes, 20)
    ma20_prev = _ma(closes[:-5], 20)
    close = closes[-1]
    if ma20 is None or ma20_prev is None or close <= ma20 or ma20 <= ma20_prev:
        return None
    return {"ma20": round(ma20, 2), "close": round(close, 2)}


def _v_shape(closes, amounts):
    """分时深 V 检测。返回特征 dict 或 None。

    closes: 逐分钟收盘价序列；amounts: 逐分钟成交额（元）。
    """
    if len(closes) < 30:
        return None
    # 去掉开头跳空/异常分钟（0 价）
    valid = [(c, a) for c, a in zip(closes, amounts) if c and c == c]
    if len(valid) < 30:
        return None
    cs = [v[0] for v in valid]
    am = [v[1] for v in valid]
    idx_min = min(range(len(cs)), key=lambda i: cs[i])
    if idx_min < 10 or idx_min > len(cs) - 10:
        return None  # V 底应出现在中段（早盘后下探、尾盘前回升）
    H = max(cs[:idx_min + 1])
    low = cs[idx_min]
    if H <= 0:
        return None
    depth = (H - low) / H
    if depth < V_DEPTH_MIN:
        return None
    final = cs[-1]
    recover = (final - low) / (H - low) if H > low else 0.0
    if recover < RECOVER_MIN:
        return None  # 未收复过半 → 不是洗盘后拉回
    # 量能：下跌段（V 底前）缩量 vs 回升段（V 底后）放量
    down_avg = sum(am[:idx_min + 1]) / (idx_min + 1) if idx_min + 1 > 0 else 0
    up_seg = am[idx_min + 1:]
    up_avg = sum(up_seg) / len(up_seg) if up_seg else 0
    if down_avg <= 0 or up_avg / down_avg < VOL_UP_RATIO:
        return None
    return {
        "depth": round(depth * 100, 2),
        "recover": round(recover * 100, 1),
        "vol_ratio": round(up_avg / down_avg, 2),
        "low": round(low, 2), "high": round(H, 2),
        "v_time": f"{idx_min:02d}分钟处",
    }


def _intraday(code):
    """单只个股分时（收盘价 + 成交额序列）。push2his/push2delay 主备并发。"""
    try:
        secid = ("1." if code.startswith("6") else "0.") + code
        params = {
            "secid": secid,
            "ut": INDEX_UT,
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "iscr": 0, "iscca": 1, "ndays": 1,
        }

        def _one(host):
            try:
                url = f"https://{host}/api/qt/stock/trends2/get?" + urllib.parse.urlencode(params)
                data = net.http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"}, tries=1, timeout=6)
                trends = (data.get("data") or {}).get("trends") or []
                closes, amounts = [], []
                for t in trends:
                    p = t.split(",")
                    if len(p) < 7:
                        continue
                    closes.append(to_num(p[2]))
                    amounts.append(to_num(p[6]))
                if not closes:
                    return None
                return closes, amounts
            except Exception:
                return None

        return net.race_fns([lambda: _one("push2his.eastmoney.com"), lambda: _one("push2delay.eastmoney.com")], prefer=0)
    except Exception:
        return None


def fetch_vshape(date=None):
    """V字洗盘实时选股主函数。date 忽略（分时为实时数据源）。"""
    errors = []
    if date:
        errors.append("V字洗盘为分时实时口径，不支持历史回放（date 参数已忽略）")

    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_stocks = ex.submit(safe, "stocks", lambda: net.fetch_paged(ALL_A_FS, SCAN_FIELDS, limit=6000))
        r_stocks = f_stocks.result()[1]
    if isinstance(r_stocks, dict) and "error" in r_stocks:
        errors.append(r_stocks.get("error"))
        stocks = []
    else:
        stocks = r_stocks

    # 预筛：小幅波动 + 流动性
    candidates = []
    for r in stocks:
        pct = to_num(r.get("f3"))
        amount = to_num(r.get("f6"))
        if pct != pct or amount < MIN_AMOUNT_YI * 100000000 or not (PCT_MIN <= pct <= PCT_MAX):
            continue
        candidates.append({
            "code": str(r.get("f12")), "name": r.get("f14"),
            "pct": round(pct, 2), "amount_yi": round(amount / 100000000, 2),
            "turnover": round(to_num(r.get("f8")), 2),
            "vol_ratio": round(to_num(r.get("f10")), 2),
            "industry": r.get("f100"),
        })
    candidates.sort(key=lambda x: -x["amount_yi"])
    candidates = candidates[:MAX_CHECK]

    # 1) K线核对：站上MA20且MA20走高
    def enrich(c):
        try:
            hist = em.fetch_kline_hist(c["code"])
            tr = _check_trend(hist)
            if tr:
                c["ma20"] = tr["ma20"]
                c["close"] = tr["close"]
                return c
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=24) as ex:
        trend_ok = [x for x in ex.map(enrich, candidates) if x is not None]
    trend_ok.sort(key=lambda x: -x["amount_yi"])
    trend_ok = trend_ok[:MAX_TICK]

    # 2) 分时深 V 检测
    def check_v(c):
        try:
            data = _intraday(c["code"])
            if not data:
                return None
            v = _v_shape(data[0], data[1])
            if not v:
                return None
            return {**c, **v}
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=20) as ex:
        hits = [x for x in ex.map(check_v, trend_ok) if x is not None]

    hits.sort(key=lambda x: -x["depth"])
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rule": "上升趋势（站上MA20且MA20走高）+ 当日分时深V（下跌缩量、回升放量、收复过半跌幅）",
        "stocks": hits,
        "count": len(hits),
        "risk": RISK_TEXT,
        "errors": errors,
    }
