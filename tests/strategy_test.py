# -*- coding: utf-8 -*-
"""新增策略（3日资金 / 放量阳线）的离线验证测试。

1. 纯函数单元测试：资金流解析、连续天数、放量阳线连续天数、上升趋势判断。
2. 扫描函数离线测试：用假数据打桩 em/net 抓取，验证 flow3/trend3 聚合结果符合预期。
3. 生成 flow3/trend3 端点的基线 schema fixture（供 verify_schema.py 做结构回归）。
"""
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stockreview import analysis, em, net  # noqa: E402
from stockreview.flow3 import fetch_flow3_scan  # noqa: E402
from stockreview.trend3 import fetch_trend3_scan  # noqa: E402


class FakeDT:
    fixed = datetime(2026, 8, 14, 10, 30, 0)

    @classmethod
    def now(cls):
        return cls.fixed


# ---------- 假数据 ----------

FAKE_INDICES = [
    {"name": "上证指数", "pre_close": 3000.0, "current": 3010.0, "pct": 0.33, "avg_price": 3005.0, "above_avg": True, "vs_avg_pct": 0.17},
    {"name": "北证50", "pre_close": 1100.0, "current": 1105.0, "pct": 0.45, "avg_price": None, "above_avg": None, "vs_avg_pct": None},
]
FAKE_BREADTH = {
    "up": 2500, "down": 1800, "flat": 200,
    "distribution": [{"key": "-3", "count": 30}, {"key": "0", "count": 200}, {"key": "2", "count": 500}],
    "date": "20260814",
}
FAKE_EMPTY_POOL = {"tc": 0, "pool": []}

# 板块（board_rows 输出格式）
FAKE_BOARDS = [
    {"code": "BK01", "name": "半导体", "pct": 3.2, "gap": 1.0, "flow_yi": 8.0, "amount_yi": 100.0,
     "turnover": 2.0, "vol_ratio": 1.5, "ratio": 0.5, "up": 3, "down": 1, "leader": "甲", "leader_pct": 10.0, "leader_code": "600001"},
    {"code": "BK02", "name": "银行", "pct": -0.5, "gap": -0.2, "flow_yi": -2.0, "amount_yi": 50.0,
     "turnover": 0.5, "vol_ratio": 0.8, "ratio": 0.1, "up": 0, "down": 2, "leader": "银行股", "leader_pct": 0.5, "leader_code": "601398"},
    {"code": "BK03", "name": "食品", "pct": 1.0, "gap": 0.3, "flow_yi": 0.5, "amount_yi": 30.0,
     "turnover": 1.0, "vol_ratio": 1.1, "ratio": 0.2, "up": 1, "down": 0, "leader": "丙", "leader_pct": 2.0, "leader_code": "000003"},
]
FAKE_CONCEPT = [
    {"code": "BK10", "name": "人工智能", "pct": 2.0, "gap": 0.5, "flow_yi": 3.0, "amount_yi": 80.0,
     "turnover": 1.8, "vol_ratio": 1.4, "ratio": 0.4, "up": 2, "down": 0, "leader": "甲", "leader_pct": 10.0, "leader_code": "600001"},
]


def fflow_lines(daily_flows):
    """按每日主力净流入序列（旧->新）构造 fflow daykline 行。"""
    lines = []
    for i, mf in enumerate(daily_flows):
        lines.append(f"2026-08-{10 + i:02d},{mf:.1f},0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,10.0,1.0,0.0,0.0")
    return lines


FFLOW_MAP = {
    "90.BK01": fflow_lines([1.0e8, 2.0e8, 3.0e8, 4.0e8]),          # 4 连流入
    "90.BK02": fflow_lines([-1.0e8, -2.0e8, -3.0e8]),              # 3 连流出
    "90.BK03": fflow_lines([1.0e8, -1.0e8, 1.0e8, -1.0e8]),        # 无连续
    "90.BK10": fflow_lines([5.0e7, 6.0e7, 7.0e7]),                 # 3 连流入
    "1.600001": fflow_lines([1.0e8, 2.0e8, 3.0e8, 4.0e8, 5.0e8]),  # 5 连流入
    "0.600002": fflow_lines([1.0e8, 2.0e8, -1.0e8]),               # 2 流入后流出
}


def stock_row(code, name, pct, amount, vr, flow, close=None, open_=None, industry="半导体"):
    close = close if close is not None else 10.0
    open_ = open_ if open_ is not None else close * 0.99
    return {
        "f2": close, "f3": pct, "f6": amount, "f8": 10.0, "f10": vr,
        "f12": code, "f14": name, "f17": open_, "f18": close / (1 + pct / 100),
        "f22": 1.0, "f62": flow, "f184": 0.5, "f100": industry,
    }


FAKE_STOCKS = [
    stock_row("600001", "甲科技", 5.0, 5.0e8, 1.8, 5.0e8),          # 今日流入，fflow 5连 → 命中
    stock_row("600002", "乙软件", 2.0, 5.0e8, 1.2, 2.0e8),          # 今日流入，fflow 不连续 → 不命中
    stock_row("600003", "丙数据", 1.0, 5.0e8, 1.0, -1.0e8),         # 今日流出 → 预筛排除
]


def build_kline(n=40, streak=4, vol=1_000_000.0, base=10.0, flat_break=False):
    """构造日K：前期缓涨，最后 streak 天阳线且每天量能较前一日放大 1.3 倍；
    flat_break 时把 streak 首日前一天改为阴线（用于打断连续性）。"""
    rows = []
    close = base
    for i in range(n):
        if i >= n - streak:
            open_ = close * 0.995
            close = close * 1.01
            volume = vol * 1.3 if i == n - streak else rows[-1]["volume"] * 1.3
        elif flat_break and i == n - streak - 1:
            open_ = close * 1.01
            close = close * 0.99
            volume = vol
        else:
            open_ = close
            close = close * 1.003
            volume = vol
        rows.append({
            "date": f"2026-08-{i:02d}", "open": round(open_, 2), "close": round(close, 2),
            "high": round(max(open_, close) * 1.01, 2), "low": round(min(open_, close) * 0.99, 2),
            "volume": volume, "amount": volume * close, "pct": round((close / open_ - 1) * 100, 2),
        })
    return rows


KLINE_MAP = {
    "600001": build_kline(streak=4),        # 4 连阳放量 + 上升 → 命中
    "600002": build_kline(streak=2, flat_break=True),  # 仅 2 连 → 不命中
    "BK01": build_kline(streak=3, base=100.0),
    "BK10": build_kline(streak=2, base=50.0, flat_break=True),
}


def patch_fetchers():
    em.fetch_industry_boards = lambda: [dict(x) for x in FAKE_BOARDS]
    em.fetch_concept_boards = lambda: [dict(x) for x in FAKE_CONCEPT]
    net.fetch_paged = lambda fs, fields, fid="f3", po=1, limit=600: [dict(x) for x in FAKE_STOCKS]
    em.fetch_indices = lambda: [dict(x) for x in FAKE_INDICES]
    em.fetch_breadth = lambda: dict(FAKE_BREADTH)
    em.fetch_zt_pool = lambda: {"tc": 0, "pool": []}
    em.fetch_zb_pool = lambda: {"tc": 0, "pool": []}
    em.fetch_dt_pool = lambda: {"tc": 0, "pool": []}
    em.fetch_market_amount = lambda: 10000.5
    em.fetch_fflow_daykline = lambda secid, limit=0: list(FFLOW_MAP.get(secid, []))
    em.fetch_kline_hist = lambda code, limit=45: [dict(x) for x in KLINE_MAP.get(str(code), [])]
    em.fetch_board_kline = lambda code, limit=45: [dict(x) for x in KLINE_MAP.get(str(code), [])]
    import stockreview.flow3 as flow3_mod
    import stockreview.trend3 as trend3_mod
    flow3_mod.datetime = FakeDT
    trend3_mod.datetime = FakeDT


# ---------- 断言 ----------

def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("  ✓", msg)


def main():
    print("== 纯函数单元测试 ==")
    rows = analysis.parse_fflow_rows(FFLOW_MAP["1.600001"])
    check(rows[0]["main_flow"] == 1.0e8 and rows[-1]["main_flow"] == 5.0e8 and rows[0]["date"] == "2026-08-10",
          "parse_fflow_rows 解析正确")
    check(analysis.trailing_inflow_days(rows) == 5, "trailing_inflow_days = 5")
    check(analysis.trailing_outflow_days(analysis.parse_fflow_rows(FFLOW_MAP["90.BK02"])) == 3,
          "trailing_outflow_days = 3")
    check(analysis.streak_flow_sum(rows, 2) == 9.0e8, "streak_flow_sum 正确")
    hist = KLINE_MAP["600001"]
    check(analysis.yang_streak(hist) == 4, "yang_streak = 4（连续阳线+温和放量）")
    check(analysis.yang_streak(KLINE_MAP["600002"]) == 2, "yang_streak = 2（不满足3日）")
    check(analysis.is_uptrend(hist) is True, "is_uptrend = True（站上MA20且MA20走高）")
    down_hist = [dict(x) for x in hist]  # 深拷贝，避免污染 KLINE_MAP 共享数据
    down_hist[-1]["close"] = down_hist[-1]["close"] * 0.8  # 收盘跌破 MA20
    check(analysis.is_uptrend(down_hist) is False, "is_uptrend = False（跌破MA20）")
    check(analysis.pct_5d(hist) is not None, "pct_5d 可计算")

    print("== flow3 离线扫描 ==")
    patch_fetchers()
    flow3 = fetch_flow3_scan()
    inflow_boards = {x["name"]: x for x in flow3["inflow_boards"]}
    outflow_boards = {x["name"]: x for x in flow3["outflow_boards"]}
    inflow_stocks = {x["name"]: x for x in flow3["inflow_stocks"]}
    check(inflow_boards.get("半导体", {}).get("days") == 4, "板块【半导体】连续净流入 4 日")
    check(inflow_boards.get("人工智能", {}).get("days") == 3, "板块【人工智能】连续净流入 3 日")
    check("食品" not in inflow_boards and "食品" not in outflow_boards, "板块【食品】无连续3日，不入选")
    check(outflow_boards.get("银行", {}).get("days") == 3, "板块【银行】连续净流出 3 日")
    check(inflow_stocks.get("甲科技", {}).get("days") == 5, "个股【甲科技】连续净流入 5 日")
    check("乙软件" not in inflow_stocks and "丙数据" not in inflow_stocks, "乙/丙不满足条件")
    check(flow3["scanned_boards"] == 4 and flow3["scanned_stocks"] == 2, "扫描计数正确")

    print("== trend3 离线扫描 ==")
    trend3 = fetch_trend3_scan()
    stocks = {x["name"]: x for x in trend3["stocks"]}
    boards = {x["name"]: x for x in trend3["boards"]}
    check(stocks.get("甲科技", {}).get("days") == 4, "个股【甲科技】连续放量阳线 4 日")
    check("乙软件" not in stocks, "个股【乙软件】仅2日，不入选")
    check(boards.get("半导体", {}).get("days") == 3, "板块【半导体】连续放量阳线 3 日")
    check("人工智能" not in boards, "板块【人工智能】仅2日，不入选")
    check(trend3["scanned_stocks"] == 3 and trend3["scanned_boards"] == 3, "trend3 预筛计数正确")

    print("== 生成 schema fixture ==")
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from compare_schema import schema_map
    fixture_dir = os.path.join(ROOT, "tests", "fixtures")
    for name, data in (("flow3", flow3), ("trend3", trend3)):
        sm = schema_map(data)
        with open(os.path.join(fixture_dir, f"baseline_{name}.json"), "w", encoding="utf-8") as f:
            json.dump(sm, f, ensure_ascii=False, indent=1)
        print(f"  ✓ baseline_{name}.json 已生成（{len(sm)} paths）")

    print("\n策略测试全部通过 ✔")


if __name__ == "__main__":
    main()
