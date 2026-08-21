# -*- coding: utf-8 -*-
"""交易策略模块：可执行交易系统 + 基于信号的实时股票池。

交易系统基于本站既有策略模块（支撑位有效/涨停回踩/放量阳线等），
并用历史日K做过真实回测（scripts/backtest_support.py 与
scripts/backtest_strategies.py），回测数据如实呈现：

- 系统1「缩量回踩支撑+放量阳线确认」：近2年×300样本，3日胜率78.0%（423信号）
- 系统2「涨停缩量回踩均线」：近2年×200样本，3日胜率53.0%、5日均收+2.22%（3292信号）
- 系统3「连续放量阳线趋势跟随」：回测3日胜率50.0%，接近随机，不采用（如实说明）

股票池 = 对应策略模块的实时扫描信号（加入时间=信号确认日、看多理由=信号描述、
所属板块=个股行业），全部真实可溯源。

⚠️ 回测基于历史数据，不代表未来收益；本页所有内容仅为策略研究，
不构成任何投资建议。股市有风险，投资需谨慎。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .pullback import fetch_pullback_scan
from .support_valid import fetch_support_valid_scan
from .utils import to_num

RISK_TEXT = "本文仅为策略研究与行情复盘参考，不构成任何投资建议。回测基于历史数据，不代表未来收益。市场有风险，投资需谨慎。"

TRADING_SYSTEMS = [
    {
        "id": "sys1",
        "name": "缩量回踩支撑 + 放量阳线确认",
        "style": "低吸反转 · 高胜率（回测验证）",
        "summary": "在近60日低点支撑附近，等待缩量回踩 + 次日放量阳线确认后介入，"
                   "是本站唯一经过回测验证的高胜率买点（3日胜率78%），适合稳健型散户。",
        "entry": [
            "支撑位：近60日最低价（箱体下沿/前低）。",
            "信号日：盘中最低触及支撑（≤支撑×1.02）且收盘站稳（≥支撑×0.98）且当日缩量（≤前5日均量×0.9）。",
            "确认日（次日）：放量阳线（收盘>开盘 且 量≥前5日均量）——资金主动接盘信号。",
        ],
        "stop": "收盘跌破支撑（支撑×0.98）止损，单笔亏损控制在 5% 以内。",
        "target": "反弹至压力位（近20日高点）或 3-5 日收益 +8% 分批止盈。",
        "position": "单只 ≤ 总仓 10%，同板块 ≤ 2 只；确认日放量不够则放弃。",
        "backtest": {
            "signals": 423, "win3": "78.0%", "win5": "72.3%", "no_lower": "68.6%",
            "note": "近2年×300只样本（scripts/backtest_support.py）；回测条件：+缩量+次日放量阳线确认",
        },
        "source": "有效支撑",
    },
    {
        "id": "sys2",
        "name": "涨停缩量回踩均线",
        "style": "强势股回调 · 正期望",
        "summary": "20日内涨停的强势股，缩量回踩 MA20（或 5/10 日均线）不破时介入，"
                   "博弈强势股二次启动；回测 5 日均收 +2.22%、胜率约 53%，"
                   "期望为正但胜率中性，需要严格止损与仓位管理。",
        "entry": [
            "前置：20日内出现涨停（10%/20% 板），且处于上升趋势（站上 MA20 且 MA20 走高）。",
            "信号日：缩量回踩（量≤前5日均量×0.9），盘中最低不破支撑（涨停日低点/收盘），收盘站稳均线。",
            "加分项：所属板块为市场热点（板块涨停家数居前）。",
        ],
        "stop": "收盘跌破 MA20（或回踩支撑）止损，单笔亏损控制在 5% 以内。",
        "target": "前高附近或 5 日收益 +5% 分批止盈；破位反抽不过则离场。",
        "position": "单只 ≤ 总仓 8%，整体仓位跟随大盘情绪（情绪评级偏冷/极寒时降半仓）。",
        "backtest": {
            "signals": 3292, "win3": "53.0%", "win5": "53.8%", "avg5": "+2.22%",
            "note": "近2年×200只样本（scripts/backtest_strategies.py）；口径：涨停+缩量回踩MA5；页面股票池口径略宽（回踩均线+缩量，含涨停前置）",
        },
        "source": "涨停回踩",
    },
]

# 回测不达标、不采用的系统（如实说明）
UNUSED_SYSTEMS = [
    {
        "id": "sys3",
        "name": "连续放量阳线趋势跟随",
        "reason": "回测 3 日胜率 50.0%、5 日 48.3%（近2年×200样本，302信号），接近随机，"
                  "追涨胜率不足，不作为独立交易系统采用（仅供趋势观察）。",
    },
]


def _sys1_row(r):
    return {
        "system_id": "sys1",
        "system_name": "缩量回踩支撑 + 放量阳线确认",
        "code": r.get("code"), "name": r.get("name"), "industry": r.get("industry"),
        "add_date": r.get("confirm_date") or r.get("signal_date") or "",
        "add_label": "确认日",
        "reason": (f"缩量回踩支撑(S={r.get('support')})后次日放量阳线确认"
                   f"（缩量比{r.get('shrink_ratio')}·确认量比{r.get('confirm_vol')}）"),
        "params": {
            "support": r.get("support"), "shrink_ratio": r.get("shrink_ratio"),
            "confirm_vol": r.get("confirm_vol"),
        },
    }


def _sys2_row(r):
    return {
        "system_id": "sys2",
        "system_name": "涨停缩量回踩均线",
        "code": r.get("code"), "name": r.get("name"), "industry": r.get("industry"),
        "add_date": r.get("limit_date") or "",
        "add_label": "涨停日",
        "reason": (f"{r.get('limit_date') or ''}涨停({r.get('limit_pct')}%)后缩量回踩"
                   f"MA20({r.get('ma20')})不破（量比{r.get('hist_vol_ratio')}）"
                   f"{'·板块热点' if r.get('hot') else ''}"),
        "params": {
            "ma20": r.get("ma20"), "hist_vol_ratio": r.get("hist_vol_ratio"),
            "days_since": r.get("days_since"), "limit_pct": r.get("limit_pct"),
        },
    }


def fetch_trading(date=None):
    """交易策略主函数：交易系统定义 + 实时信号股票池。"""
    errors = []

    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(safe, "sys1", lambda: fetch_support_valid_scan(date))
        f2 = ex.submit(safe, "sys2", lambda: fetch_pullback_scan(date))
        r1 = f1.result()[1]
        r2 = f2.result()[1]

    pool = []
    if isinstance(r1, dict) and "error" in r1:
        errors.append(r1.get("error"))
    else:
        for s in (r1.get("stocks") or [])[:30]:
            pool.append(_sys1_row(s))
    if isinstance(r2, dict) and "error" in r2:
        errors.append(r2.get("error"))
    else:
        for s in (r2.get("stocks") or [])[:30]:
            pool.append(_sys2_row(s))

    # 去重（同代码多系统命中保留先者）
    seen = set()
    dedup = []
    for row in pool:
        if row["code"] in seen:
            continue
        seen.add(row["code"])
        dedup.append(row)

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "history_date": date,
        "systems": TRADING_SYSTEMS,
        "unused_systems": UNUSED_SYSTEMS,
        "pool": dedup,
        "pool_count": len(dedup),
        "risk": RISK_TEXT,
        "errors": errors,
    }
