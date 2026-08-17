# -*- coding: utf-8 -*-
"""市场热度模块：同花顺热股榜（A股日榜）。

- 热度排名 TOP50：按榜单排名（order）取前 50。
- 热度上升最快 TOP50：按排名变化（hot_rank_chg，正数=排名上升）降序取前 50。
- 附带每只股票：涨跌幅、热度值、概念标签、上榜原因等。
"""
from datetime import datetime

from . import net
from .market import fetch_market_context
from .utils import to_num

# 同花顺热股榜接口
HOT_URL = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"
HOT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://www.10jqka.com.cn/",
}

TOP_N = 50


def fetch_hot_rank_list(type_="day"):
    """抓取同花顺热股榜并规范化为行列表。"""
    url = f"{HOT_URL}?stock_type=a&type={type_}&list_type=normal"
    data = net.http_get_json(url, headers=HOT_HEADERS)
    lst = ((data.get("data") or {}).get("stock_list")) or []
    out = []
    for x in lst:
        tag = x.get("tag") or {}
        concepts = tag.get("concept_tag") or []
        out.append({
            "code": str(x.get("code") or ""),
            "name": x.get("name"),
            "rank": int(x.get("order") or 0),
            "rate": to_num(x.get("rate")),
            "rank_chg": int(x.get("hot_rank_chg") or 0),
            "pct": to_num(x.get("rise_and_fall")),
            "tags": concepts[:4],
            "popularity_tag": tag.get("popularity_tag") or "",
            "analyse_title": x.get("analyse_title") or "",
        })
    return out


def fetch_hot_scan():
    """市场热度扫描主函数：热度排名TOP50 + 热度上升最快TOP50。"""
    errors = []
    rows = []
    try:
        rows = fetch_hot_rank_list("day")
    except Exception as exc:
        errors.append(f"热股榜: {type(exc).__name__}: {exc}")

    context = fetch_market_context()
    errors.extend(context["errors"])

    top = sorted(rows, key=lambda x: x["rank"])[:TOP_N]
    rising = sorted(rows, key=lambda x: -x["rank_chg"])[:TOP_N]

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "source": "同花顺热股榜（A股日榜）",
        "top": {"count": len(top), "stocks": top},
        "rising": {"count": len(rising), "stocks": rising},
        "errors": errors,
    }
