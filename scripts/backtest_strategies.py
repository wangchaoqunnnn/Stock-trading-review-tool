# -*- coding: utf-8 -*-
"""交易策略系统 2/3 回测。

系统2（涨停缩量回踩均线）：
- 前20日内出现过涨停（close/prev_close-1 >= 9.5%）
- 当日盘中最低触及 MA5（low <= MA5*1.005）且收盘站稳（close >= MA5*0.985）
- 当日缩量（vol <= 前5日均量*0.9）

系统3（连续放量阳线趋势跟随）：
- 连续 >=3 日阳线（close>open）且温和放量（vol 介于前日 1.02~2.5 倍）
- 站上 MA20 且 MA20 走高（ma20 较 5 日前上行）

结果口径与 backtest_support.py 一致：信号后 3/5 日收益与胜率。
用法: python scripts/backtest_strategies.py [样本数]
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stockreview.config import ALL_A_FS  # noqa: E402
from stockreview.net import fetch_paged  # noqa: E402
from scripts.backtest_support import fetch_sina_kline  # noqa: E402

LOOKBACK = 250
HORIZON = 5


def ma_of(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def eval_sys2(hist, i):
    """涨停缩量回踩 MA5。返回 (特征, 结果) 或 None。"""
    if i < 30 or i + HORIZON >= len(hist):
        return None
    t = hist[i]
    # 前20日有涨停
    limit_hit = False
    for j in range(max(1, i - 20), i):
        prev = hist[j - 1]["close"]
        if prev > 0 and hist[j]["close"] / prev - 1 >= 0.095:
            limit_hit = True
            break
    if not limit_hit:
        return None
    closes = [x["close"] for x in hist[i - 10:i + 1]]
    ma5 = ma_of(closes, 5)
    if ma5 is None or ma5 <= 0:
        return None
    if not (t["low"] <= ma5 * 1.005 and t["close"] >= ma5 * 0.985):
        return None
    prev5 = hist[max(0, i - 5):i]
    avg5 = sum(x["volume"] for x in prev5) / len(prev5) if prev5 else 0
    if avg5 <= 0 or t["volume"] / avg5 > 0.9:
        return None
    if t["close"] < hist[i - 1]["close"] * 0.97:
        return None  # 剔除暴跌
    close0 = t["close"]
    ret3 = hist[i + 3]["close"] / close0 - 1 if i + 3 < len(hist) else None
    ret5 = hist[i + HORIZON]["close"] / close0 - 1
    no_lower = min(x["low"] for x in hist[i + 1:i + 3]) >= t["low"] if i + 3 <= len(hist) else None
    return {"shrink": t["volume"] / avg5}, {"ret3": ret3, "ret5": ret5, "no_lower": no_lower}


def eval_sys3(hist, i):
    """连续放量阳线趋势跟随。返回 (特征, 结果) 或 None。"""
    if i < 60 or i + HORIZON >= len(hist):
        return None
    streak = 0
    for j in range(i, max(0, i - 6), -1):
        t = hist[j]
        prev_v = hist[j - 1]["volume"] if j > 0 else 0
        if t["close"] > t["open"] and prev_v > 0 and 1.02 <= t["volume"] / prev_v <= 2.5:
            streak += 1
        else:
            break
    if streak < 3:
        return None
    closes = [x["close"] for x in hist[i - 25:i + 1]]
    ma20 = ma_of(closes, 20)
    ma20_prev = ma_of(closes[:-5], 20)
    t = hist[i]
    if ma20 is None or ma20_prev is None:
        return None
    if not (t["close"] > ma20 and ma20 > ma20_prev):
        return None
    close0 = t["close"]
    ret3 = hist[i + 3]["close"] / close0 - 1 if i + 3 < len(hist) else None
    ret5 = hist[i + HORIZON]["close"] / close0 - 1
    return {"streak": streak}, {"ret3": ret3, "ret5": ret5, "no_lower": None}


def run(histories, eval_fn):
    ret3s, ret5s, nls = [], [], []
    signals = 0
    for hist in histories:
        for i in range(LOOKBACK + HORIZON, len(hist) - HORIZON):
            r = eval_fn(hist, i)
            if r is None:
                continue
            _, out = r
            signals += 1
            if out["ret3"] is not None:
                ret3s.append(out["ret3"])
            ret5s.append(out["ret5"])
            if out["no_lower"] is not None:
                nls.append(out["no_lower"])

    def stat(xs):
        xs = [v for v in xs if v is not None]
        if not xs:
            return None
        win = sum(1 for v in xs if v > 0) / len(xs) * 100
        avg = sum(xs) / len(xs) * 100
        return round(win, 1), round(avg, 2)

    return {
        "signals": signals,
        "ret3": stat(ret3s),
        "ret5": stat(ret5s),
        "no_lower": (round(sum(1 for v in nls if v) / len(nls) * 100, 1) if nls else None),
    }


def main():
    sample_n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    print(f"抓取全A行情（按成交额取前 {sample_n} 只样本）...")
    stocks = fetch_paged(ALL_A_FS, "f2,f3,f6,f12,f14", fid="f6", po=1, limit=sample_n)
    codes = [str(r.get("f12")) for r in stocks]
    print(f"抓取 {len(codes)} 只日K...")

    def one(code):
        try:
            return fetch_sina_kline(code)
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=12) as ex:
        histories = [h for h in ex.map(one, codes) if len(h) >= LOOKBACK + HORIZON + 70]
    print(f"可用历史序列: {len(histories)} 只\n")

    for name, fn in (("系统2 涨停缩量回踩MA5", eval_sys2), ("系统3 连续放量阳线趋势", eval_sys3)):
        r = run(histories, fn)
        r3 = r["ret3"]
        r5 = r["ret5"]
        nl = r["no_lower"]
        print(f"{name}: 信号{r['signals']}  "
              f"3日胜率{(str(r3[0])+'%') if r3 else '-'} 3日均收{(str(r3[1])+'%') if r3 else '-'}  "
              f"5日胜率{(str(r5[0])+'%') if r5 else '-'} 5日均收{(str(r5[1])+'%') if r5 else '-'}  "
              f"不创新低{(str(nl)+'%') if nl is not None else '-'}")
    print("\n回测完成。")


if __name__ == "__main__":
    main()
