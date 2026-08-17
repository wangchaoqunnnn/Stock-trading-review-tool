# -*- coding: utf-8 -*-
"""今日涨停面板：涨停 / 炸板 / 跌停 / 最高板 / 竞价涨停。

- 数据源：东方财富当日涨停池(getTopicZTPool)、炸板池(getTopicZBPool)、
  跌停池(getTopicDTPool)，均为封板/开板实时口径。
- 竞价涨停：首封时间 fbt < 09:26:00 的涨停股。
- 最高板：当日最高连板数（lbc 最大）的涨停股。
- 成交量/量比/换手：从行情接口批量补取（池子本身不含量比）。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em
from .market import fetch_market_context
from .utils import to_num

# 行情补取字段：f5 成交量(手)、f6 成交额、f8 换手、f10 量比
SPOT_FIELDS = "f2,f3,f5,f6,f8,f10,f12,f14,f62"


def _safe(name, fn):
    try:
        return name, fn()
    except Exception as exc:
        return name, {"error": f"{type(exc).__name__}: {exc}"}


def _fmt_row(x, spot):
    """池子行 + 实时行情 -> 统一输出行。"""
    return {
        "code": str(x.get("c") or ""),
        "name": x.get("n"),
        "industry": x.get("hybk"),
        "pct": round(to_num(x.get("zdp")), 2),
        "lbc": int(x.get("lbc") or 0),
        "fbt": str(x.get("fbt") or ""),
        "zbc": int(x.get("zbc") or 0),
        "amount_yi": round(to_num(x.get("amount")) / 100000000, 2),
        "fund_yi": round(to_num(x.get("fund")) / 100000000, 2),
        "vol_wan": round(to_num(spot.get("f5")) / 10000, 0) if spot else None,
        "vol_ratio": round(to_num(spot.get("f10")), 2) if spot else None,
        "turnover": round(to_num(spot.get("f8")), 2) if spot else None,
    }


def _pool_rows(pool, spot_map):
    return [_fmt_row(x, spot_map.get(str(x.get("c")))) for x in (pool.get("pool") or [])]


def _by_fbt(r):
    try:
        return int(r["fbt"] or 0)
    except (TypeError, ValueError):
        return 999999


def fetch_ztpool_detail():
    """今日涨停面板主函数。"""
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "zt": ex.submit(_safe, "zt", em.fetch_zt_pool),
            "zb": ex.submit(_safe, "zb", em.fetch_zb_pool),
            "dt": ex.submit(_safe, "dt", em.fetch_dt_pool),
        }
        results = {k: f.result() for k, f in futures.items()}
        context = ex.submit(fetch_market_context).result()

    errors = list(context["errors"])
    zt = results["zt"][1] if not isinstance(results["zt"], dict) else {"tc": 0, "pool": []}
    zb = results["zb"][1] if not isinstance(results["zb"], dict) else {"tc": 0, "pool": []}
    dt = results["dt"][1] if not isinstance(results["dt"], dict) else {"tc": 0, "pool": []}
    for k in ("zt", "zb", "dt"):
        v = results[k]
        if isinstance(v, dict) and "error" in v:
            errors.append(v["error"])

    # 批量补取行情（量比/成交量/换手）
    codes = set()
    for pool in (zt, zb, dt):
        codes.update(str(x.get("c")) for x in (pool.get("pool") or []))
    spot_map = em.fetch_spot_map(sorted(codes), fields=SPOT_FIELDS)

    zt_rows = _pool_rows(zt, spot_map)
    zb_rows = _pool_rows(zb, spot_map)
    dt_rows = _pool_rows(dt, spot_map)

    # 排序：涨停按连板降序+首封升序；炸板/跌停按首封升序
    zt_rows.sort(key=lambda r: (-r["lbc"], _by_fbt(r)))
    zb_rows.sort(key=_by_fbt)
    dt_rows.sort(key=_by_fbt)

    max_lb = max((r["lbc"] for r in zt_rows), default=0)
    max_board = [r for r in zt_rows if max_lb > 0 and r["lbc"] == max_lb]
    max_board.sort(key=lambda r: -r["fund_yi"])
    jingjia = [r for r in zt_rows if r["fbt"] and _by_fbt(r) < 92600]
    jingjia.sort(key=_by_fbt)

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "zt": {"count": len(zt_rows), "stocks": zt_rows},
        "zb": {"count": len(zb_rows), "stocks": zb_rows},
        "dt": {"count": len(dt_rows), "stocks": dt_rows},
        "max_board": {"count": len(max_board), "max_lb": max_lb, "stocks": max_board},
        "jingjia": {"count": len(jingjia), "stocks": jingjia},
        "errors": errors,
    }
