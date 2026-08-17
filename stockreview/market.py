# -*- coding: utf-8 -*-
"""市场环境上下文：指数、涨跌分布、市场情绪、两市成交额（各策略页共用）。"""
from concurrent.futures import ThreadPoolExecutor

from . import em
from .analysis import compute_emotion


def _safe(name, fn):
    try:
        return name, fn()
    except Exception as exc:
        return name, {"error": f"{type(exc).__name__}: {exc}"}


def fetch_market_context():
    """并行抓取市场环境数据并计算情绪指标。"""
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "indices": ex.submit(_safe, "indices", em.fetch_indices),
            "breadth": ex.submit(_safe, "breadth", em.fetch_breadth),
            "zt": ex.submit(_safe, "zt", em.fetch_zt_pool),
            "zb": ex.submit(_safe, "zb", em.fetch_zb_pool),
            "dt": ex.submit(_safe, "dt", em.fetch_dt_pool),
            "amount": ex.submit(_safe, "amount", em.fetch_market_amount),
        }
        results = {k: f.result() for k, f in futures.items()}

    def val(k, default):
        return results[k][1] if not isinstance(results[k], dict) else default

    zt = val("zt", {"tc": 0, "pool": []})
    zb = val("zb", {"tc": 0, "pool": []})
    dt = val("dt", {"tc": 0, "pool": []})
    emotion = compute_emotion(zt, zb, dt)
    errors = [str(v.get("error")) for v in results.values() if isinstance(v, dict) and "error" in v]
    return {
        "indices": val("indices", []),
        "breadth": val("breadth", {"up": 0, "down": 0, "flat": 0}),
        "emotion": emotion,
        "amount_yi": val("amount", None),
        "errors": errors,
    }
