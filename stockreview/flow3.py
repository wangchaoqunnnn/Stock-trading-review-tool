# -*- coding: utf-8 -*-
"""3日以上资金流策略：主力资金连续净流入/流出达到 3 日及以上的板块与个股。

- 板块：全部行业 + 概念板块，逐板块拉取主力资金流历史，统计连续净流入/流出天数。
- 个股：全A按当日主力净流入预筛（连续净流入的必要条件），再逐个核对资金流历史。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .analysis import (
    MIN_STREAK_DAYS,
    parse_fflow_rows,
    streak_flow_sum,
    trailing_inflow_days,
    trailing_outflow_days,
)
from .config import ALL_A_FS
from .market import fetch_market_context
from .utils import to_num

# 全A扫描行情字段（含今日主力净流入 f62）
SCAN_FIELDS = "f2,f3,f6,f8,f10,f12,f14,f17,f18,f22,f62,f184,f100"

# 个股资金流历史核对上限（按今日净流入排序取前 N）
STOCK_CHECK_LIMIT = 500


def _safe(name, fn):
    try:
        return name, fn()
    except Exception as exc:
        return name, {"error": f"{type(exc).__name__}: {exc}"}


def _fflow_rows(secid, date=None):
    """抓取资金流历史并按 date 截取（date 非空时为历史回放）。"""
    rows = parse_fflow_rows(em.fetch_fflow_daykline(secid))
    if date:
        rows = [r for r in rows if r["date"] <= date]
    return rows


def _board_flow(code, name, pct, flow_yi, amount_yi, date=None):
    """单个板块的资金流历史核对，返回命中结果 dict 或 None。"""
    rows = _fflow_rows("90." + code, date)
    if len(rows) < 3:
        return None
    inflow_days = trailing_inflow_days(rows)
    outflow_days = trailing_outflow_days(rows)
    today_flow_yi = round(rows[-1]["main_flow"] / 100000000, 2)
    out = {
        "code": code, "name": name,
        "pct": pct,
        "flow_yi": flow_yi,
        "amount_yi": amount_yi,
        "today_flow_yi": today_flow_yi,
    }
    if inflow_days >= MIN_STREAK_DAYS:
        return {**out, "side": "in", "days": inflow_days,
                "streak_flow_yi": round(streak_flow_sum(rows, inflow_days) / 100000000, 2)}
    if outflow_days >= MIN_STREAK_DAYS:
        return {**out, "side": "out", "days": outflow_days,
                "streak_flow_yi": round(streak_flow_sum(rows, outflow_days) / 100000000, 2)}
    return None


def _stock_flow(row, date=None):
    """单只个股的资金流历史核对（仅净流入方向），命中返回结果 dict。"""
    code = row.get("f12")
    if not code:
        return None
    secid = ("1." if str(code).startswith("6") else "0.") + str(code)
    rows = _fflow_rows(secid, date)
    if len(rows) < 3:
        return None
    days = trailing_inflow_days(rows)
    if days < MIN_STREAK_DAYS:
        return None
    return {
        "code": str(code),
        "name": row.get("f14"),
        "pct": to_num(row.get("f3")),
        "price": to_num(row.get("f2")),
        "flow_yi": round(to_num(row.get("f62")) / 100000000, 2),
        "amount_yi": round(to_num(row.get("f6")) / 100000000, 2),
        "turnover": to_num(row.get("f8")),
        "vol_ratio": to_num(row.get("f10")),
        "industry": row.get("f100"),
        "days": days,
        "streak_flow_yi": round(streak_flow_sum(rows, days) / 100000000, 2),
    }


def fetch_flow3_scan(date=None):
    """3日以上资金流扫描主函数。date 非空时为历史回放（资金流历史截至该日期）。"""
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "industry": ex.submit(_safe, "industry", em.fetch_industry_boards),
            "concept": ex.submit(_safe, "concept", em.fetch_concept_boards),
            "stocks": ex.submit(_safe, "stocks", lambda: net.fetch_paged(ALL_A_FS, SCAN_FIELDS, limit=6000)),
        }
        results = {k: f.result() for k, f in futures.items()}
        context = ex.submit(fetch_market_context).result()

    errors = list(context["errors"])
    if date:
        errors.append(f"历史回放({date})：今日主力净流入为实时字段，资金流历史按该日期截取")
    industry = results["industry"][1] if not isinstance(results["industry"], dict) else []
    concept = results["concept"][1] if not isinstance(results["concept"], dict) else []
    stocks = results["stocks"][1] if not isinstance(results["stocks"], dict) else []
    for k in ("industry", "concept", "stocks"):
        v = results[k]
        if isinstance(v, dict) and "error" in v:
            errors.append(v["error"])

    # ---- 板块 ----
    boards = industry + concept
    def check_board(b):
        return _board_flow(b.get("code"), b.get("name"), b.get("pct"), b.get("flow_yi"), b.get("amount_yi"), date)
    with ThreadPoolExecutor(max_workers=12) as ex:
        board_results = list(ex.map(check_board, boards))
    board_hits = [x for x in board_results if x is not None]
    inflow_boards = sorted([x for x in board_hits if x["side"] == "in"],
                           key=lambda x: (-x["days"], -x["streak_flow_yi"]))
    outflow_boards = sorted([x for x in board_hits if x["side"] == "out"],
                            key=lambda x: (-x["days"], -x["streak_flow_yi"]))

    # ---- 个股 ----
    stock_candidates = [r for r in stocks if to_num(r.get("f62")) > 0]
    stock_candidates.sort(key=lambda r: -to_num(r.get("f62")))
    stock_candidates = stock_candidates[:STOCK_CHECK_LIMIT]
    with ThreadPoolExecutor(max_workers=16) as ex:
        stock_hits = list(ex.map(lambda r: _stock_flow(r, date), stock_candidates))
    inflow_stocks = sorted([x for x in stock_hits if x is not None],
                           key=lambda x: (-x["days"], -x["streak_flow_yi"]))[:120]

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "scanned_boards": len(boards),
        "inflow_boards": inflow_boards,
        "outflow_boards": outflow_boards,
        "scanned_stocks": len(stock_candidates),
        "inflow_stocks": inflow_stocks,
        "errors": errors,
    }
