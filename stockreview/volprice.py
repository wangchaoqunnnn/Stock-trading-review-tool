# -*- coding: utf-8 -*-
"""量价异动扫描：全A按"放量上攻/放量滞涨/冲高回落/缩量上涨/放量下跌/缩量回踩"分类。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .analysis import VOLPRICE_CATEGORIES, categorize_volprice, compute_emotion
from .config import ALL_A_FS
from .utils import to_num

# 全A扫描行情字段
SCAN_FIELDS = "f2,f3,f6,f8,f10,f12,f14,f15,f16,f17,f18,f22,f62,f184,f100"


def fetch_volume_price_scan():
    """量价异动扫描主函数。"""
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
        turn = to_num(r.get("f8"))
        vr = to_num(r.get("f10"))
        pct = to_num(r.get("f3"))
        if amount_v < 500000000 or not (5 <= turn <= 20):
            continue
        if not (vr >= 1.5 or vr <= 0.9):
            continue
        if not (-7 <= pct <= 7):
            continue
        high = to_num(r.get("f15"))
        low = to_num(r.get("f16"))
        prev_close = to_num(r.get("f18")) or 0
        candidates.append({
            "code": r.get("f12"),
            "name": r.get("f14"),
            "close": to_num(r.get("f2")),
            "pct": pct,
            "speed": to_num(r.get("f22")),
            "vol_ratio": vr,
            "turnover": turn,
            "amount_yi": round(amount_v / 100000000, 2),
            "main_flow": round(to_num(r.get("f62")) / 100000000, 2),
            "industry": r.get("f100"),
            "high_pct": round((high / prev_close - 1) * 100, 2) if prev_close else pct,
            "low_pct": round((low / prev_close - 1) * 100, 2) if prev_close else pct,
        })
    big = sorted([c for c in candidates if c["vol_ratio"] >= 1.5], key=lambda x: -x["vol_ratio"])[:30]
    small = sorted([c for c in candidates if c["vol_ratio"] <= 0.9], key=lambda x: x["vol_ratio"])[:20]
    candidates = (big + small)[:150]

    def enrich(c):
        try:
            hist = em.fetch_kline_hist(c["code"])
        except Exception:
            hist = []
        if len(hist) >= 22:
            closes = [h["close"] for h in hist]
            vols = [h["volume"] for h in hist]
            highs = [h["high"] for h in hist]
            amounts = [h["amount"] for h in hist]
            today = hist[-1]
            prev5 = vols[-6:-1]
            prev5_avg = sum(prev5) / len(prev5) if prev5 else 0
            prev10 = vols[-11:-6]
            prev10_avg = sum(prev10) / len(prev10) if prev10 else 0
            c["hist_vol_ratio"] = round(today["volume"] / prev5_avg, 2) if prev5_avg else None
            c["ma20"] = round(sum(closes[-20:]) / 20, 2)
            c["high10"] = max(highs[-11:-1]) if len(highs) >= 11 else max(highs[:-1]) if len(highs) > 1 else today["high"]
            c["high20"] = max(highs[-21:-1]) if len(highs) >= 21 else c["high10"]
            c["amount20_max"] = max(amounts[-21:-1]) if len(amounts) >= 21 else max(amounts[:-1]) if len(amounts) > 1 else today["amount"]
            c["above_ma20"] = today["close"] > c["ma20"]
            c["break_high10"] = today["close"] > c["high10"]
            c["break_high20"] = today["close"] > c["high20"]
            c["amount_new20"] = today["amount"] > c["amount20_max"]
            c["vol_shrink_then_expand"] = bool(prev10_avg and prev5_avg and prev5_avg <= prev10_avg * 0.95 and today["volume"] >= prev5_avg * 1.5)
        else:
            c["hist_vol_ratio"] = None
            c["ma20"] = None
            c["above_ma20"] = None
            c["break_high10"] = None
            c["break_high20"] = None
            c["amount_new20"] = None
            c["vol_shrink_then_expand"] = None
        return c
    with ThreadPoolExecutor(max_workers=8) as ex:
        candidates = list(ex.map(enrich, candidates))

    board_map = {b["name"]: b.get("flow_yi", 0) for b in industry}
    for c in candidates:
        c["board_flow"] = board_map.get(c.get("industry"), 0)

    cats = categorize_volprice(candidates)

    strong_boards = sorted(industry, key=lambda x: -(x.get("flow_yi") or 0))[:10]
    emotion = compute_emotion(zt, zb, dt)
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": indices,
            "breadth": breadth,
            "emotion": emotion,
            "amount_yi": amount,
        },
        "strong_boards": strong_boards,
        "total_scanned": len(candidates),
        "categories": cats,
        "errors": errors,
    }
