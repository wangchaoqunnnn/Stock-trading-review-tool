# -*- coding: utf-8 -*-
"""A股每日复盘本地服务：实时抓取东方财富数据，前端每30秒自动刷新。

运行: python server.py [port]
"""
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
EM_UT = "bd1d9ddb04089700cf9c27f6f7426281"
EMEX_UT = "7eea3edcaed734bea9cbfc24409ed989"
ALL_A_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
NEWS_KEYWORDS = [
    "A股", "两市", "涨停", "连板", "板块", "资金", "成交", "央行", "政策", "半导体",
    "人工智能", "AI", "机器人", "电力", "新能源", "军工", "航天", "有色", "铜",
    "算力", "华为", "特斯拉", "降息", "加息", "苹果", "英伟达",
]


def http_get(url, headers=None, decode="utf-8", timeout=18, tries=3):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode(decode, errors="replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(0.8)


def http_get_json(url, headers=None):
    return json.loads(http_get(url, headers=headers))


def clist_url(fs, fields, fid="f3", po=1, pn=1, pz=100):
    params = {
        "pn": pn, "pz": pz, "po": po, "np": 1, "ut": EM_UT,
        "fltt": 2, "invt": 2, "fid": fid, "fs": fs, "fields": fields,
    }
    return "https://push2delay.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode(params)


def fetch_paged(fs, fields, fid="f3", po=1, limit=600):
    rows = []
    pn = 1
    while True:
        url = clist_url(fs, fields, fid=fid, po=po, pn=pn, pz=100)
        data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
        total = int(data["total"])
        diff = data.get("diff") or []
        rows.extend(diff)
        if len(rows) >= min(total, limit) or not diff:
            break
        pn += 1
        time.sleep(0.05)
    return rows


def to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def fetch_indices():
    indices = [
        ("上证指数", "1.000001"),
        ("深证成指", "0.399001"),
        ("创业板指", "0.399006"),
        ("科创50", "1.000688"),
        ("沪深300", "1.000300"),
        ("北证50", "0.899050"),
    ]
    out = []
    for name, secid in indices:
        try:
            params = {
                "secid": secid,
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                "iscr": 0, "iscca": 1, "ndays": 1,
            }
            url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get?" + urllib.parse.urlencode(params)
            data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
            pre = float(data["preClose"])
            trends = data.get("trends") or []
            last = trends[-1].split(",")
            cur = float(last[2])
            out.append({
                "name": name, "pre_close": pre, "current": cur,
                "pct": round((cur / pre - 1) * 100, 2),
            })
        except Exception:
            pass
    return out


def fetch_market_amount():
    try:
        secids = "1.000001,0.399001"
        params = {"fltt": 2, "invt": 2, "fields": "f2,f3,f6,f12,f14", "secids": secids}
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
        data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
        diff = data.get("data", {}).get("diff") or []
        total = 0.0
        for r in diff:
            total += to_num(r.get("f6"))
        return round(total / 100000000, 2)
    except Exception:
        return None


def fetch_breadth():
    date = datetime.now().strftime("%Y%m%d")
    url = f"https://push2ex.eastmoney.com/getTopicZDFenBu?ut={EMEX_UT}&dpt=wz.ztzt&Pageindex=0&pagesize=100&sort=fbt%3Aasc&date={date}"
    data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
    fenbu = data.get("data", {}).get("fenbu") or []
    up = down = flat = 0
    dist = []
    for item in fenbu:
        for k, v in item.items():
            try:
                iv = int(k)
            except Exception:
                continue
            v = int(v or 0)
            if iv > 0:
                up += v
            elif iv < 0:
                down += v
            else:
                flat += v
            dist.append({"key": k, "count": v})
    dist.sort(key=lambda x: int(x["key"]))
    return {"up": up, "down": down, "flat": flat, "distribution": dist, "date": date}


def fetch_zt_pool():
    return fetch_ex_pool("getTopicZTPool")


def fetch_zb_pool():
    return fetch_ex_pool("getTopicZBPool")


def fetch_dt_pool():
    return fetch_ex_pool("getTopicDTPool")


def fetch_ex_pool(path):
    date = datetime.now().strftime("%Y%m%d")
    pool = []
    tc = 0
    page = 0
    while page < 8:
        url = (
            f"https://push2ex.eastmoney.com/{path}?ut={EMEX_UT}&dpt=wz.ztzt"
            f"&Pageindex={page}&pagesize=100&sort=fbt%3Aasc&date={date}"
        )
        data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
        d = data.get("data") or {}
        tc = int(d.get("tc") or 0)
        rows = d.get("pool") or []
        pool.extend(rows)
        if len(pool) >= tc or not rows:
            break
        page += 1
        time.sleep(0.08)
    return {"tc": tc, "pool": pool}


def board_rows(rows):
    out = []
    for r in rows:
        prev = to_num(r.get("f18"))
        gap = (to_num(r.get("f17")) / prev - 1) * 100 if prev else 0.0
        out.append({
            "code": r.get("f12"),
            "name": r.get("f14"),
            "pct": to_num(r.get("f3")),
            "gap": round(gap, 2),
            "flow_yi": round(to_num(r.get("f62")) / 100000000, 2),
            "amount_yi": round(to_num(r.get("f6")) / 100000000, 2),
            "turnover": to_num(r.get("f8")),
            "vol_ratio": to_num(r.get("f10")),
            "ratio": to_num(r.get("f184")),
            "up": r.get("f104"),
            "down": r.get("f105"),
            "leader": r.get("f128"),
            "leader_pct": to_num(r.get("f141")),
        })
    return out


def fetch_industry_boards():
    rows = fetch_paged(
        "m:90+t:2+f:!50",
        "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f184,f104,f105,f128,f141",
    )
    return board_rows(rows)


def fetch_concept_boards():
    rows = fetch_paged(
        "m:90+t:3+f:!50",
        "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f184,f104,f105,f128,f141",
    )
    return board_rows(rows)


def fetch_stock_flow_top(po=1, pz=40):
    fields = "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f184"
    rows = fetch_paged(ALL_A_FS, fields, fid="f62", po=po, limit=pz)
    return [
        {
            "code": r.get("f12"),
            "name": r.get("f14"),
            "pct": to_num(r.get("f3")),
            "flow_yi": round(to_num(r.get("f62")) / 100000000, 2),
            "amount_yi": round(to_num(r.get("f6")) / 100000000, 2),
            "turnover": to_num(r.get("f8")),
            "vol_ratio": to_num(r.get("f10")),
            "ratio": to_num(r.get("f184")),
        }
        for r in rows
    ]


def fetch_news():
    hits = []
    today = datetime.now().strftime("%Y-%m-%d")
    for col in (350, 351):
        for page in (1, 2):
            params = {
                "client": "web", "biz": "web_news_col", "column": col,
                "order": 1, "needInteractData": 0, "page_index": page,
                "page_size": 40, "req_trace": "eastmoney",
            }
            url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?" + urllib.parse.urlencode(params)
            try:
                data = http_get_json(url, headers={"Referer": "https://finance.eastmoney.com/"})
                for item in data.get("data", {}).get("list", []):
                    st = str(item.get("showTime", ""))
                    if not st.startswith(today):
                        continue
                    text = str(item.get("title", "")) + " " + str(item.get("summary", ""))
                    if any(k in text for k in NEWS_KEYWORDS):
                        hits.append({
                            "time": st,
                            "title": item.get("title", ""),
                            "summary": (item.get("summary", "") or "")[:160],
                            "url": item.get("url", ""),
                        })
            except Exception:
                pass
            time.sleep(0.05)
    seen = set()
    out = []
    for h in hits:
        if h["title"] in seen:
            continue
        seen.add(h["title"])
        out.append(h)
    return out[:25]


def compute_emotion(zt, zb, dt):
    pool = zt["pool"]
    jingjia = [x for x in pool if int(x.get("fbt") or 0) < 92600]
    max_lb = max((int(x.get("lbc") or 0) for x in pool), default=0)
    zt_tc = zt["tc"] or len(pool)
    zb_tc = zb["tc"] or 0
    dt_tc = dt["tc"] or 0
    zhaban_rate = round(zb_tc / (zt_tc + zb_tc) * 100, 1) if (zt_tc + zb_tc) else 0
    return {
        "zt": zt_tc,
        "zb": zb_tc,
        "dt": dt_tc,
        "jingjia": len(jingjia),
        "max_lb": max_lb,
        "zhaban_rate": zhaban_rate,
    }


def zt_summary(zt):
    pool = zt["pool"]
    by_board = {}
    for x in pool:
        b = x.get("hybk") or "未知"
        by_board.setdefault(b, {"count": 0, "fund_yi": 0.0, "max_lb": 0})
        by_board[b]["count"] += 1
        by_board[b]["fund_yi"] += to_num(x.get("fund")) / 100000000
        by_board[b]["max_lb"] = max(by_board[b]["max_lb"], int(x.get("lbc") or 0))
    board_list = sorted(
        [{"name": k, **v} for k, v in by_board.items()],
        key=lambda x: (-x["count"], -x["fund_yi"]),
    )[:12]
    liangban = sorted(
        [x for x in pool if int(x.get("lbc") or 0) >= 1],
        key=lambda x: (-int(x.get("lbc") or 0), -(to_num(x.get("fund")) or 0)),
    )[:12]
    auction = sorted(
        [x for x in pool if int(x.get("fbt") or 0) < 92600],
        key=lambda x: -(to_num(x.get("fund")) or 0),
    )[:12]
    return {"by_board": board_list, "liangban": liangban, "auction": auction}


def build_signals(ctx):
    sig = []
    b = ctx["breadth"]
    emo = ctx["emotion"]
    ind = {x["name"]: x for x in ctx["indices"]}
    sh = ind.get("上证指数", {}).get("pct", 0)
    jj = emo["jingjia"]
    max_lb = emo["max_lb"]
    zt = emo["zt"]
    zb = emo["zb"]
    top_industry = ctx["sectors"]["industry_top_pct"][0] if ctx["sectors"]["industry_top_pct"] else {}
    top_concept = ctx["sectors"]["concept_top_flow"][0] if ctx["sectors"]["concept_top_flow"] else {}
    top_flow = ctx["flows"]["inflow"][0] if ctx["flows"]["inflow"] else {}

    def push(name, ok, detail):
        sig.append({"name": name, "ok": ok, "detail": detail})

    push("竞价活跃", jj >= 3, f"竞价(09:25)涨停 {jj} 家")
    push("连板高度", max_lb >= 3, f"最高 {max_lb} 连板")
    push("涨停梯队", zt >= 20, f"涨停 {zt} 家 / 炸板 {zb} 家")
    push("指数环境", (b["up"] > b["down"]) and sh > 0,
         f"上涨 {b['up']} / 下跌 {b['down']}，上证 {sh:+.2f}%")
    push("板块共振", top_industry.get("pct", 0) >= 2 and top_industry.get("flow_yi", 0) > 0,
         f"{top_industry.get('name','')} {top_industry.get('pct',0):+.2f}%，主力 {top_industry.get('flow_yi',0):+.2f}亿")
    push("主线资金", top_concept.get("flow_yi", 0) >= 5,
         f"{top_concept.get('name','')} 主力净流入 {top_concept.get('flow_yi',0):+.2f}亿")
    push("个股资金", top_flow.get("flow_yi", 0) >= 1,
         f"{top_flow.get('name','')} 主力净流入 {top_flow.get('flow_yi',0):+.2f}亿")
    return sig


def build_watchlist(ctx):
    pool = ctx["zt_pool_raw"]
    out = []
    seen = set()
    for x in sorted(pool, key=lambda x: (-(int(x.get("lbc") or 0)), -(to_num(x.get("fund")) or 0)))[:12]:
        code = x.get("c")
        out.append({
            "code": code,
            "name": x.get("n"),
            "pct": round(to_num(x.get("zdp")), 2),
            "flow_yi": round(to_num(x.get("fund")) / 100000000, 2),
            "lbc": int(x.get("lbc") or 0),
            "fbt": str(x.get("fbt") or ""),
            "zbc": int(x.get("zbc") or 0),
            "industry": x.get("hybk"),
        })
        seen.add(code)
    for x in ctx["flows"]["inflow"][:10]:
        code = x.get("code")
        if code in seen:
            continue
        out.append({
            "code": code,
            "name": x.get("name"),
            "pct": round(x.get("pct") or 0, 2),
            "flow_yi": x.get("flow_yi"),
            "lbc": 0,
            "fbt": "",
            "zbc": 0,
            "industry": "",
        })
    return out[:18]


def fetch_snapshot():
    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "indices": ex.submit(safe, "indices", fetch_indices),
            "amount": ex.submit(safe, "amount", fetch_market_amount),
            "breadth": ex.submit(safe, "breadth", fetch_breadth),
            "zt": ex.submit(safe, "zt", fetch_zt_pool),
            "zb": ex.submit(safe, "zb", fetch_zb_pool),
            "dt": ex.submit(safe, "dt", fetch_dt_pool),
            "industry": ex.submit(safe, "industry", fetch_industry_boards),
            "concept": ex.submit(safe, "concept", fetch_concept_boards),
            "inflow": ex.submit(safe, "inflow", lambda: fetch_stock_flow_top(po=1)),
            "outflow": ex.submit(safe, "outflow", lambda: fetch_stock_flow_top(po=0)),
            "news": ex.submit(safe, "news", fetch_news),
        }
        results = {k: f.result() for k, f in futures.items()}

    errors = [str(v.get("error")) for k, v in results.items() if isinstance(v, dict) and "error" in v]
    indices = results["indices"][1] if not isinstance(results["indices"], dict) else []
    amount = results["amount"][1] if not isinstance(results["amount"], dict) else None
    breadth = results["breadth"][1] if not isinstance(results["breadth"], dict) else {"up": 0, "down": 0, "flat": 0, "distribution": []}
    zt = results["zt"][1] if not isinstance(results["zt"], dict) else {"tc": 0, "pool": []}
    zb = results["zb"][1] if not isinstance(results["zb"], dict) else {"tc": 0, "pool": []}
    dt = results["dt"][1] if not isinstance(results["dt"], dict) else {"tc": 0, "pool": []}
    industry = results["industry"][1] if not isinstance(results["industry"], dict) else []
    concept = results["concept"][1] if not isinstance(results["concept"], dict) else []
    inflow = results["inflow"][1] if not isinstance(results["inflow"], dict) else []
    outflow = results["outflow"][1] if not isinstance(results["outflow"], dict) else []
    news = results["news"][1] if not isinstance(results["news"], dict) else []

    industry_pct = sorted([x for x in industry if x.get("pct") == x.get("pct")], key=lambda x: -x["pct"])[:15]
    industry_flow = sorted([x for x in industry if x.get("flow_yi") == x.get("flow_yi")], key=lambda x: -x["flow_yi"])[:15]
    concept_pct = sorted([x for x in concept if x.get("pct") == x.get("pct")], key=lambda x: -x["pct"])[:15]
    concept_flow = sorted([x for x in concept if x.get("flow_yi") == x.get("flow_yi")], key=lambda x: -x["flow_yi"])[:15]

    emotion = compute_emotion(zt, zb, dt)
    zts = zt_summary(zt)
    sectors = {
        "industry_top_pct": industry_pct,
        "industry_top_flow": industry_flow,
        "concept_top_pct": concept_pct,
        "concept_top_flow": concept_flow,
    }
    flows = {"inflow": inflow, "outflow": outflow}
    ctx = {
        "indices": indices,
        "amount": amount,
        "breadth": breadth,
        "emotion": emotion,
        "sectors": sectors,
        "zt_pool_raw": zt["pool"],
        "flows": flows,
        "news": news,
    }
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "indices": indices,
        "amount_yi": amount,
        "breadth": breadth,
        "emotion": emotion,
        "zt_summary": zts,
        "sectors": sectors,
        "flows": flows,
        "watchlist": build_watchlist(ctx),
        "signals": build_signals(ctx),
        "news": news,
        "errors": errors,
    }


class SnapshotCache:
    def __init__(self, ttl=30):
        self.ttl = ttl
        self.lock = threading.Lock()
        self.ts = 0
        self.data = None

    def get(self, force=False):
        now = time.time()
        with self.lock:
            if force or self.data is None or (now - self.ts) > self.ttl:
                self.data = fetch_snapshot()
                self.ts = time.time()
            return self.data


CACHE = SnapshotCache(ttl=30)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/api/snapshot":
            self._send_json(CACHE.get())
        elif path == "/api/refresh":
            self._send_json(CACHE.get(force=True))
        elif path == "/" or path == "/index.html":
            self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
        elif path == "/app.js":
            self._send_file(os.path.join(STATIC_DIR, "app.js"), "text/javascript; charset=utf-8")
        elif path == "/style.css":
            self._send_file(os.path.join(STATIC_DIR, "style.css"), "text/css; charset=utf-8")
        else:
            self.send_error(404)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"A股每日复盘服务已启动: http://127.0.0.1:{port}")
    print("首次数据抓取需要几秒，之后每30秒自动刷新。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
