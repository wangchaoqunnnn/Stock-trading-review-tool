# -*- coding: utf-8 -*-
"""龙头股模块：市场总龙 / 板块龙头 / 情绪龙头。

- 市场总龙：全市场最高连板（lbc=max_lb）的股票，按封单金额降序。
- 板块龙头：按行业板块分组，组内按（连板、首封时间、封单）取第一。
- 情绪龙头：连板梯队前排（lbc≥2 按连板+封单），叠加同花顺人气榜排名标注；
  无连板时回退为「涨停池 ∩ 人气榜」。
"""
from datetime import datetime

from . import em
from .hot import fetch_hot_rank_list
from .market import fetch_market_context
from .utils import to_num


def _fbt_int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 999999


def _fmt_zt(x):
    return {
        "code": str(x.get("c") or ""),
        "name": x.get("n"),
        "industry": x.get("hybk"),
        "pct": round(to_num(x.get("zdp")), 2),
        "lbc": int(x.get("lbc") or 0),
        "fbt": str(x.get("fbt") or ""),
        "fund_yi": round(to_num(x.get("fund")) / 100000000, 2),
        "amount_yi": round(to_num(x.get("amount")) / 100000000, 2),
        "turnover": round(to_num(x.get("hs")), 2),
    }


def fetch_leaders_scan():
    """龙头股扫描主函数。"""
    errors = []
    pool = []
    hot_rows = []
    try:
        pool = (em.fetch_zt_pool() or {}).get("pool") or []
    except Exception as exc:
        errors.append(f"涨停池: {type(exc).__name__}: {exc}")
    try:
        hot_rows = fetch_hot_rank_list("day")
    except Exception as exc:
        errors.append(f"人气榜: {type(exc).__name__}: {exc}")

    context = fetch_market_context()
    errors.extend(context["errors"])

    rows = [_fmt_zt(x) for x in pool]
    hot_map = {h["code"]: h for h in hot_rows}

    # ---- 市场总龙：最高连板 + 封单降序 ----
    max_lb = max((r["lbc"] for r in rows), default=0)
    market_leader = sorted(
        [r for r in rows if max_lb > 0 and r["lbc"] == max_lb],
        key=lambda x: -x["fund_yi"],
    )[:5]
    for r in market_leader:
        r["tag"] = f"最高{max_lb}板"

    # ---- 板块龙头：按行业分组取最强 ----
    by_board = {}
    for r in rows:
        by_board.setdefault(r["industry"] or "未知", []).append(r)
    board_leaders = []
    for board, items in by_board.items():
        items.sort(key=lambda x: (-x["lbc"], _fbt_int(x["fbt"]), -x["fund_yi"]))
        leader = items[0]
        board_leaders.append({"industry": board, "zt_count": len(items), **leader})
    board_leaders.sort(key=lambda x: (-x["zt_count"], -x["lbc"], _fbt_int(x["fbt"])))
    board_leaders = board_leaders[:20]

    # ---- 情绪龙头：连板梯队前排 + 人气标注 ----
    ladder = sorted([r for r in rows if r["lbc"] >= 2], key=lambda x: (-x["lbc"], -x["fund_yi"]))
    emotion = []
    for r in ladder[:10]:
        h = hot_map.get(r["code"])
        emotion.append({
            **r,
            "hot_rank": h["rank"] if h else None,
            "hot_rate": h["rate"] if h else None,
        })
    if not emotion:
        # 回退：涨停池 ∩ 人气榜前20
        zt_codes = {r["code"]: r for r in rows}
        for h in sorted(hot_rows, key=lambda x: x["rank"])[:20]:
            r = zt_codes.get(h["code"])
            if r:
                emotion.append({**r, "hot_rank": h["rank"], "hot_rate": h["rate"]})
        emotion = emotion[:10]
    for r in emotion:
        r["tag"] = ("最高板" if r["lbc"] == max_lb and max_lb > 0 else "") + \
                   ("人气" if r.get("hot_rank") else "")

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "max_lb": max_lb,
        "market_leader": {"count": len(market_leader), "stocks": market_leader},
        "board_leader": {"count": len(board_leaders), "stocks": board_leaders},
        "emotion_leader": {"count": len(emotion), "stocks": emotion},
        "errors": errors,
    }
