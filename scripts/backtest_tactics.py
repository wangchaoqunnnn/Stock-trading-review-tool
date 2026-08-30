# -*- coding: utf-8 -*-
"""N字战法 / 突破战法 回测。

N字战法（低吸反转）：
- 第一笔上涨：区间内从起涨低点到阶段高点累计涨幅 >= 20%（确认强势股）
- 二笔回调：阶段高点后 3~8 天，缩量回落（量 < 前5日均量）、不创新低（回调低点 > 起涨低点）
- 三笔启动（信号日）：放量阳线（close>open、vol>=回调期均量*vol_mult）、上穿5日线

突破战法（趋势主升）：
- 横盘蓄势：前 7~20 天在箱体内震荡（区间振幅 <= box_amp）
- 突破日（信号日）：收盘站上箱体上沿且放量（vol >= 前5日均量*vol_mult）

结果口径与 backtest_support.py 一致：信号后 3/5 日收益与胜率。
用法: python scripts/backtest_tactics.py [样本数]
"""
import os
import sys

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


def eval_n_shape(hist, i, gain=0.25, days_min=3, days_max=8, vol_mult=1.2, shrink=0.9):
    """N字战法信号。返回 (特征, 结果) 或 None。

    修复点（相对初版）：
    - 回调期由"每日都缩量"放宽为"回调期均量 <= 前5日均量×shrink"（洗盘允许偶发放量日）
    - 信号日放量相对前5日均量（vol >= avg5×vol_mult，初版相对回调均量×1.3 过严）
    """
    if i < 45 or i + HORIZON >= len(hist):
        return None
    # 区间 [i-30, i] 内找起涨低点与其后的阶段高点
    seg = hist[i - 30:i + 1]
    low_i = min(range(len(seg)), key=lambda k: seg[k]["low"])
    L0 = seg[low_i]["low"]
    if L0 <= 0:
        return None
    after = seg[low_i + 1:]  # 起涨点之后（不含信号日）
    if not after:
        return None
    high_i = max(range(len(after)), key=lambda k: after[k]["high"])
    H0 = after[high_i]["high"]
    idx_h = i - 30 + low_i + 1 + high_i  # H0 在 hist 中的绝对下标
    if H0 / L0 - 1 < gain:
        return None  # 第一波涨幅不足
    days = i - idx_h
    if not (days_min <= days <= days_max):
        return None  # 回调期长度不符
    # 回调期缩量：回调期均量 <= 前5日均量×shrink
    base = hist[max(0, idx_h - 5):idx_h]
    avg5 = sum(x["volume"] for x in base) / len(base) if base else 0
    if avg5 <= 0:
        return None
    pull = hist[idx_h + 1:i]
    if not pull:
        return None
    pull_avg = sum(x["volume"] for x in pull) / len(pull)
    if pull_avg / avg5 > shrink:
        return None  # 回调期整体未缩量
    if min(x["low"] for x in pull) <= L0 * 1.0:
        return None  # 回调创新低（跌破起涨低点）
    t = hist[i]
    # 信号日：放量阳线 + 收盘站上5日线
    if not (t["close"] > t["open"]):
        return None
    closes = [x["close"] for x in hist[i - 6:i + 1]]
    ma5 = ma_of(closes, 5)
    if ma5 is None or t["close"] < ma5:
        return None
    vr = t["volume"] / avg5
    if vr < vol_mult:
        return None
    if t["close"] < hist[i - 1]["close"]:
        return None  # 收盘未收复前日
    close0 = t["close"]
    ret3 = hist[i + 3]["close"] / close0 - 1 if i + 3 < len(hist) else None
    ret5 = hist[i + HORIZON]["close"] / close0 - 1
    return {"days": days, "gain": round(H0 / L0 - 1, 2), "vr": round(vr, 2)}, {"ret3": ret3, "ret5": ret5, "no_lower": None}


def eval_breakout(hist, i, box_days_min=7, box_days_max=20, box_amp=0.15, vol_mult=1.5):
    """突破战法信号。返回 (特征, 结果) 或 None。"""
    if i < box_days_max + 10 or i + HORIZON >= len(hist):
        return None
    box = hist[i - box_days_max:i]
    lo = min(x["low"] for x in box)
    hi = max(x["high"] for x in box)
    if lo <= 0 or hi / lo - 1 > box_amp:
        return None  # 箱体振幅过大（非横盘）
    t = hist[i]
    if t["close"] <= hi:
        return None  # 收盘未站上箱体上沿
    prev5 = hist[max(0, i - 5):i]
    avg5 = sum(x["volume"] for x in prev5) / len(prev5) if prev5 else 0
    if avg5 <= 0 or t["volume"] < avg5 * vol_mult:
        return None  # 未放量
    close0 = t["close"]
    ret3 = hist[i + 3]["close"] / close0 - 1 if i + 3 < len(hist) else None
    ret5 = hist[i + HORIZON]["close"] / close0 - 1
    return {"amp": round(hi / lo - 1, 3), "vr": round(t["volume"] / avg5, 2)}, {"ret3": ret3, "ret5": ret5, "no_lower": None}


def run(histories, eval_fn):
    ret3s, ret5s = [], []
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

    def stat(xs):
        xs = [v for v in xs if v is not None]
        if not xs:
            return None
        win = sum(1 for v in xs if v > 0) / len(xs) * 100
        avg = sum(xs) / len(xs) * 100
        return round(win, 1), round(avg, 2)

    return {"signals": signals, "ret3": stat(ret3s), "ret5": stat(ret5s)}


def main():
    sample_n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    print(f"抓取全A行情（按成交额取前 {sample_n} 只样本）...")
    stocks = fetch_paged(ALL_A_FS, "f2,f3,f6,f12,f14", fid="f6", po=1, limit=sample_n)
    codes = [str(r.get("f12")) for r in stocks]
    print(f"抓取 {len(codes)} 只日K...")

    from concurrent.futures import ThreadPoolExecutor

    def one(code):
        try:
            return fetch_sina_kline(code)
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=12) as ex:
        histories = [h for h in ex.map(one, codes) if len(h) >= LOOKBACK + HORIZON + 70]
    print(f"可用历史序列: {len(histories)} 只\n")

    combos = [
        ("N字 基线(修复)", dict()),
        ("N字 回调缩量0.9", dict(shrink=0.9)),
        ("N字 涨幅25%", dict(gain=0.25)),
        ("N字 涨幅25%+缩量0.9", dict(gain=0.25, shrink=0.9)),
        ("N字 放量1.5", dict(vol_mult=1.5)),
        ("突破 基线", dict()),
        ("突破 振幅10%", dict(box_amp=0.10)),
        ("突破 放量2倍", dict(vol_mult=2.0)),
        ("突破 振幅10%+放量2倍", dict(box_amp=0.10, vol_mult=2.0)),
    ]
    print(f"{'条件组合':<20}{'信号数':>6}{'3日胜率':>9}{'3日均收':>9}{'5日胜率':>9}{'5日均收':>9}")
    print("-" * 62)
    for name, kw in combos:
        fn = eval_n_shape if name.startswith("N字") else eval_breakout
        r = run(histories, lambda h, i, fn=fn, kw=kw: fn(h, i, **kw))
        r3 = r["ret3"]
        r5 = r["ret5"]
        print(f"{name:<20}{r['signals']:>6}"
              f"{(str(r3[0])+'%') if r3 else '-':>9}{(str(r3[1])+'%') if r3 else '-':>9}"
              f"{(str(r5[0])+'%') if r5 else '-':>9}{(str(r5[1])+'%') if r5 else '-':>9}")


if __name__ == "__main__":
    main()
