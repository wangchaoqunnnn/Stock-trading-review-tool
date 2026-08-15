# -*- coding: utf-8 -*-
"""等价性测试：用相同的离线假数据分别驱动 git HEAD 的原始 server.py
与重构后的 stockreview 包，断言两者输出完全一致（功能保持不变）。"""
import importlib.util
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 沙箱限制写入系统临时目录，这里在工作区内使用临时目录
TMP = os.path.join(ROOT, ".refactor_tmp")
sys.path.insert(0, ROOT)


# ---------- 固定时钟（保证 as_of / time_phase 确定性） ----------

class FakeDT:
    fixed = datetime(2025, 1, 15, 10, 30, 0)

    @classmethod
    def now(cls):
        return cls.fixed


FIXED_PHASE = {"phase": "早盘资金验证", "window": "9:30-10:00", "tip": "资金持续流入、板块涨停扩散，等第一次回踩不破", "active": True}


# ---------- 离线假数据 ----------

def make_hist(limit_idx, base=10.0, up=0.01, limit_pct=10.0, today_pull=0.005, vol_scale=0.5, n=45):
    """构造 n 天日K：先缓涨，limit_idx 日涨停，最后一日缩量小幅回踩。"""
    rows = []
    close = base
    for i in range(n):
        pct = up if i != limit_idx else limit_pct / 100.0
        if i == n - 1:
            pct = -today_pull
        close = close * (1 + pct)
        volume = 1_000_000.0
        if i == limit_idx:
            volume = 3_000_000.0
        if i == n - 1:
            volume = 500_000.0
        open_ = close / (1 + pct) if i else close
        high = max(open_, close) * 1.005
        low = min(open_, close) * 0.995
        rows.append({
            "date": f"2025-01-{i + 1:02d}",
            "open": round(open_, 2), "close": round(close, 2),
            "high": round(high, 2), "low": round(low, 2),
            "volume": volume, "amount": volume * close, "pct": round(pct * 100, 2),
        })
    return rows


def make_hist_pullback(base=10.0):
    """涨停回踩命中样例：45 日，倒数第 2 日涨停，最后一日缩量回踩不破。"""
    return make_hist(limit_idx=43, base=base, today_pull=0.003, vol_scale=0.5)


FAKE_INDICES = [
    {"name": "上证指数", "pre_close": 3000.0, "current": 3010.0, "pct": 0.33, "avg_price": 3005.0, "above_avg": True, "vs_avg_pct": 0.17},
    {"name": "深证成指", "pre_close": 10000.0, "current": 10050.0, "pct": 0.50, "avg_price": 10020.0, "above_avg": True, "vs_avg_pct": 0.30},
    {"name": "创业板指", "pre_close": 2000.0, "current": 1980.0, "pct": -1.00, "avg_price": 1990.0, "above_avg": False, "vs_avg_pct": -0.50},
    {"name": "科创50", "pre_close": 900.0, "current": 905.0, "pct": 0.56, "avg_price": 903.0, "above_avg": True, "vs_avg_pct": 0.22},
    {"name": "沪深300", "pre_close": 3500.0, "current": 3490.0, "pct": -0.29, "avg_price": 3495.0, "above_avg": False, "vs_avg_pct": -0.14},
    {"name": "北证50", "pre_close": 1100.0, "current": 1105.0, "pct": 0.45, "avg_price": 1102.0, "above_avg": True, "vs_avg_pct": 0.27},
]

FAKE_BREADTH = {
    "up": 2500, "down": 1800, "flat": 200,
    "distribution": [{"key": "-5", "count": 10}, {"key": "-3", "count": 30}, {"key": "0", "count": 200}, {"key": "2", "count": 500}, {"key": "5", "count": 50}],
    "date": "20250115",
}

FAKE_ZT = {"tc": 3, "pool": [
    {"c": "600001", "n": "甲科技", "hybk": "半导体", "fbt": 93000, "lbc": 2, "fund": 1.0e8, "zdp": 10.0, "amount": 2.0e8, "hs": 12.0, "lbt": "", "zbc": 0},
    {"c": "000003", "n": "乙软件", "hybk": "半导体", "fbt": 95000, "lbc": 1, "fund": 5.0e7, "zdp": 10.0, "amount": 1.5e8, "hs": 8.0, "lbt": "", "zbc": 1},
    {"c": "300004", "n": "丙能源", "hybk": "新能源", "fbt": 101000, "lbc": 0, "fund": 2.0e7, "zdp": 19.9, "amount": 1.0e8, "hs": 15.0, "lbt": "", "zbc": 0},
]}
FAKE_ZB = {"tc": 1, "pool": [{"c": "000003", "n": "乙软件", "hybk": "半导体", "fbt": 95000, "lbc": 1, "fund": 5.0e7, "zdp": 9.5, "amount": 1.5e8, "hs": 8.0, "lbt": "", "zbc": 1}]}
FAKE_DT = {"tc": 0, "pool": []}

FAKE_INDUSTRY = [
    {"f12": "BK01", "f14": "半导体", "f3": 3.2, "f6": 1.0e10, "f8": 2.0, "f10": 1.8, "f17": 101.0, "f18": 100.0, "f62": 8.0e8, "f184": 0.5, "f104": 3, "f105": 1, "f128": "甲科技", "f141": 10.0, "f140": "600001"},
    {"f12": "BK02", "f14": "新能源", "f3": 1.5, "f6": 8.0e9, "f8": 1.6, "f10": 1.2, "f17": 101.5, "f18": 100.0, "f62": 3.0e8, "f184": 0.3, "f104": 2, "f105": 1, "f128": "丙能源", "f141": 19.9, "f140": "300004"},
    {"f12": "BK03", "f14": "银行", "f3": -0.5, "f6": 5.0e9, "f8": 0.5, "f10": 0.8, "f17": 99.5, "f18": 100.0, "f62": -1.0e8, "f184": 0.1, "f104": 0, "f105": 2, "f128": "银行股", "f141": 0.5, "f140": "601398"},
]
FAKE_CONCEPT = [
    {"f12": "BK10", "f14": "人工智能", "f3": 4.0, "f6": 1.2e10, "f8": 2.5, "f10": 2.0, "f17": 104.0, "f18": 100.0, "f62": 1.0e9, "f184": 0.6, "f104": 5, "f105": 0, "f128": "甲科技", "f141": 10.0, "f140": "600001"},
]

FAKE_FLOW_IN = [
    {"code": "600001", "name": "甲科技", "pct": 10.0, "flow_yi": 3.5, "amount_yi": 2.0, "turnover": 12.0, "vol_ratio": 2.5, "ratio": 0.8},
    {"code": "000007", "name": "丁新材", "pct": 2.0, "flow_yi": 2.1, "amount_yi": 3.0, "turnover": 8.0, "vol_ratio": 1.8, "ratio": 0.5},
]
FAKE_FLOW_OUT = [
    {"code": "601398", "name": "银行股", "pct": -1.0, "flow_yi": -2.0, "amount_yi": 4.0, "turnover": 0.5, "vol_ratio": 0.8, "ratio": 0.2},
]

FAKE_NEWS = [
    {"time": "2025-01-15 09:30:00", "title": "A股三大指数高开 半导体板块领涨", "summary": "摘要一", "url": "https://example.com/1"},
    {"time": "2025-01-15 09:00:00", "title": "央行开展逆回购操作", "summary": "摘要二", "url": "https://example.com/2"},
]

FAKE_YZT = {
    "date": "20250114", "total": 3, "matched": 2, "avg_pct": 2.1, "up": 2, "down": 0,
    "samples": [{"code": "600001", "name": "甲科技", "pct": 3.0, "lbc": 2}],
}

# 个股扫描候选（触发各类过滤与分类分支）
def stock_row(code, name, pct, turn, vr, amount, high_pct=None, low_pct=None, flow=1.0e8, industry="半导体", speed=1.0):
    prev = 10.0
    high = prev * (1 + (high_pct if high_pct is not None else pct) / 100.0)
    low = prev * (1 + (low_pct if low_pct is not None else min(pct, 0)) / 100.0)
    return {
        "f2": prev * (1 + pct / 100.0), "f3": pct, "f6": amount, "f8": turn, "f10": vr,
        "f12": code, "f14": name, "f15": high, "f16": low, "f17": prev * 1.01, "f18": prev,
        "f22": speed, "f62": flow, "f184": 0.5, "f100": industry,
    }

FAKE_STOCKS = [
    stock_row("600001", "甲科技", 5.0, 10, 2.5, 1.0e9, high_pct=6.0, flow=2.0e8),          # 放量上攻候选
    stock_row("600002", "乙软件", 1.0, 12, 3.0, 1.0e9, high_pct=1.5, flow=-5.0e7),         # 放量滞涨候选
    stock_row("000003", "丙数据", 2.5, 15, 0.7, 1.0e9, high_pct=2.8, flow=5.0e7),           # 缩量上涨候选
    stock_row("300004", "丁能源", -1.0, 8, 0.6, 1.0e9, high_pct=0.5, flow=-2.0e7),          # 缩量回踩候选
    stock_row("000005", "戊材料", -2.0, 18, 2.2, 1.0e9, high_pct=-0.5, flow=-1.0e8),        # 放量下跌候选
    stock_row("600006", "己机械", 6.0, 9, 1.6, 1.0e9, high_pct=9.0, flow=8.0e7),            # 冲高回落候选
    stock_row("600007", "庚低量", 1.0, 10, 1.0, 1.0e9),                                     # 量比过滤（1.0 不满足）
    stock_row("600008", "辛低价", 3.0, 10, 2.0, 1.0e8),                                     # 成交额过滤
    stock_row("600009", "壬低换", 3.0, 3, 2.0, 1.0e9),                                      # 换手过滤
    stock_row("600010", "癸大涨", 9.0, 10, 2.0, 1.0e9),                                     # 涨幅过滤
    stock_row("000011", "子回踩", 0.0, 10, 0.9, 1.0e9, flow=1.0e8, industry="半导体"),       # 回踩扫描候选（带涨停史）
    stock_row("300012", "丑回踩", -3.0, 12, 0.8, 1.0e9, flow=-3.0e7, industry="新能源"),     # 回踩扫描候选
]

FAKE_KLINES = {
    "600001": make_hist(limit_idx=40),
    "600002": make_hist(limit_idx=38, base=8.0),
    "000003": make_hist(limit_idx=41, base=12.0),
    "300004": make_hist(limit_idx=39, base=20.0),
    "000005": make_hist(limit_idx=42, base=15.0),
    "600006": make_hist(limit_idx=37, base=9.0),
    "000011": make_hist_pullback(base=10.0),
    "300012": make_hist_pullback(base=25.0),
}


def fake_watchlist_ticks(stocks):
    for s in stocks:
        s.update({
            "price": 10.5, "avg": 10.0, "above_avg": True, "vs_avg": 5.0,
            "break_high": True, "break_auction_high": False,
            "auction_high": 10.2, "auction_low": 9.8, "recent_low": 10.0,
            "recent_gain": 1.2, "day_high": 10.6, "day_low": 9.7,
        })
    return stocks


def fake_spot_map(codes):
    return {c: {"f10": 2.0, "f8": 12.0, "f62": 5.0e7} for c in codes}


def fake_flow_top(po=1, pz=40):
    return FAKE_FLOW_IN if po == 1 else FAKE_FLOW_OUT


def fake_kline(code):
    return list(FAKE_KLINES.get(code, []))


# ---------- 比较工具 ----------

def normalize(v):
    """NaN 归一化（两边同为 NaN 视为相等）。"""
    try:
        if v != v:
            return "<nan>"
    except Exception:
        pass
    return v


def deep_equal(a, b, path="root"):
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False, f"{path}: keys differ: {sorted(set(a.keys()) ^ set(b.keys()))}"
        for k in a:
            ok, msg = deep_equal(a[k], b[k], f"{path}.{k}")
            if not ok:
                return False, msg
        return True, ""
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False, f"{path}: list length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            ok, msg = deep_equal(x, y, f"{path}[{i}]")
            if not ok:
                return False, msg
        return True, ""
    if isinstance(a, float) and isinstance(b, float):
        if normalize(a) != normalize(b):
            return False, f"{path}: {a!r} != {b!r}"
        return True, ""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a != b:
            return False, f"{path}: {a!r} != {b!r}"
        return True, ""
    if a != b:
        return False, f"{path}: {a!r} != {b!r}"
    return True, ""


def assert_equal(name, a, b):
    ok, msg = deep_equal(a, b)
    if not ok:
        raise AssertionError(f"[{name}] 不一致: {msg}")
    print(f"  ✓ {name} 一致（{type(a).__name__}）")


# ---------- 加载原始实现 ----------

def load_original():
    """从 git HEAD 导出原始 server.py 到工作区临时目录并导入。"""
    os.makedirs(TMP, exist_ok=True)
    orig_path = os.path.join(TMP, "orig_server.py")
    with open(orig_path, "w", encoding="utf-8") as f:
        subprocess.run(
            ["git", "show", "HEAD:server.py"], cwd=ROOT,
            stdout=f, stderr=subprocess.PIPE, check=True,
        )
    spec = importlib.util.spec_from_file_location("orig_server", orig_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["orig_server"] = mod
    spec.loader.exec_module(mod)
    return mod


def patch_original(orig):
    """把原版 server.py 的网络函数替换为离线假数据。"""
    orig.fetch_indices = lambda: [dict(x) for x in FAKE_INDICES]
    orig.fetch_market_amount = lambda: 12000.5
    orig.fetch_breadth = lambda: dict(FAKE_BREADTH)
    orig.fetch_zt_pool = lambda: {"tc": FAKE_ZT["tc"], "pool": [dict(x) for x in FAKE_ZT["pool"]]}
    orig.fetch_zb_pool = lambda: {"tc": FAKE_ZB["tc"], "pool": [dict(x) for x in FAKE_ZB["pool"]]}
    orig.fetch_dt_pool = lambda: {"tc": FAKE_DT["tc"], "pool": [dict(x) for x in FAKE_DT["pool"]]}
    orig.fetch_industry_boards = lambda: orig.board_rows([dict(x) for x in FAKE_INDUSTRY])
    orig.fetch_concept_boards = lambda: orig.board_rows([dict(x) for x in FAKE_CONCEPT])
    orig.fetch_stock_flow_top = fake_flow_top
    orig.fetch_news = lambda: [dict(x) for x in FAKE_NEWS]
    orig.fetch_yesterday_zt_perf = lambda: dict(FAKE_YZT)
    orig.fetch_watchlist_ticks = fake_watchlist_ticks
    orig.fetch_spot_map = fake_spot_map
    orig.fetch_kline_hist = fake_kline
    orig.fetch_paged = lambda fs, fields, fid="f3", po=1, limit=600: [dict(x) for x in FAKE_STOCKS]
    orig.time_phase = lambda: dict(FIXED_PHASE)
    orig.datetime = FakeDT


def patch_new(em, net, realtime, snapshot, volprice, pullback):
    """把重构版各模块的网络函数替换为同一套离线假数据。"""
    em.fetch_indices = lambda: [dict(x) for x in FAKE_INDICES]
    em.fetch_market_amount = lambda: 12000.5
    em.fetch_breadth = lambda: dict(FAKE_BREADTH)
    em.fetch_zt_pool = lambda: {"tc": FAKE_ZT["tc"], "pool": [dict(x) for x in FAKE_ZT["pool"]]}
    em.fetch_zb_pool = lambda: {"tc": FAKE_ZB["tc"], "pool": [dict(x) for x in FAKE_ZB["pool"]]}
    em.fetch_dt_pool = lambda: {"tc": FAKE_DT["tc"], "pool": [dict(x) for x in FAKE_DT["pool"]]}
    em.fetch_industry_boards = lambda: em.board_rows([dict(x) for x in FAKE_INDUSTRY])
    em.fetch_concept_boards = lambda: em.board_rows([dict(x) for x in FAKE_CONCEPT])
    em.fetch_stock_flow_top = fake_flow_top
    em.fetch_news = lambda: [dict(x) for x in FAKE_NEWS]
    em.fetch_yesterday_zt_perf = lambda: dict(FAKE_YZT)
    em.fetch_spot_map = fake_spot_map
    em.fetch_kline_hist = fake_kline
    net.fetch_paged = lambda fs, fields, fid="f3", po=1, limit=600: [dict(x) for x in FAKE_STOCKS]
    realtime.fetch_watchlist_ticks = fake_watchlist_ticks
    realtime.time_phase = lambda: dict(FIXED_PHASE)
    snapshot.datetime = FakeDT
    realtime.datetime = FakeDT
    volprice.datetime = FakeDT
    pullback.datetime = FakeDT


def main():
    print("== 加载原始实现（git HEAD:server.py）==")
    orig = load_original()
    orig_time_phase_real = orig.time_phase  # 保存真实实现，供纯函数对比
    print("== 加载重构实现（stockreview 包）==")
    from stockreview import em, net, realtime, snapshot, volprice, pullback
    from stockreview import analysis as new_analysis

    patch_original(orig)
    patch_new(em, net, realtime, snapshot, volprice, pullback)

    print("\n== 纯函数等价性 ==")
    assert_equal("to_num", [orig.to_num(x) for x in ("1.5", None, "abc", 3, "-")],
                 [new_analysis.to_num(x) for x in ("1.5", None, "abc", 3, "-")])
    # 用固定时钟直接驱动 time_phase 本体
    orig_time_phase_real.__globals__["datetime"] = FakeDT
    new_analysis.time_phase.__globals__["datetime"] = FakeDT
    assert_equal("time_phase(10:30)", orig_time_phase_real(), new_analysis.time_phase())
    class ClockDT:
        @classmethod
        def now(cls):
            return datetime(2025, 1, 15, 14, 20, 0)
    orig_time_phase_real.__globals__["datetime"] = ClockDT
    new_analysis.time_phase.__globals__["datetime"] = ClockDT
    assert_equal("time_phase(14:20)", orig_time_phase_real(), new_analysis.time_phase())
    # 恢复固定时钟（time_phase 的 globals 即模块 globals，会影响到 fetch_snapshot 的 as_of）
    orig_time_phase_real.__globals__["datetime"] = FakeDT
    new_analysis.time_phase.__globals__["datetime"] = FakeDT

    assert_equal("compute_emotion", orig.compute_emotion(FAKE_ZT, FAKE_ZB, FAKE_DT),
                 new_analysis.compute_emotion(FAKE_ZT, FAKE_ZB, FAKE_DT))
    assert_equal("zt_summary", orig.zt_summary(FAKE_ZT), new_analysis.zt_summary(FAKE_ZT))
    assert_equal("board_rows", orig.board_rows(FAKE_INDUSTRY), em.board_rows(FAKE_INDUSTRY))
    assert_equal("clist_url", orig.clist_url("m:1+t:2", "f2,f3", fid="f62", po=0, pn=2, pz=50),
                 net.clist_url("m:1+t:2", "f2,f3", fid="f62", po=0, pn=2, pz=50))

    # build_signals / build_watchlist 上下文
    emotion = new_analysis.compute_emotion(FAKE_ZT, FAKE_ZB, FAKE_DT)
    sectors = {
        "industry_top_pct": [dict(x) for x in FAKE_INDUSTRY],
        "industry_top_flow": [dict(x) for x in FAKE_INDUSTRY],
        "concept_top_pct": [dict(x) for x in FAKE_CONCEPT],
        "concept_top_flow": [dict(x) for x in FAKE_CONCEPT],
    }
    flows = {"inflow": [dict(x) for x in FAKE_FLOW_IN], "outflow": [dict(x) for x in FAKE_FLOW_OUT]}
    ctx = {
        "indices": [dict(x) for x in FAKE_INDICES], "amount": 12000.5, "breadth": dict(FAKE_BREADTH),
        "emotion": emotion, "sectors": sectors, "zt_pool_raw": [dict(x) for x in FAKE_ZT["pool"]],
        "flows": flows, "news": [dict(x) for x in FAKE_NEWS],
    }
    assert_equal("build_signals", orig.build_signals(ctx), new_analysis.build_signals(ctx))
    assert_equal("build_watchlist", orig.build_watchlist(ctx), new_analysis.build_watchlist(ctx))

    # 量价分类 / 回踩评分（重构中提取的纯函数，用样例数据回归验证）
    from stockreview.analysis import categorize_volprice, evaluate_pullback, build_hot_sectors
    cand = [
        {"code": "600001", "vol_ratio": 2.5, "pct": 5.0, "main_flow": 2.0, "board_flow": 8.0,
         "break_high10": True, "break_high20": False, "high_pct": 6.0, "hist_vol_ratio": 1.8, "close": 10.5, "ma20": 10.0, "above_ma20": True},
        {"code": "600002", "vol_ratio": 3.0, "pct": 1.0, "main_flow": -0.5, "board_flow": 8.0,
         "break_high10": False, "break_high20": False, "high_pct": 1.5, "hist_vol_ratio": 2.0, "close": 8.1, "ma20": 8.0, "above_ma20": True},
        {"code": "000003", "vol_ratio": 0.7, "pct": 2.5, "main_flow": 0.5, "board_flow": 8.0,
         "break_high10": True, "break_high20": True, "high_pct": 2.8, "hist_vol_ratio": 0.6, "close": 12.3, "ma20": 12.0, "above_ma20": True},
    ]
    cand_copies = [dict(x) for x in cand]
    cats = categorize_volprice(cand_copies)
    assert cats["放量上攻"] and cats["放量滞涨"] and cats["缩量上涨"], "量价分类分支未全部命中"
    assert "放量上攻" in cand_copies[0]["tags"] and "放量滞涨" in cand_copies[1]["tags"] and "缩量上涨" in cand_copies[2]["tags"]
    print("  ✓ categorize_volprice 各分支命中")

    hot_set, _ = build_hot_sectors(em.board_rows([dict(x) for x in FAKE_INDUSTRY]), FAKE_ZT["pool"])
    assert "半导体" in hot_set and "银行" not in hot_set, "热点板块集合异常"
    print("  ✓ build_hot_sectors 命中")
    pb_cand = {"code": "000011", "name": "子回踩", "pct": 0.0, "speed": 0.5, "vol_ratio": 0.9,
               "turnover": 10.0, "amount_yi": 10.0, "main_flow": 1.0, "industry": "半导体"}
    board_flow_map = {"半导体": 8.0, "新能源": 3.0, "银行": -1.0}
    hit = evaluate_pullback(pb_cand, FAKE_KLINES["000011"], hot_set, board_flow_map)
    assert hit is not None and hit["hot"] and hit["score"] > 0, f"回踩样例未命中: {hit}"
    miss = evaluate_pullback(pb_cand, FAKE_KLINES["000011"], {"新能源"}, board_flow_map)
    assert miss is not None, "回踩样例（非热点）不应被过滤（热板块判定在 industry 名）"
    print("  ✓ evaluate_pullback 命中与评分")

    print("\n== 完整聚合等价性（离线假数据） ==")
    assert_equal("fetch_snapshot", orig.fetch_snapshot(), snapshot.fetch_snapshot())
    assert_equal("fetch_realtime(第1次)", orig.fetch_realtime(), realtime.fetch_realtime())
    assert_equal("fetch_realtime(第2次/环比)", orig.fetch_realtime(), realtime.fetch_realtime())
    assert_equal("fetch_volume_price_scan", orig.fetch_volume_price_scan(), volprice.fetch_volume_price_scan())
    assert_equal("fetch_pullback_scan", orig.fetch_pullback_scan(), pullback.fetch_pullback_scan())

    print("\n全部等价性断言通过 ✔")


if __name__ == "__main__":
    main()
