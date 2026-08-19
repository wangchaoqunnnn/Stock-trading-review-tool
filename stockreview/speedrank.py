# -*- coding: utf-8 -*-
"""涨速榜：实时 3 分钟 / 5 分钟涨速前 100 只股票。

- 主榜：全A clist 按即时涨速（f22）降序取前 100。
- 3/5 分钟涨速：对前 100 只拉取分时数据（每分钟价格），
  3分钟涨速 = 现价/3分钟前价-1，5分钟涨速 = 现价/5分钟前价-1。
- 缓存 30s，配合前端 30s 自动刷新。
"""
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .config import ALL_A_FS, INDEX_UT
from .market import fetch_market_context
from .utils import to_num

# 扫描字段：f22 即时涨速
SCAN_FIELDS = "f2,f3,f5,f6,f8,f10,f12,f14,f22,f62,f100"
TOP_N = 100
SPEED_WORKERS = 10


def _intraday_closes(code):
    """单只个股分时收盘价序列（每分钟）。"""
    try:
        secid = ("1." if code.startswith("6") else "0.") + code
        params = {
            "secid": secid,
            "ut": INDEX_UT,
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "iscr": 0, "iscca": 1, "ndays": 1,
        }
        url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get?" + urllib.parse.urlencode(params)
        data = net.http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
        rows = data.get("trends") or []
        return [float(r.split(",")[2]) for r in rows if len(r.split(",")) > 2]
    except Exception:
        return []


def _speed3_5(closes):
    """由分时收盘价序列计算 3 分钟/5 分钟涨速（%）。"""
    if not closes:
        return None, None
    cur = closes[-1]
    s3 = round((cur / closes[-4] - 1) * 100, 2) if len(closes) >= 4 and closes[-4] else None
    s5 = round((cur / closes[-6] - 1) * 100, 2) if len(closes) >= 6 and closes[-6] else None
    return s3, s5


def fetch_speedrank_scan(date=None):
    """涨速榜主函数。date 非空：分时数据源仅实时，不支持历史回放。"""
    context = fetch_market_context()
    errors = list(context["errors"])
    if date:
        return {
            "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "market": {
                "indices": context["indices"], "breadth": context["breadth"],
                "emotion": context["emotion"], "amount_yi": context["amount_yi"],
            },
            "stocks": [],
            "errors": [f"历史回放({date})：涨速榜为分时实时数据源，不支持历史回放"],
        }

    rows = []
    try:
        rows = net.fetch_paged(ALL_A_FS, SCAN_FIELDS, fid="f22", po=1, limit=TOP_N)
    except Exception as exc:
        errors.append(f"涨速榜: {type(exc).__name__}: {exc}")

    codes = [str(r.get("f12")) for r in rows]
    with ThreadPoolExecutor(max_workers=SPEED_WORKERS) as ex:
        closes_list = list(ex.map(_intraday_closes, codes))

    stocks = []
    for r, closes in zip(rows, closes_list):
        s3, s5 = _speed3_5(closes)
        stocks.append({
            "code": str(r.get("f12")),
            "name": r.get("f14"),
            "price": round(to_num(r.get("f2")), 2),
            "pct": round(to_num(r.get("f3")), 2),
            "speed": round(to_num(r.get("f22")), 2),   # 即时涨速
            "speed3": s3,                               # 3分钟涨速
            "speed5": s5,                               # 5分钟涨速
            "vol_ratio": round(to_num(r.get("f10")), 2),
            "amount_yi": round(to_num(r.get("f6")) / 100000000, 2),
            "turnover": round(to_num(r.get("f8")), 2),
            "main_flow": round(to_num(r.get("f62")) / 100000000, 2),
            "industry": r.get("f100"),
        })
    stocks.sort(key=lambda x: -(x["speed3"] if x["speed3"] is not None else -999))

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "stocks": stocks,
        "errors": errors,
    }
