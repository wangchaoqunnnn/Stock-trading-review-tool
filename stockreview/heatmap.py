# -*- coding: utf-8 -*-
"""市场热力图：全部行业板块按涨跌幅着色的热力数据（前端渲染色块）。"""
from datetime import datetime

from . import em
from .market import fetch_market_context
from .utils import to_num


def fetch_heatmap_scan(date=None):
    """热力图扫描主函数。

    实时：返回全部行业板块（涨跌幅/主力资金/成交额/领涨）。
    历史：板块涨跌幅用板块K线重构；主力资金/成交额为实时字段不可得（置 0）。
    """
    errors = []
    context = fetch_market_context()
    errors.extend(context["errors"])

    if date:
        ds = date.replace("-", "")
        boards = em.fetch_industry_boards()
        rows = []
        for b in boards:
            code = b.get("code")
            if not code:
                continue
            hist = em.fetch_board_kline(code, limit=5, end_date=date)
            pct = None
            if hist:
                pct = hist[-1].get("pct")
            if pct is None or pct != pct:
                continue
            rows.append({
                "code": code, "name": b.get("name"),
                "pct": round(float(pct), 2),
                "flow_yi": 0.0, "amount_yi": 0.0,
                "leader": "", "hist": True,
            })
        errors.append(f"历史回放({date})：主力资金/成交额为实时字段，历史模式下为 0")
    else:
        try:
            industry = em.fetch_industry_boards()
        except Exception as exc:
            errors.append(f"行业板块: {type(exc).__name__}: {exc}")
            industry = []
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
