# -*- coding: utf-8 -*-
"""每日复盘快照聚合：并行抓取各数据源并组装 /api/snapshot 响应。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em
from .analysis import build_signals, build_watchlist, compute_emotion, zt_summary


def fetch_snapshot():
    """每日复盘快照主函数。"""
    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

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
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "indices": indices,
        "amount_yi": amount,
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
