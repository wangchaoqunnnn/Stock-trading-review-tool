# -*- coding: utf-8 -*-
"""新增策略（3日资金 / 放量阳线）的离线验证测试。

1. 纯函数单元测试：资金流解析、连续天数、放量阳线连续天数、上升趋势判断。
2. 扫描函数离线测试：用假数据打桩 em/net 抓取，验证 flow3/trend3 聚合结果符合预期。
3. 生成 flow3/trend3 端点的基线 schema fixture（供 verify_schema.py 做结构回归）。
"""
import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stockreview import analysis, em, net  # noqa: E402
from stockreview.flow3 import fetch_flow3_scan  # noqa: E402
from stockreview.trend3 import fetch_trend3_scan  # noqa: E402


class FakeDT:
    fixed = datetime(2026, 8, 15, 10, 30, 0)

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


def build_kline_sideways(n=45, base=10.0, vol=1_000_000.0, flat_days=25):
    """横盘震荡K线：前期缓涨到位，最后 flat_days 天收盘价恒定（高/低在±1%内波动）。

    横盘段收盘价恒定 → MA20 与 5 日前 MA20 完全相等（满足"走平"），
    且不属于上升趋势（ma20 > ma20_prev5 不成立）。
    """
    rows = []
    close = base
    flat_level = None
    for i in range(n):
        if i < n - flat_days:
            open_ = close
            close = close * 1.004
            volume = vol
        else:
            if flat_level is None:
                flat_level = close
            open_ = flat_level
            close = flat_level
            volume = vol
        rows.append({
            "date": f"2026-08-{i:02d}", "open": round(open_, 2), "close": round(close, 2),
            "high": round(max(open_, close) * 1.01, 2), "low": round(min(open_, close) * 0.99, 2),
            "volume": volume, "amount": volume * close, "pct": round((close / open_ - 1) * 100, 2),
        })
    return rows


def build_kline_downtrend(n=40, base=10.0, vol=1_000_000.0):
    """下降趋势K线：前期缓涨后连续回落，收盘明显跌破 MA20。"""
    rows = []
    close = base
    for i in range(n):
        if i < n - 12:
            open_ = close
            close = close * 1.004
        else:
            open_ = close
            close = close * 0.98
        volume = vol
        rows.append({
            "date": f"2026-08-{i:02d}", "open": round(open_, 2), "close": round(close, 2),
            "high": round(max(open_, close) * 1.01, 2), "low": round(min(open_, close) * 0.99, 2),
            "volume": volume, "amount": volume * close, "pct": round((close / open_ - 1) * 100, 2),
        })
    return rows


# limit20 用：历史涨停池（按日期）
FAKE_ZT_BY_DATE = {
    "20260813": {"tc": 3, "pool": [
        {"c": "600001", "n": "甲科技", "hybk": "半导体", "lbc": 1},
        {"c": "600002", "n": "乙软件", "hybk": "半导体", "lbc": 0},
        {"c": "600003", "n": "丙数据", "hybk": "通信", "lbc": 0},
    ]},
    "20260814": {"tc": 2, "pool": [
        {"c": "600001", "n": "甲科技", "hybk": "半导体", "lbc": 2},
        {"c": "600004", "n": "丁材料", "hybk": "有色", "lbc": 0},
    ]},
    "20260815": {"tc": 1, "pool": [
        {"c": "600005", "n": "戊能源", "hybk": "电力", "lbc": 0},
    ]},
}

LIMIT20_KLINE_MAP = {
    "600001": KLINE_MAP["600001"],                    # 上升趋势
    "600002": build_kline_sideways(),                 # 横盘震荡
    "600003": build_kline_downtrend(),                # 下降趋势
    "600004": build_kline_sideways(base=8.0),         # 横盘震荡
    "600005": build_kline_sideways(base=12.0),        # 横盘震荡
}


def fake_ex_pool(path, date=None):
    d = FAKE_ZT_BY_DATE.get(date, {"tc": 0, "pool": []})
    return {"tc": d["tc"], "pool": [dict(x) for x in d["pool"]]}


def build_kline_breakout(n=260, hist_high=None, recent_high=9.3, today_high=10.5, base=9.2, vol=1_000_000.0):
    """突破判定K线：前 n-1 天低波动，可指定历史高点/近20日高点/今日高点。"""
    rows = []
    for i in range(n):
        high = base * 1.01
        if hist_high and i == n - 60:
            high = hist_high
        if i >= n - 20:
            high = max(high, recent_high)
        if i == n - 1:
            high = today_high
        rows.append({
            "date": f"2026-08-{i % 28 + 1:02d}", "open": base, "close": base * 0.99,
            "high": high, "low": base * 0.98, "volume": vol, "amount": vol * base, "pct": -1.0,
        })
    return rows


# breakout 用：各股票长K线
BREAKOUT_KLINE_MAP = {
    "600001": build_kline_breakout(hist_high=10.0, recent_high=9.3, today_high=10.5),   # 短期+历史双突破
    "600002": build_kline_breakout(hist_high=12.0, recent_high=9.3, today_high=10.5),   # 仅短期突破
    "600003": build_kline_breakout(hist_high=None, recent_high=10.0, today_high=9.8),   # 不突破
}


# ztpool 用：今日涨停/炸板/跌停池 + 行情补取
FAKE_POOL_ZT = {"tc": 3, "pool": [
    {"c": "600001", "n": "甲科技", "hybk": "半导体", "fbt": 92500, "lbc": 2, "zbc": 0, "fund": 1.0e8, "zdp": 10.0, "amount": 2.0e8},
    {"c": "600002", "n": "乙软件", "hybk": "半导体", "fbt": 93000, "lbc": 1, "zbc": 0, "fund": 5.0e7, "zdp": 10.0, "amount": 1.5e8},
    {"c": "300004", "n": "丙能源", "hybk": "新能源", "fbt": 101000, "lbc": 0, "zbc": 0, "fund": 2.0e7, "zdp": 19.9, "amount": 1.0e8},
]}
FAKE_POOL_ZB = {"tc": 1, "pool": [
    {"c": "000005", "n": "丁银行", "hybk": "银行", "fbt": 94000, "lbc": 0, "zbc": 1, "fund": 3.0e7, "zdp": 8.0, "amount": 8.0e7},
]}
FAKE_POOL_DT = {"tc": 1, "pool": [
    {"c": "601398", "n": "戊保险", "hybk": "保险", "fbt": 0, "lbc": 0, "zbc": 0, "fund": 0.0, "zdp": -9.9, "amount": 5.0e7},
]}
FAKE_SPOT_MAP = {c: {"f5": 1_000_000.0, "f10": 2.5, "f8": 12.0} for c in ("600001", "600002", "300004", "000005", "601398")}

# hot 用：同花顺热股榜假数据（order 排名 / hot_rank_chg 排名变化）
FAKE_HOT_LIST = [
    {"market": 33, "code": "600001", "name": "甲科技", "order": 1, "rate": "1000000", "hot_rank_chg": "0", "rise_and_fall": 5.0,
     "tag": {"concept_tag": ["半导体", "芯片"], "popularity_tag": "首板涨停"}, "analyse_title": "半导体板块活跃"},
    {"market": 33, "code": "600002", "name": "乙软件", "order": 2, "rate": "900000", "hot_rank_chg": "3", "rise_and_fall": 2.0,
     "tag": {"concept_tag": ["软件"]}, "analyse_title": ""},
    {"market": 33, "code": "600003", "name": "丙数据", "order": 3, "rate": "800000", "hot_rank_chg": "28", "rise_and_fall": -1.0,
     "tag": {"concept_tag": ["算力"]}, "analyse_title": "算力概念"},
    {"market": 33, "code": "600004", "name": "丁材料", "order": 4, "rate": "700000", "hot_rank_chg": "-5", "rise_and_fall": 3.5,
     "tag": {}, "analyse_title": ""},
]


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
    em.fetch_kline_hist = lambda code, limit=45, end_date=None: [dict(x) for x in KLINE_MAP.get(str(code), [])]
    em.fetch_board_kline = lambda code, limit=45, end_date=None: [dict(x) for x in KLINE_MAP.get(str(code), [])]
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

    sw_hist = build_kline_sideways()
    dt_hist = build_kline_downtrend()
    check(analysis.is_sideways(sw_hist) is True, "is_sideways = True（横盘震荡）")
    check(analysis.is_sideways(KLINE_MAP["600001"]) is False, "上升趋势K线不是横盘")
    check(analysis.is_sideways(dt_hist) is False, "下降趋势K线不是横盘")
    check(analysis.classify_state(KLINE_MAP["600001"]) == "uptrend", "classify_state -> uptrend")
    check(analysis.classify_state(sw_hist) == "sideways", "classify_state -> sideways")
    check(analysis.classify_state(dt_hist) == "downtrend", "classify_state -> downtrend")

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

    print("== limit20 离线扫描 ==")
    em.fetch_ex_pool = fake_ex_pool
    em.fetch_kline_hist = lambda code, limit=45, end_date=None: [dict(x) for x in LIMIT20_KLINE_MAP.get(str(code), [])]

    def limit20_stocks():
        rows = [dict(x) for x in FAKE_STOCKS]  # 600001/600002/600003
        rows.append(stock_row("600004", "丁材料", 1.0, 5.0e8, 1.1, 1.0e8, industry="有色"))
        rows.append(stock_row("600005", "戊能源", 0.5, 5.0e8, 1.0, 5.0e7, industry="电力"))
        rows.append(stock_row("600006", "己汽车", 0.8, 5.0e8, 1.0, 1.0e8, industry="汽车"))  # 无涨停史
        return rows
    net.fetch_paged = lambda fs, fields, fid="f3", po=1, limit=600: limit20_stocks()
    import stockreview.limit20 as limit20_mod
    limit20_mod.datetime = FakeDT
    d20 = limit20_mod.fetch_limit20_scan()
    up_stocks = {x["name"]: x for x in d20["uptrend_stocks"]}
    sw_stocks = {x["name"]: x for x in d20["sideways_stocks"]}
    check(d20["universe"] == 5, f"20日内封涨停 {d20['universe']} 只（应为5）")
    check(d20["uptrend_count"] == 1 and d20["sideways_count"] == 3, "上升1 / 横盘3 计数正确")
    check(up_stocks.get("甲科技", {}).get("state") == "uptrend" and up_stocks["甲科技"]["days_since"] == 1,
          "甲科技=上升趋势，距涨停1个交易日（0814涨停）")
    check(sw_stocks.get("乙软件", {}).get("state") == "sideways" and sw_stocks["乙软件"]["days_since"] == 2,
          "乙软件=横盘震荡，距涨停2个交易日（0813涨停）")
    check("丙数据" not in up_stocks and "丙数据" not in sw_stocks, "丙数据为下降趋势，不入选")
    check("丁材料" in sw_stocks and "戊能源" in sw_stocks, "丁材料/戊能源=横盘震荡入选")
    check(d20["window_dates"][-1] == "2026-08-15", "统计窗口含当日")

    print("== ztpool 离线扫描 ==")
    em.fetch_zt_pool = lambda: {"tc": FAKE_POOL_ZT["tc"], "pool": [dict(x) for x in FAKE_POOL_ZT["pool"]]}
    em.fetch_zb_pool = lambda: {"tc": FAKE_POOL_ZB["tc"], "pool": [dict(x) for x in FAKE_POOL_ZB["pool"]]}
    em.fetch_dt_pool = lambda: {"tc": FAKE_POOL_DT["tc"], "pool": [dict(x) for x in FAKE_POOL_DT["pool"]]}
    em.fetch_spot_map = lambda codes, fields="f2,f3,f6,f8,f10,f12,f14,f62": {c: dict(FAKE_SPOT_MAP[c]) for c in codes if c in FAKE_SPOT_MAP}
    import stockreview.ztpool as ztpool_mod
    ztpool_mod.datetime = FakeDT
    zp = ztpool_mod.fetch_ztpool_detail()
    check(zp["zt"]["count"] == 3 and zp["zt"]["stocks"][0]["name"] == "甲科技",
          "涨停 3 只且按连板降序（甲科技2板在前）")
    check(zp["zb"]["count"] == 1 and zp["zb"]["stocks"][0]["name"] == "丁银行", "炸板 1 只")
    check(zp["dt"]["count"] == 1 and zp["dt"]["stocks"][0]["name"] == "戊保险", "跌停 1 只")
    check(zp["max_board"]["max_lb"] == 2 and zp["max_board"]["count"] == 1, "最高2板（甲科技）")
    check(zp["jingjia"]["count"] == 1 and zp["jingjia"]["stocks"][0]["name"] == "甲科技",
          "竞价涨停 1 只（首封09:25:00<09:26）")
    r = zp["zt"]["stocks"][0]
    check(r["vol_wan"] == 100 and r["vol_ratio"] == 2.5 and r["amount_yi"] == 2.0 and r["industry"] == "半导体",
          "行字段：量100万手/量比2.5/成交2.0亿/板块半导体")

    print("== hot 离线扫描 ==")
    net.http_get_json = lambda url, headers=None, tries=3: {"data": {"stock_list": [dict(x) for x in FAKE_HOT_LIST]}}
    import stockreview.hot as hot_mod
    hot_mod.datetime = FakeDT
    test_hot_dir = os.path.join(ROOT, ".refactor_tmp", "test_hot")
    os.makedirs(test_hot_dir, exist_ok=True)
    hot_mod.DATA_DIR = test_hot_dir
    hot_mod.SNAPSHOT_FILE = os.path.join(test_hot_dir, "hot_history.json")
    if os.path.exists(hot_mod.SNAPSHOT_FILE):
        os.remove(hot_mod.SNAPSHOT_FILE)
    hot = hot_mod.fetch_hot_scan()
    top = {x["name"]: x for x in hot["top"]["stocks"]}
    rising = {x["name"]: x for x in hot["rising"]["stocks"]}
    check(len(hot["top"]["stocks"]) == 4 and top["甲科技"]["rank"] == 1, "热度TOP 按排名升序（甲科技第1）")
    check(len(hot["rising"]["stocks"]) == 4 and hot["rising"]["stocks"][0]["name"] == "丙数据",
          "热度上升最快 按排名变化降序（丙数据+28居首）")
    check(rising["乙软件"]["rank_chg"] == 3 and rising["乙软件"]["pct"] == 2.0, "行字段：排名变化/涨跌幅")
    check(top["甲科技"]["tags"] == ["半导体", "芯片"] and top["甲科技"]["popularity_tag"] == "首板涨停",
          "概念标签与状态解析正确")
    check(hot["rising3"]["ready"] is False and hot["rising3"]["count"] == 0 and hot["rising3"]["days_available"] == 1,
          "连续3日：首日数据积累中（已积累1天，ready=False）")

    # 场景2：预写昨日+前日快照（FakeDT=2026-08-15 → 昨日08-14/前日08-13）
    yesterday = (FakeDT.fixed - timedelta(days=1)).strftime("%Y-%m-%d")
    before = (FakeDT.fixed - timedelta(days=2)).strftime("%Y-%m-%d")
    history = {
        before: {"600001": {"order": 5, "chg": -1}, "600002": {"order": 6, "chg": 0}, "600003": {"order": 7, "chg": 1}, "600004": {"order": 5, "chg": 1}},
        yesterday: {"600001": {"order": 3, "chg": 2}, "600002": {"order": 4, "chg": 1}, "600003": {"order": 8, "chg": -1}, "600004": {"order": 6, "chg": 1}},
    }
    with open(hot_mod.SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False)
    hot2 = hot_mod.fetch_hot_scan()
    r3 = {x["name"]: x for x in hot2["rising3"]["stocks"]}
    check(hot2["rising3"]["ready"] is True, "连续3日：快照就绪（次日）")
    check("甲科技" in r3 and "乙软件" in r3, "甲/乙连续3日排名上升（1<3<5 / 2<4<6）")
    check("丙数据" not in r3 and "丁材料" not in r3, "丙/丁未连续3日上升（3<8<7 / 4<6<5）")
    check(hot2["rising3"]["count"] == 2, "连续3日命中 2 只")

    print("== breakout 离线扫描 ==")
    em.fetch_long_kline = lambda code, limit=250, end_date=None: [dict(x) for x in BREAKOUT_KLINE_MAP.get(str(code), [])]
    net.fetch_paged = lambda fs, fields, fid="f3", po=1, limit=600: [
        stock_row("600001", "甲科技", 5.0, 5.0e8, 1.8, 2.0e8),
        stock_row("600002", "乙软件", 3.0, 5.0e8, 1.5, 1.5e8),
        stock_row("600003", "丙数据", -1.0, 5.0e8, 1.0, 1.0e8),   # 今日下跌 → 预筛排除
        stock_row("600004", "丁材料", 2.0, 5.0e8, 1.2, 2.5e8),   # 无K线数据 → 跳过
    ]
    import stockreview.breakout as breakout_mod
    breakout_mod.datetime = FakeDT
    bo = breakout_mod.fetch_breakout_scan()
    short_map = {x["name"]: x for x in bo["short"]["stocks"]}
    hist_map = {x["name"]: x for x in bo["hist"]["stocks"]}
    check(bo["scanned"] == 3, f"预筛 3 只（丙下跌排除，丁无K线但计入候选）→ 实际 {bo['scanned']}")
    check("甲科技" in short_map and "乙软件" in short_map and "丙数据" not in short_map and "丁材料" not in short_map,
          "短期突破：甲/乙入选，丙不突破、丁无数据")
    check("甲科技" in hist_map and "乙软件" not in hist_map, "历史突破：仅甲（乙历史高点12.0未突破）")
    check(short_map["甲科技"]["break_pct"] > 0 and short_map["甲科技"]["vol_ratio"] == 1.8,
          "突破幅度/量比字段正确")
    check(bo["short"]["count"] == 2 and bo["hist"]["count"] == 1, "计数正确")

    print("== leaders 离线扫描 ==")
    em.fetch_zt_pool = lambda: {"tc": 3, "pool": [
        {"c": "600001", "n": "甲科技", "hybk": "半导体", "fbt": 93000, "lbc": 4, "zbc": 0, "fund": 3.0e8, "zdp": 10.0, "amount": 2.0e8, "hs": 10.0},
        {"c": "600002", "n": "乙软件", "hybk": "半导体", "fbt": 94000, "lbc": 2, "zbc": 0, "fund": 2.0e8, "zdp": 10.0, "amount": 1.5e8, "hs": 8.0},
        {"c": "600003", "n": "丙能源", "hybk": "新能源", "fbt": 95000, "lbc": 4, "zbc": 0, "fund": 1.0e8, "zdp": 19.9, "amount": 1.0e8, "hs": 15.0},
        {"c": "600004", "n": "丁材料", "hybk": "有色", "fbt": 101000, "lbc": 0, "zbc": 0, "fund": 5.0e7, "zdp": 5.0, "amount": 8.0e7, "hs": 6.0},
    ]}
    em.fetch_hot_rank_list = None  # 由 hot 模块提供，见下
    import stockreview.leaders as leaders_mod
    leaders_mod.fetch_hot_rank_list = hot_mod.fetch_hot_rank_list  # 走真实规范化逻辑（http_get_json 已打桩）
    leaders_mod.datetime = FakeDT
    ld = leaders_mod.fetch_leaders_scan()
    mkt = {x["name"]: x for x in ld["market_leader"]["stocks"]}
    bd = {x["industry"]: x for x in ld["board_leader"]["stocks"]}
    emo = {x["name"]: x for x in ld["emotion_leader"]["stocks"]}
    check(ld["max_lb"] == 4, "最高4板")
    check(set(mkt.keys()) == {"甲科技", "丙能源"} and mkt["甲科技"]["fund_yi"] == 3.0,
          "市场总龙=最高4板两只，按封单降序（甲在前）")
    check(bd.get("半导体", {}).get("name") == "甲科技" and bd["半导体"]["zt_count"] == 2,
          "板块龙头：半导体=甲科技（4板）")
    check(bd.get("新能源", {}).get("name") == "丙能源" and bd.get("有色", {}).get("name") == "丁材料",
          "板块龙头：新能源=丙能源、有色=丁材料")
    check(emo.get("甲科技", {}).get("hot_rank") == 1 and "乙软件" in emo,
          "情绪龙头：连板梯队（甲/乙/丙）且甲人气第1")
    check("丁材料" not in emo, "首板丁材料不进情绪龙头")

    print("== heatmap 离线扫描 ==")
    em.fetch_industry_boards = lambda: em.board_rows([
        {"f12": "BK01", "f14": "半导体", "f3": 3.2, "f6": 1.0e10, "f8": 2.0, "f10": 1.8, "f17": 101.0, "f18": 100.0, "f62": 8.0e8, "f184": 0.5, "f104": 3, "f105": 1, "f128": "甲科技", "f141": 10.0, "f140": "600001"},
        {"f12": "BK02", "f14": "银行", "f3": -1.5, "f6": 5.0e9, "f8": 0.5, "f10": 0.8, "f17": 98.5, "f18": 100.0, "f62": -2.0e8, "f184": 0.1, "f104": 0, "f105": 2, "f128": "银行股", "f141": 0.5, "f140": "601398"},
        {"f12": "BK03", "f14": "电力", "f3": 1.0, "f6": 3.0e9, "f8": 1.0, "f10": 1.1, "f17": 101.0, "f18": 100.0, "f62": 1.0e8, "f184": 0.2, "f104": 1, "f105": 0, "f128": "电力股", "f141": 2.0, "f140": "600011"},
    ])
    import stockreview.heatmap as heatmap_mod
    heatmap_mod.datetime = FakeDT
    hm = heatmap_mod.fetch_heatmap_scan()
    check(hm["total"] == 3 and hm["boards"][0]["name"] == "半导体" and hm["boards"][0]["pct"] == 3.2,
          "热力图：3个板块按涨跌幅降序（半导体第一）")
    check(hm["boards"][-1]["name"] == "银行" and hm["boards"][-1]["pct"] == -1.5, "银行垫底（-1.5%）")

    print("== emotion_history 离线扫描 ==")
    from stockreview.emotion_history import emotion_score, emotion_level

    def fake_ex(date):
        if date == "20260813":
            return {"tc": 30, "pool": [{"c": "600001", "fbt": 93000, "lbc": 3}]}
        return {"tc": 60, "pool": [{"c": "600001", "fbt": 93000, "lbc": 5}, {"c": "600002", "fbt": 92500, "lbc": 4}]}
    em.fetch_ex_pool = lambda path, date=None: fake_ex(date)
    em.fetch_breadth = lambda date=None: {"up": 3000, "down": 1000, "flat": 200}
    import stockreview.emotion_history as eh_mod
    eh_mod._recent_trading_dates = lambda days=15, max_calendar=45, ref_date=None: ["20260813", "20260814", "20260815"]
    eh_mod.datetime = FakeDT
    eh = eh_mod.fetch_emotion_history(days=15)
    rows = {r["date"]: r for r in eh["rows"]}
    check(eh["days"] == 3, "3 个交易日")
    check(rows["2026-08-15"]["zt"] == 60 and rows["2026-08-15"]["max_lb"] == 5 and rows["2026-08-15"]["jingjia"] == 1,
          "当日：涨停60/最高5板/竞价1家")
    check(rows["2026-08-13"]["zt"] == 30, "前日：涨停30")
    s = emotion_score({"tc": 60, "pool": []}, {"tc": 15, "pool": []}, {"tc": 5, "pool": []}, {"up": 3000, "down": 1000})
    check(0 <= s["score"] <= 100, f"情绪分在0-100（{s['score']}）")
    check(emotion_level(80) == "亢奋" and emotion_level(50) == "中性" and emotion_level(10) == "冰点",
          "情绪等级划分正确")

    print("== 生成 schema fixture ==")
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from compare_schema import schema_map
    fixture_dir = os.path.join(ROOT, "tests", "fixtures")
    for name, data in (("flow3", flow3), ("trend3", trend3), ("limit20", d20), ("ztpool", zp), ("hot", hot2), ("breakout", bo), ("leaders", ld), ("heatmap", hm), ("emotion_history", eh)):
        sm = schema_map(data)
        with open(os.path.join(fixture_dir, f"baseline_{name}.json"), "w", encoding="utf-8") as f:
            json.dump(sm, f, ensure_ascii=False, indent=1)
        print(f"  ✓ baseline_{name}.json 已生成（{len(sm)} paths）")

    print("\n策略测试全部通过 ✔")


if __name__ == "__main__":
    main()
