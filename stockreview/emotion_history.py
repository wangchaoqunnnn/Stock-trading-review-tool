# -*- coding: utf-8 -*-
"""市场情绪周期表：最近 N 个交易日每日市场情绪分。

- 数据：东方财富历史涨停池/炸板池/跌停池 + 涨跌分布（push2ex 按日期）。
- 情绪分（0~100，越高越热）：
  涨停家数(25) + 炸板率(20) + 最高连板(15) + 竞价涨停(10) + 上涨占比(20) + 跌停(10)。
- 等级：≥75 亢奋 / 60~75 活跃 / 40~60 中性 / 25~40 低迷 / <25 冰点。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from . import em
from .utils import to_num

DEFAULT_DAYS = 15
MAX_CALENDAR_DAYS = 45


def emotion_level(score):
    if score >= 75:
        return "亢奋"
    if score >= 60:
        return "活跃"
    if score >= 40:
        return "中性"
    if score >= 25:
        return "低迷"
    return "冰点"


def emotion_score(zt, zb, dt, breadth):
    """由当日池子与涨跌分布计算情绪分与明细指标。"""
    zt_tc = zt["tc"] or len(zt["pool"])
    zb_tc = zb["tc"] or 0
    dt_tc = dt["tc"] or 0
    pool = zt.get("pool") or []
    max_lb = max((int(x.get("lbc") or 0) for x in pool), default=0)
    jingjia = len([x for x in pool if int(x.get("fbt") or 0) < 92600])
    zhaban_rate = round(zb_tc / (zt_tc + zb_tc) * 100, 1) if (zt_tc + zb_tc) else 0
    up = to_num(breadth.get("up") or 0)
    down = to_num(breadth.get("down") or 0)
    up_ratio = round(up / (up + down), 3) if (up + down) else 0.5
    score = round(
        min(zt_tc, 80) / 80 * 25
        + max(0.0, 1 - zhaban_rate / 50) * 20
        + min(max_lb, 7) / 7 * 15
        + min(jingjia, 10) / 10 * 10
        + up_ratio * 20
        + max(0.0, 1 - dt_tc / 30) * 10,
        1,
    )
    return {
        "zt": zt_tc, "zb": zb_tc, "dt": dt_tc,
        "max_lb": max_lb, "jingjia": jingjia,
        "zhaban_rate": zhaban_rate, "up_ratio": up_ratio,
        "score": score, "level": emotion_level(score),
    }


def _recent_trading_dates(days=DEFAULT_DAYS, max_calendar=MAX_CALENDAR_DAYS):
    """扫描最近 max_calendar 个日历日，返回 tc>0 的最近 days 个交易日（YYYYMMDD，旧→新）。"""
    now = datetime.now()
    calendar = [(now - timedelta(days=i)).strftime("%Y%m%d") for i in range(max_calendar)]

    def one(ds):
        try:
            data = em.fetch_ex_pool("getTopicZTPool", date=ds)
            return ds, bool(data.get("tc"))
        except Exception:
            return ds, False

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(one, calendar))
    dates = [ds for ds, ok in results if ok]
    dates.sort()
    return dates[-days:]


def _day_data(ds):
    """单日四个数据源的并行抓取。"""
    def safe(fn):
        try:
            return fn()
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=4) as ex:
        zt = ex.submit(safe, lambda: em.fetch_ex_pool("getTopicZTPool", date=ds)).result()
        zb = ex.submit(safe, lambda: em.fetch_ex_pool("getTopicZBPool", date=ds)).result()
        dt = ex.submit(safe, lambda: em.fetch_ex_pool("getTopicDTPool", date=ds)).result()
        breadth = ex.submit(safe, lambda: em.fetch_breadth(date=ds)).result()
    return zt, zb, dt, breadth


def fetch_emotion_history(days=DEFAULT_DAYS):
    """情绪周期表主函数：返回最近 days 个交易日的每日情绪数据（旧→新）。"""
    errors = []
    dates = []
    try:
        dates = _recent_trading_dates(days)
    except Exception as exc:
        errors.append(f"交易日历: {type(exc).__name__}: {exc}")

    def build(ds):
        zt, zb, dt, breadth = _day_data(ds)
        if isinstance(zt, dict) and "error" in zt:
            return None
        if isinstance(breadth, dict) and "error" in breadth:
            breadth = {"up": 0, "down": 0, "flat": 0}
        zb = zb if isinstance(zb, dict) else {"tc": 0, "pool": []}
        dt = dt if isinstance(dt, dict) else {"tc": 0, "pool": []}
        metrics = emotion_score(zt, zb, dt, breadth)
        return {"date": f"{ds[:4]}-{ds[4:6]}-{ds[6:]}", **metrics}

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = [r for r in ex.map(build, dates) if r is not None]

    if errors:
        pass  # 已收集
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "days": len(rows),
        "rows": rows,
        "errors": errors,
    }
