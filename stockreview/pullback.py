# -*- coding: utf-8 -*-
"""涨停回踩扫描：20日内涨停 + 上升趋势 + 缩量回踩不破 + 市场热点。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .analysis import build_hot_sectors, compute_emotion, evaluate_pullback
from .config import ALL_A_FS
from .utils import to_num

# 回踩扫描行情字段
SCAN_FIELDS = "f2,f3,f6,f8,f10,f12,f14,f15,f16,f18,f22,f62,f184,f100"


def fetch_pullback_scan():
    """涨停回踩扫描主函数。"""
    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "stocks": ex.submit(safe, "stocks", lambda: net.fetch_paged(ALL_A_FS, SCAN_FIELDS, limit=6000)),
            "industry": ex.submit(safe, "industry", em.fetch_industry_boards),
            "indices": ex.submit(safe, "indices", em.fetch_indices),
            "breadth": ex.submit(safe, "breadth", em.fetch_breadth),
            "zt": ex.submit(safe, "zt", em.fetch_zt_pool),
            "zb": ex.submit(safe, "zb", em.fetch_zb_pool),
            "dt": ex.submit(safe, "dt", em.fetch_dt_pool),
            "amount": ex.submit(safe, "amount", em.fetch_market_amount),
        }
        results = {k: f.result() for k, f in futures.items()}

    errors = [str(v.get("error")) for v in results.values() if isinstance(v, dict) and "error" in v]
    stocks = results["stocks"][1] if not isinstance(results["stocks"], dict) else []
    industry = results["industry"][1] if not isinstance(results["industry"], dict) else []
    indices = results["indices"][1] if not isinstance(results["indices"], dict) else []
    breadth = results["breadth"][1] if not isinstance(results["breadth"], dict) else {"up": 0, "down": 0, "flat": 0}
    zt = results["zt"][1] if not isinstance(results["zt"], dict) else {"tc": 0, "pool": []}
    zb = results["zb"][1] if not isinstance(results["zb"], dict) else {"tc": 0, "pool": []}
    dt = results["dt"][1] if not isinstance(results["dt"], dict) else {"tc": 0, "pool": []}
    amount = results["amount"][1] if not isinstance(results["amount"], dict) else None

    candidates = []
    for r in stocks:
        amount_v = to_num(r.get("f6"))
        pct = to_num(r.get("f3"))
        vr = to_num(r.get("f10"))
        if amount_v < 500000000 or not (-5 <= pct <= 3) or vr > 1.2:
            continue
        candidates.append({
            "code": r.get("f12"),
            "name": r.get("f14"),
            "close": to_num(r.get("f2")),
            "pct": pct,
            "speed": to_num(r.get("f22")),
            "vol_ratio": vr,
            "turnover": to_num(r.get("f8")),
            "amount_yi": round(amount_v / 100000000, 2),
            "main_flow": round(to_num(r.get("f62")) / 100000000, 2),
            "industry": r.get("f100"),
        })
    candidates.sort(key=lambda x: -x["amount_yi"])
    candidates = candidates[:120]

    def enrich(c):
        try:
            c["hist"] = em.fetch_kline_hist(c["code"])
        except Exception:
            c["hist"] = []
        return c
    with ThreadPoolExecutor(max_workers=8) as ex:
        candidates = list(ex.map(enrich, candidates))

    hot_set, _ = build_hot_sectors(industry, zt.get("pool") or [])
    board_flow_map = {b["name"]: b.get("flow_yi", 0) for b in industry}

    results = []
    for c in candidates:
        hist = c.get("hist") or []
        hit = evaluate_pullback(c, hist, hot_set, board_flow_map)
        if hit is not None:
            results.append(hit)
    results.sort(key=lambda x: -x["score"])
    emotion = compute_emotion(zt, zb, dt)
    hot_boards = sorted(industry, key=lambda x: -(x.get("flow_yi") or 0))[:10]
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": indices, "breadth": breadth, "emotion": emotion, "amount_yi": amount,
        },
        "hot_boards": hot_boards,
        "scanned": len(candidates), "matched": len(results), "stocks": results,
        "errors": errors,
    }
