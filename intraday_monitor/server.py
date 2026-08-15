# -*- coding: utf-8 -*-
"""盘中实时监控后端：代理东方财富数据并托管前端页面。

功能与重构前一致，仅将重复的 HTTP 请求封装与配置常量收敛到
仓库根目录的 stockreview 包（net/config），快照组装逻辑保持不变。
"""
import json
import os
import sys
import threading
import time
import urllib.parse
from collections import defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 使仓库根目录的 stockreview 包可导入（本目录不一定在 sys.path 中）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stockreview.config import EMEX_UT, UA
from stockreview.net import http_get_json

HOST = "127.0.0.1"
PORT = 8765
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_TTL = 5

# 快照缓存：{ts, data, lock}
cache = {"ts": 0.0, "data": None, "lock": threading.Lock()}


def fetch_paged(fs, fields, pz=100, fid="f3"):
    """板块/个股列表分页抓取。"""
    rows = []
    pn = 1
    while True:
        params = {
            "pn": pn,
            "pz": pz,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": fid,
            "fs": fs,
            "fields": fields,
        }
        url = "https://push2delay.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode(params)
        data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
        total = int(data["total"])
        diff = data.get("diff") or []
        rows.extend(diff)
        if len(rows) >= total or not diff:
            break
        pn += 1
        time.sleep(0.08)
    return rows


def fetch_zt_pool(date):
    """当日涨停池（单页 500 条）。"""
    params = {
        "ut": EMEX_UT,
        "dpt": "wz.ztzt",
        "Pageindex": 0,
        "pagesize": 500,
        "sort": "fbt:asc",
        "date": date,
    }
    url = "https://push2ex.eastmoney.com/getTopicZTPool?" + urllib.parse.urlencode(params)
    data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/ztb/detail"})
    return data.get("data", {}).get("pool", [])


def fetch_breadth(date):
    """涨跌家数分布。"""
    params = {
        "ut": EMEX_UT,
        "dpt": "wz.ztzt",
        "Pageindex": 0,
        "pagesize": 200,
        "sort": "fbt:asc",
        "date": date,
    }
    url = "https://push2ex.eastmoney.com/getTopicZDFenBu?" + urllib.parse.urlencode(params)
    data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/ztb/detail"})
    fenbu = data.get("data", {}).get("fenbu", [])
    up = down = flat = 0
    for item in fenbu:
        for k, v in item.items():
            try:
                key = int(k)
            except Exception:
                continue
            if key > 0:
                up += v
            elif key < 0:
                down += v
            else:
                flat += v
    return {"up": up, "down": down, "flat": flat}


def fetch_index():
    """主要指数涨跌。"""
    params = {
        "fltt": 2,
        "invt": 2,
        "fields": "f2,f3,f12,f14",
        "secids": "1.000001,0.399001,0.399006",
    }
    url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
    data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
    diff = (data.get("data") or {}).get("diff") or []
    return [{"name": r.get("f14"), "pct": r.get("f3")} for r in diff]


def fetch_quotes(pool):
    """批量个股行情。"""
    secids = ",".join(f"{x['m']}.{x['c']}" for x in pool)
    if not secids:
        return {}
    params = {
        "fltt": 2,
        "invt": 2,
        "fields": "f2,f3,f6,f8,f10,f12,f14,f62,f184",
        "secids": secids,
    }
    url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
    data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
    diff = (data.get("data") or {}).get("diff") or []
    return {str(r.get("f12")): r for r in diff}


def build_snapshot():
    """组装盘中监控快照（输出结构与重构前一致）。"""
    errors = []
    today = datetime.now().strftime("%Y%m%d")
    pool = []
    boards = []
    breadth = {"up": 0, "down": 0, "flat": 0}
    indices = []

    try:
        pool = fetch_zt_pool(today)
    except Exception as exc:
        errors.append(f"涨停池: {exc!r}")
    try:
        boards = fetch_paged(
            "m:90+t:2+f:!50",
            "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f184",
        )
    except Exception as exc:
        errors.append(f"板块: {exc!r}")
    try:
        breadth = fetch_breadth(today)
    except Exception as exc:
        errors.append(f"涨跌分布: {exc!r}")
    try:
        indices = fetch_index()
    except Exception as exc:
        errors.append(f"指数: {exc!r}")

    board_map = {b.get("f14"): b for b in boards}

    try:
        quotes = fetch_quotes(pool)
    except Exception as exc:
        quotes = {}
        errors.append(f"个股行情: {exc!r}")

    sector_stats = defaultdict(
        lambda: {
            "zt_count": 0,
            "fund": 0.0,
            "lbcs": [],
            "early": 0,
            "no_zha": 0,
            "board_pct": None,
            "board_flow": None,
        }
    )
    stocks = []
    for x in pool:
        code = str(x["c"]).zfill(6)
        sec = x.get("hybk", "未知")
        fbt = float(x.get("fbt") or 0)
        zbc = int(float(x.get("zbc") or 0))
        fund = float(x.get("fund") or 0)
        ltsz = float(x.get("ltsz") or 0)
        seal_ratio = fund / ltsz * 100 if ltsz else 0.0
        q = quotes.get(code, {})
        vr = q.get("f10") if q.get("f10") not in (None, "-") else None
        flow = float(q.get("f62") or 0)
        stats = sector_stats[sec]
        stats["zt_count"] += 1
        stats["fund"] += fund / 1e8
        stats["lbcs"].append(int(float(x.get("lbc") or 0)))
        if fbt <= 100000:
            stats["early"] += 1
        if zbc == 0:
            stats["no_zha"] += 1

        tags = []
        if fbt <= 92500:
            tags.append("竞价封板")
        elif fbt <= 100000:
            tags.append("早盘首板")
        if zbc == 0:
            tags.append("未炸板")
        if seal_ratio >= 3:
            tags.append("封单强")
        if vr is not None and vr >= 1.5:
            tags.append("量比放大")

        stocks.append(
            {
                "code": code,
                "name": x.get("n"),
                "sector": sec,
                "pct": round(float(x.get("zdp") or 0), 2),
                "lbc": int(float(x.get("lbc") or 0)),
                "fbt": int(fbt),
                "zbc": zbc,
                "fund": round(fund / 1e8, 2),
                "seal_ratio": round(seal_ratio, 2),
                "hs": q.get("f8"),
                "vr": vr,
                "flow": round(flow / 1e8, 2),
                "amount": round((q.get("f6") or 0) / 1e8, 2),
                "tags": tags,
            }
        )

    sectors = []
    for sec, s in sector_stats.items():
        bd = board_map.get(sec) or next((v for k, v in board_map.items() if sec in k or k in sec), {})
        board_pct = float(bd.get("f3")) if bd.get("f3") is not None else None
        board_flow = float(bd.get("f62") or 0) / 1e8 if bd.get("f62") is not None else None
        sectors.append(
            {
                "sector": sec,
                "zt_count": s["zt_count"],
                "fund": round(s["fund"], 2),
                "max_lbc": max(s["lbcs"]) if s["lbcs"] else 0,
                "early": s["early"],
                "no_zha": s["no_zha"],
                "board_pct": board_pct,
                "board_flow": board_flow,
            }
        )
    sectors.sort(key=lambda x: (-x["zt_count"], -(x["board_flow"] or 0), -x["fund"]))
    stocks.sort(key=lambda x: (x["fbt"], -(x["seal_ratio"])))

    total = len(pool)
    zha_count = sum(1 for s in stocks if s["zbc"] > 0)
    return {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": today,
        "errors": errors,
        "total": total,
        "zha_count": zha_count,
        "zha_ratio": round(zha_count / total * 100, 1) if total else 0,
        "breadth": breadth,
        "indices": indices,
        "sectors": sectors,
        "stocks": stocks,
    }


def get_snapshot():
    with cache["lock"]:
        now = time.time()
        if cache["data"] and now - cache["ts"] < CACHE_TTL:
            return cache["data"]
        data = build_snapshot()
        cache["ts"] = now
        cache["data"] = data
        return data


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stdout.write(f"[monitor] {fmt % args}\n")

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except Exception:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/snapshot":
            try:
                self._send_json(get_snapshot())
            except Exception as exc:
                self._send_json({"error": repr(exc), "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, 500)
        elif parsed.path == "/health":
            self._send_json({"ok": True})
        elif parsed.path in ("/", "/index.html", "/monitor.html"):
            self._send_file(os.path.join(BASE_DIR, "monitor.html"), "text/html; charset=utf-8")
        else:
            self.send_error(404)


def main():
    port = PORT
    args = sys.argv[1:]
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    server = ThreadingHTTPServer((HOST, port), Handler)
    print(f"monitor running at http://{HOST}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
