# -*- coding: utf-8 -*-
"""市场热力图：全部行业板块按涨跌幅着色的热力数据（前端渲染色块）。"""
from datetime import datetime

from . import em
from .market import fetch_market_context
from .utils import to_num


def fetch_heatmap_scan():
    """热力图扫描主函数：返回全部行业板块（含涨跌幅/主力资金/成交额/领涨）。"""
    errors = []
    industry = []
    try:
        industry = em.fetch_industry_boards()
    except Exception as exc:
        errors.append(f"行业板块: {type(exc).__name__}: {exc}")

    context = fetch_market_context()
    errors.extend(context["errors"])

    rows = [x for x in industry if x.get("pct") == x.get("pct")]  # 过滤 NaN
    rows.sort(key=lambda x: -x["pct"])
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "total": len(rows),
        "boards": rows,
        "errors": errors,
    }
