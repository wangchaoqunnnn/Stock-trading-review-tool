# -*- coding: utf-8 -*-
"""每日复盘快照聚合：并行抓取各数据源并组装 /api/snapshot 响应。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em
from .analysis import build_signals, build_watchlist, compute_emotion, zt_summary


def _prev_amount_at(now_str):
    """前一交易日当前时刻的两市累计成交额（亿）。

    now_str: "YYYY-MM-DD HH:MM"。使用指数分时（trends2 ndays=2）的
    每分钟成交额，取昨日(前一交易日)截至当前时刻的累计。数据源不可达
    （push2his 挂起）或开盘前返回 None。
    """
    day, hm = now_str[:10], now_str[11:16]
    if hm < "09:30":
        return None
    total = 0.0
    for secid in ("1.000001", "0.399001"):
        days = em.fetch_amount_minutes(secid, ndays=2)
        dates = sorted(d for d in days if d < day)
        if not dates:
            return None
        y = dates[-1]
        acc = 0.0
        for tm, amt in days[y]:
            acc += amt
            if tm >= hm:
                break
        total += acc
    return round(total / 100000000, 2)


def fetch_snapshot(date=None):
    """每日复盘快照主函数。date 非空时为历史回放。

    历史模式：涨停/炸板/跌停池按日期（push2ex 支持）；指数与板块涨跌幅用
    K线重构；涨跌家数/主力资金/快讯为实时数据源，历史模式下不可得。
    """
    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    if date:
        return _fetch_snapshot_history(date, safe)

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "indices": ex.submit(safe, "indices", em.fetch_indices),
            "amount": ex.submit(safe, "amount", em.fetch_market_amount),
            "breadth": ex.submit(safe, "breadth", em.fetch_breadth),
            "zt": ex.submit(safe, "zt", em.fetch_zt_pool),
            "zb": ex.submit(safe, "zb", em.fetch_zb_pool),
            "dt": ex.submit(safe, "dt", em.fetch_dt_pool),
            "industry": ex.submit(safe, "industry", em.fetch_industry_boards),
            "concept": ex.submit(safe, "concept", em.fetch_concept_boards),
            "inflow": ex.submit(safe, "inflow", lambda: em.fetch_stock_flow_top(po=1)),
            "outflow": ex.submit(safe, "outflow", lambda: em.fetch_stock_flow_top(po=0)),
            "news": ex.submit(safe, "news", em.fetch_news),
        }
        results = {k: f.result() for k, f in futures.items()}

    errors = [str(v.get("error")) for k, v in results.items() if isinstance(v, dict) and "error" in v]
    indices = results["indices"][1] if not isinstance(results["indices"], dict) else []
    amount = results["amount"][1] if not isinstance(results["amount"], dict) else None
    breadth = results["breadth"][1] if not isinstance(results["breadth"], dict) else {"up": 0, "down": 0, "flat": 0, "distribution": []}
    zt = results["zt"][1] if not isinstance(results["zt"], dict) else {"tc": 0, "pool": []}
    zb = results["zb"][1] if not isinstance(results["zb"], dict) else {"tc": 0, "pool": []}
    dt = results["dt"][1] if not isinstance(results["dt"], dict) else {"tc": 0, "pool": []}
    industry = results["industry"][1] if not isinstance(results["industry"], dict) else []
    concept = results["concept"][1] if not isinstance(results["concept"], dict) else []
    inflow = results["inflow"][1] if not isinstance(results["inflow"], dict) else []
    outflow = results["outflow"][1] if not isinstance(results["outflow"], dict) else []
    news = results["news"][1] if not isinstance(results["news"], dict) else []

    industry_pct = sorted([x for x in industry if x.get("pct") == x.get("pct")], key=lambda x: -x["pct"])[:15]
    industry_flow = sorted([x for x in industry if x.get("flow_yi") == x.get("flow_yi")], key=lambda x: -x["flow_yi"])[:15]
    concept_pct = sorted([x for x in concept if x.get("pct") == x.get("pct")], key=lambda x: -x["pct"])[:15]
    concept_flow = sorted([x for x in concept if x.get("flow_yi") == x.get("flow_yi")], key=lambda x: -x["flow_yi"])[:15]

    emotion = compute_emotion(zt, zb, dt)
    zts = zt_summary(zt)
    sectors = {
        "industry_top_pct": industry_pct,
        "industry_top_flow": industry_flow,
        "concept_top_pct": concept_pct,
        "concept_top_flow": concept_flow,
    }
    flows = {"inflow": inflow, "outflow": outflow}
    ctx = {
        "indices": indices,
        "amount": amount,
        "breadth": breadth,
        "emotion": emotion,
        "sectors": sectors,
        "zt_pool_raw": zt["pool"],
        "flows": flows,
        "news": news,
    }
    # 当前放量额：与前一日当前时刻成交额对比（盘中实时口径）
    amount_prev = _prev_amount_at(datetime.now().strftime("%Y-%m-%d %H:%M"))
    if amount is not None and amount_prev:
        amount_diff = round(amount - amount_prev, 2)
        amount_diff_pct = round((amount / amount_prev - 1) * 100, 2)
    else:
        amount_diff = None
        amount_diff_pct = None
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "indices": indices,
        "amount_yi": amount,
        "amount_prev_yi": amount_prev,
        "amount_diff_yi": amount_diff,
        "amount_diff_pct": amount_diff_pct,
        "breadth": breadth,
        "emotion": emotion,
        "zt_summary": zts,
        "sectors": sectors,
        "flows": flows,
        "watchlist": build_watchlist(ctx),
        "signals": build_signals(ctx),
        "news": news,
        "errors": errors,
    }


def _fetch_snapshot_history(date, safe):
    """历史回放模式：涨停池按日期 + 指数/板块K线重构，其余实时数据源标注不可得。"""
    ds = date.replace("-", "")
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "zt": ex.submit(safe, "zt", lambda: em.fetch_ex_pool("getTopicZTPool", date=ds)),
            "zb": ex.submit(safe, "zb", lambda: em.fetch_ex_pool("getTopicZBPool", date=ds)),
            "dt": ex.submit(safe, "dt", lambda: em.fetch_ex_pool("getTopicDTPool", date=ds)),
            "industry": ex.submit(safe, "industry", em.fetch_industry_boards),
            "concept": ex.submit(safe, "concept", em.fetch_concept_boards),
        }
        results = {k: f.result() for k, f in futures.items()}

    errors = [f"历史回放({date})：涨跌家数/主力资金/快讯为实时数据源，历史模式下不可得"]
    for k, v in results.items():
        if isinstance(v, dict) and "error" in v:
            errors.append(v["error"])

    zt = results["zt"][1] if not isinstance(results["zt"], dict) else {"tc": 0, "pool": []}
    zb = results["zb"][1] if not isinstance(results["zb"], dict) else {"tc": 0, "pool": []}
    dt = results["dt"][1] if not isinstance(results["dt"], dict) else {"tc": 0, "pool": []}

    # 指数：K线重构（pct 取该日期，pre_close 用前一根收盘，分时均价不可得）
    indices = []
    for name, secid in em.INDICES:
        try:
            hist = em.fetch_index_kline(secid, limit=10, end_date=date)
            if not hist:
                continue
            last = hist[-1]
            prev_close = hist[-2]["close"] if len(hist) >= 2 else last["open"]
            indices.append({
                "name": name, "pre_close": prev_close, "current": last["close"],
                "pct": last.get("pct") or round((last["close"] / prev_close - 1) * 100, 2),
                "avg_price": None, "above_avg": None, "vs_avg_pct": None,
            })
        except Exception:
            continue

    # 板块：K线重构涨跌幅（主力/成交额不可得置 0）
    def board_hist(code, name):
        try:
            hist = em.fetch_board_kline(code, limit=5, end_date=date)
            pct = hist[-1].get("pct") if hist else None
            if pct is None or pct != pct:
                return None
            return {"code": code, "name": name, "pct": round(float(pct), 2),
                    "flow_yi": 0.0, "amount_yi": 0.0, "leader": ""}
        except Exception:
            return None
    industry = results["industry"][1] if not isinstance(results["industry"], dict) else []
    concept = results["concept"][1] if not isinstance(results["concept"], dict) else []
    with ThreadPoolExecutor(max_workers=12) as ex:
        industry_rows = [x for x in ex.map(lambda b: board_hist(b.get("code"), b.get("name")), industry) if x]
        concept_rows = [x for x in ex.map(lambda b: board_hist(b.get("code"), b.get("name")), concept) if x]
    industry_pct = sorted(industry_rows, key=lambda x: -x["pct"])[:15]
    industry_flow = sorted(industry_rows, key=lambda x: -x["flow_yi"])[:15]
    concept_pct = sorted(concept_rows, key=lambda x: -x["pct"])[:15]
    concept_flow = sorted(concept_rows, key=lambda x: -x["flow_yi"])[:15]

    emotion = compute_emotion(zt, zb, dt)
    zts = zt_summary(zt)
    sectors = {
        "industry_top_pct": industry_pct,
        "industry_top_flow": industry_flow,
        "concept_top_pct": concept_pct,
        "concept_top_flow": concept_flow,
    }
    flows = {"inflow": [], "outflow": []}
    ctx = {
        "indices": indices,
        "amount": None,
        "breadth": {"up": 0, "down": 0, "flat": 0, "distribution": [], "date": ds},
        "emotion": emotion,
        "sectors": sectors,
        "zt_pool_raw": zt["pool"],
        "flows": flows,
        "news": [],
    }
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "history_date": date,
        "indices": indices,
        "amount_yi": None,
        "amount_prev_yi": None,
        "amount_diff_yi": None,
        "amount_diff_pct": None,
        "breadth": ctx["breadth"],
        "emotion": emotion,
        "zt_summary": zts,
        "sectors": sectors,
        "flows": flows,
        "watchlist": build_watchlist(ctx),
        "signals": build_signals(ctx),
        "news": [],
        "errors": errors,
    }
