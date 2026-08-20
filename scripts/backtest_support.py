# -*- coding: utf-8 -*-
"""支撑位有效性策略回测。

把"支撑有效"文字策略转成可计算规则，用历史日K回测不同条件组合的胜率，
据此确定可操作、成功率合理的最终规则。

规则要素（可计算化）：
- 支撑位 S：近 support_window 日最低点（箱体下沿/前低，策略中"筹码密集区/箱体下沿"近似）
- 回踩：当日最低价触及支撑区间（low <= S*(1+touch)）
- 收盘站稳：收盘在支撑上方（close >= S*floor，floor=0.98 表示收盘未跌破2%）
- 缩量：当日量 <= 前5日均量 * shrink
- 锤子线：下影 >= 实体*2 且收盘收在上半部（close >= open）
- 确认：信号后 1 日出现放量阳线（vol >= 前5日均量 且 close > open）

结果（信号日 t 之后）：
- 3/5 日收益（close[t+n]/close[t]-1）
- 不创新低：min(low[t+1..t+2]) >= low[t]（后续2日最低不低于信号日低点）
- 胜率 = 收益>0 的比例；另算平均收益与样本数

用法: python scripts/backtest_support.py [样本数]
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stockreview.config import ALL_A_FS  # noqa: E402
from stockreview.net import fetch_paged  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
KLINE_DATALEN = 500  # 约 2 年日K
LOOKBACK = 250       # 回测最近 250 个交易日
HORIZON = 5          # 结果窗口 5 日


def fetch_sina_kline(code, datalen=KLINE_DATALEN):
    prefix = "sh" if code.startswith(("6", "9")) else "bj" if code.startswith(("4", "8", "92")) else "sz"
    symbol = prefix + code
    url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20t=/CN_MarketDataService.getKLineData?"
           + urllib.parse.urlencode({"symbol": symbol, "scale": 240, "ma": "no", "datalen": datalen}))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://finance.sina.com.cn/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read().decode("utf-8", "replace")
    m = re.search(r"\[(.*)\]", text, re.S)
    rows = json.loads("[" + m.group(1) + "]") if m else []
    out = []
    for x in rows:
        try:
            out.append({
                "date": x.get("day"),
                "open": float(x.get("open")), "close": float(x.get("close")),
                "high": float(x.get("high")), "low": float(x.get("low")),
                "volume": float(x.get("volume")),
            })
        except Exception:
            continue
    return out


def eval_signal(hist, i, support_window, touch, floor, shrink, need_shrink, need_hammer, need_confirm):
    """t=i 日是否产生信号；返回 (信号特征dict, 结果dict) 或 None。"""
    if i < support_window + 5 or i + HORIZON >= len(hist):
        return None
    before = hist[max(0, i - support_window):i]
    if not before:
        return None
    S = min(x["low"] for x in before)
    if S <= 0:
        return None
    t = hist[i]
    # 回踩 + 收盘站稳
    if not (t["low"] <= S * (1 + touch) and t["close"] >= S * floor):
        return None
    # 缩量
    prev5 = hist[max(0, i - 5):i]
    prev5_avg = sum(x["volume"] for x in prev5) / len(prev5) if prev5 else 0
    if prev5_avg <= 0:
        return None
    shrink_ratio = t["volume"] / prev5_avg
    if need_shrink and shrink_ratio > shrink:
        return None
    # 锤子线
    body = abs(t["close"] - t["open"])
    lower_shadow = min(t["open"], t["close"]) - t["low"]
    hammer = body > 0 and lower_shadow >= body * 2 and t["close"] >= t["open"]
    if need_hammer and not hammer:
        return None
    # 确认：次日放量阳线
    if need_confirm and i + 1 < len(hist):
        nxt = hist[i + 1]
        if not (nxt["close"] > nxt["open"] and nxt["volume"] >= prev5_avg):
            return None

    # 结果
    close0 = t["close"]
    ret3 = hist[i + 3]["close"] / close0 - 1 if i + 3 < len(hist) else None
    ret5 = hist[i + HORIZON]["close"] / close0 - 1
    no_lower = min(x["low"] for x in hist[i + 1:i + 3]) >= t["low"] if i + 3 <= len(hist) else None
    return ({"hammer": hammer, "shrink": shrink_ratio}, {"ret3": ret3, "ret5": ret5, "no_lower": no_lower})


def run_combination(histories, support_window=60, touch=0.02, floor=0.98, shrink=0.9,
                    need_shrink=False, need_hammer=False, need_confirm=False):
    """对全部历史序列跑一种条件组合，返回统计。"""
    ret3s, ret5s, no_lower_ok = [], [], []
    signals = 0
    for hist in histories:
        for i in range(LOOKBACK + HORIZON, len(hist) - HORIZON):
            r = eval_signal(hist, i, support_window, touch, floor, shrink,
                            need_shrink, need_hammer, need_confirm)
            if r is None:
                continue
            _, out = r
            signals += 1
            if out["ret3"] is not None:
                ret3s.append(out["ret3"])
            ret5s.append(out["ret5"])
            no_lower_ok.append(out["no_lower"])
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
        "no_lower": (round(sum(1 for v in no_lower_ok if v) / len(no_lower_ok) * 100, 1)
                     if no_lower_ok else None),
    }


def main():
    sample_n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    print(f"抓取全A行情（按成交额取前 {sample_n} 只样本）...")
    stocks = fetch_paged(ALL_A_FS, "f2,f3,f6,f12,f14", fid="f6", po=1, limit=sample_n)
    codes = [str(r.get("f12")) for r in stocks]
    print(f"抓取 {len(codes)} 只日K（datalen={KLINE_DATALEN}）...")

    def one(code):
        try:
            return fetch_sina_kline(code)
        except Exception:
            return []
    with ThreadPoolExecutor(max_workers=12) as ex:
        histories = [h for h in ex.map(one, codes) if len(h) >= LOOKBACK + HORIZON + 70]
    print(f"可用历史序列: {len(histories)} 只\n")

    combos = [
        ("基线(回踩+收盘站稳)", dict()),
        ("+缩量", dict(need_shrink=True)),
        ("+锤子线", dict(need_hammer=True)),
        ("+缩量+锤子线", dict(need_shrink=True, need_hammer=True)),
        ("+缩量+次日放量阳确认", dict(need_shrink=True, need_confirm=True)),
        ("+缩量+锤子线+确认", dict(need_shrink=True, need_hammer=True, need_confirm=True)),
        ("收盘阈值0.99+缩量", dict(floor=0.99, need_shrink=True)),
        ("收盘阈值0.99+缩量+锤子", dict(floor=0.99, need_shrink=True, need_hammer=True)),
    ]
    print(f"{'条件组合':<26}{'信号数':>6}{'3日胜率':>9}{'3日均收':>9}{'5日胜率':>9}{'5日均收':>9}{'不创新低%':>9}")
    print("-" * 78)
    for name, kw in combos:
        r = run_combination(histories, **kw)
        r3 = r["ret3"]; r5 = r["ret5"]; nl = r["no_lower"]
        print(f"{name:<26}{r['signals']:>6}"
              f"{(str(r3[0])+'%') if r3 else '-':>9}{(str(r3[1])+'%') if r3 else '-':>9}"
              f"{(str(r5[0])+'%') if r5 else '-':>9}{(str(r5[1])+'%') if r5 else '-':>9}"
              f"{(str(nl)+'%') if nl is not None else '-':>9}")


if __name__ == "__main__":
    main()
