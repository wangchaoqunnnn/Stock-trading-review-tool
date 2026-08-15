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
from datetime import datetime, timedelta
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
            avg = float(last[7]) if len(last) > 7 else cur
            out.append({
                "name": name, "pre_close": pre, "current": cur,
                "pct": round((cur / pre - 1) * 100, 2),
                "avg_price": avg,
                "above_avg": cur >= avg,
                "vs_avg_pct": round((cur / avg - 1) * 100, 2) if avg else 0,
            })
        except Exception:
            pass
    if len(out) < len(indices):
        try:
            secids = ",".join(secid for _, secid in indices)
            params = {"fltt": 2, "invt": 2, "fields": "f2,f3,f12,f14,f17,f18", "secids": secids}
            url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
            data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
            have = {x["name"] for x in out}
            for r in data.get("data", {}).get("diff") or []:
                if r.get("f14") in have:
                    continue
                out.append({
                    "name": r.get("f14"),
                    "pre_close": to_num(r.get("f18")),
                    "current": to_num(r.get("f2")),
                    "pct": round(to_num(r.get("f3")), 2),
                    "avg_price": None,
                    "above_avg": None,
                    "vs_avg_pct": None,
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


def fetch_ex_pool(path, date=None):
    date = date or datetime.now().strftime("%Y%m%d")
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


def find_previous_zt_pool():
    now = datetime.now()
    for i in range(1, 8):
        d = (now - timedelta(days=i)).strftime("%Y%m%d")
        try:
            data = fetch_ex_pool("getTopicZTPool", date=d)
            if data.get("tc"):
                return d, data
        except Exception:
            pass
    return None, {"tc": 0, "pool": []}


def fetch_yesterday_zt_perf():
    prev_date, prev_zt = find_previous_zt_pool()
    pool = prev_zt.get("pool") or []
    codes = [str(x.get("c")) for x in pool[:80]]
    if not codes:
        return {"date": prev_date, "total": 0, "matched": 0, "avg_pct": 0, "up": 0, "down": 0, "samples": []}
    secids = ",".join(("1." if c.startswith("6") else "0.") + c for c in codes)
    params = {"fltt": 2, "invt": 2, "fields": "f2,f3,f12,f14", "secids": secids}
    url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
    data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
    diff = data.get("data", {}).get("diff") or []
    cur_map = {}
    for r in diff:
        cur_map[str(r.get("f12"))] = (to_num(r.get("f3")), r.get("f14"))
    total = matched = up = down = 0
    pct_sum = 0.0
    samples = []
    for x in pool[:80]:
        code = str(x.get("c"))
        if code not in cur_map:
            continue
        pct = cur_map[code][0]
        if pct != pct:
            continue
        matched += 1
        pct_sum += pct
        if pct > 0:
            up += 1
        elif pct < 0:
            down += 1
        samples.append({"code": code, "name": cur_map[code][1], "pct": round(pct, 2), "lbc": int(x.get("lbc") or 0)})
    avg_pct = round(pct_sum / matched, 2) if matched else 0
    samples.sort(key=lambda x: -x["lbc"])
    return {"date": prev_date, "total": len(pool), "matched": matched, "avg_pct": avg_pct, "up": up, "down": down, "samples": samples[:12]}


def time_phase():
    hm = datetime.now().hour * 100 + datetime.now().minute
    if 925 <= hm < 930:
        return {"phase": "竞价结束", "window": "9:25-9:30", "tip": "看竞价高开、量比、板块联动", "active": True}
    if 930 <= hm < 1000:
        return {"phase": "早盘资金验证", "window": "9:30-10:00", "tip": "资金持续流入、板块涨停扩散，等第一次回踩不破", "active": True}
    if 1000 <= hm < 1130:
        return {"phase": "板块合力确认", "window": "10:00-11:30", "tip": "板块形成合力才做；均价线下方放弃", "active": True}
    if 1300 <= hm < 1430:
        return {"phase": "午后分歧转一致", "window": "13:00-14:30", "tip": "看分歧转一致、炸板后回封", "active": True}
    if 1430 <= hm < 1500:
        return {"phase": "尾盘封单确认", "window": "14:30 后", "tip": "封单稳不稳，强势票尾盘跳水要警惕次日低开", "active": True}
    return {"phase": "已收盘/未开盘", "window": "—", "tip": "复盘阶段，等待下一个交易窗口", "active": False}


def fetch_watchlist_ticks(stocks):
    def one(s):
        try:
            secid = ("1." if s["code"].startswith("6") else "0.") + s["code"]
            params = {
                "secid": secid,
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                "iscr": 0, "iscca": 1, "ndays": 1,
            }
            url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get?" + urllib.parse.urlencode(params)
            data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
            trends = data.get("trends") or []
            rows = [t.split(",") for t in trends]
            if not rows:
                return s
            first = rows[0]
            last = rows[-1]
            cur = float(last[2])
            avg = float(last[7]) if len(last) > 7 else cur
            auction_high = float(first[3])
            auction_low = float(first[4])
            highs = [float(r[3]) for r in rows]
            lows = [float(r[4]) for r in rows]
            prev_high = max(highs[:-1]) if len(highs) > 1 else auction_high
            recent = rows[-4:]
            recent_low = min(float(r[4]) for r in recent)
            base = float(recent[0][2]) if len(recent) >= 2 else 0
            recent_gain = (cur - base) / base * 100 if base else 0
            s.update({
                "price": cur,
                "avg": avg,
                "above_avg": cur >= avg,
                "vs_avg": round((cur / avg - 1) * 100, 2) if avg else 0,
                "break_high": cur > prev_high,
                "break_auction_high": cur > auction_high,
                "auction_high": auction_high,
                "auction_low": auction_low,
                "recent_low": recent_low,
                "recent_gain": round(recent_gain, 2),
                "day_high": max(highs),
                "day_low": min(lows),
            })
        except Exception:
            pass
        return s
    with ThreadPoolExecutor(max_workers=10) as ex:
        return list(ex.map(one, stocks))


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
            "leader_code": r.get("f140"),
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
    def __init__(self, ttl=30, fetcher=None):
        self.ttl = ttl
        self.fetcher = fetcher or fetch_snapshot
        self.lock = threading.Lock()
        self.ts = 0
        self.data = None

    def get(self, force=False):
        now = time.time()
        with self.lock:
            if force or self.data is None or (now - self.ts) > self.ttl:
                self.data = self.fetcher()
                self.ts = time.time()
            return self.data


CACHE = SnapshotCache(ttl=30)


def fetch_spot_map(codes):
    out = {}
    if not codes:
        return out
    secids = ",".join(("1." if c.startswith("6") else "0.") + c for c in codes)
    params = {"fltt": 2, "invt": 2, "fields": "f2,f3,f6,f8,f10,f12,f14,f62", "secids": secids}
    url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
    try:
        data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
        for r in data.get("data", {}).get("diff") or []:
            out[str(r.get("f12"))] = r
    except Exception:
        pass
    return out


_RT_PREV = None

def fetch_realtime():
    global _RT_PREV

    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {
            "indices": ex.submit(safe, "indices", fetch_indices),
            "breadth": ex.submit(safe, "breadth", fetch_breadth),
            "zt": ex.submit(safe, "zt", fetch_zt_pool),
            "zb": ex.submit(safe, "zb", fetch_zb_pool),
            "dt": ex.submit(safe, "dt", fetch_dt_pool),
            "industry": ex.submit(safe, "industry", fetch_industry_boards),
            "concept": ex.submit(safe, "concept", fetch_concept_boards),
            "inflow": ex.submit(safe, "inflow", lambda: fetch_stock_flow_top(po=1)),
            "yzt": ex.submit(safe, "yzt", fetch_yesterday_zt_perf),
        }
        results = {k: f.result() for k, f in futures.items()}

    def val(k):
        return results[k][1] if not isinstance(results[k], dict) else None

    errors = [str(v.get("error")) for v in results.values() if isinstance(v, dict) and "error" in v]
    indices = val("indices") or []
    breadth = val("breadth") or {"up": 0, "down": 0, "flat": 0}
    zt = val("zt") or {"tc": 0, "pool": []}
    zb = val("zb") or {"tc": 0, "pool": []}
    dt = val("dt") or {"tc": 0, "pool": []}
    industry = val("industry") or []
    concept = val("concept") or []
    inflow = val("inflow") or []
    yzt = val("yzt") or {}

    zt_pool = zt.get("pool") or []
    zt_codes = {str(x.get("c")) for x in zt_pool}
    zt_by_industry = {}
    for x in zt_pool:
        b = x.get("hybk") or "未知"
        zt_by_industry[b] = zt_by_industry.get(b, 0) + 1

    prev_map = {}
    if _RT_PREV:
        prev_map = {s["name"]: s for s in _RT_PREV.get("industry", [])}
    for s in industry:
        s["zt_count"] = zt_by_industry.get(s["name"], 0)
        s["leader_locked"] = s.get("leader_code") in zt_codes
        p = prev_map.get(s["name"])
        s["delta_pct"] = round(s["pct"] - p["pct"], 2) if p else 0
        s["delta_flow"] = round(s["flow_yi"] - p["flow_yi"], 2) if p else 0
        s["delta_zt"] = s["zt_count"] - p["zt_count"] if p else 0
    industry_top = sorted(industry, key=lambda x: -x.get("pct", -999))[:12]
    industry_flow = sorted(industry, key=lambda x: -x.get("flow_yi", -999))[:12]
    concept_top_flow = sorted(concept, key=lambda x: -x.get("flow_yi", -999))[:12]

    candidates = []
    seen = set()
    for x in sorted(zt_pool, key=lambda x: (-(int(x.get("lbc") or 0)), -(to_num(x.get("fund")) or 0))):
        code = str(x.get("c"))
        if code in seen:
            continue
        seen.add(code)
        candidates.append({
            "code": code, "name": x.get("n"),
            "pct": round(to_num(x.get("zdp")), 2),
            "flow_yi": round(to_num(x.get("fund")) / 100000000, 2),
            "amount_yi": round(to_num(x.get("amount")) / 100000000, 2),
            "turnover": round(to_num(x.get("hs")), 2),
            "vol_ratio": 0,
            "lbc": int(x.get("lbc") or 0),
            "fbt": str(x.get("fbt") or ""),
            "lbt": str(x.get("lbt") or ""),
            "zbc": int(x.get("zbc") or 0),
            "industry": x.get("hybk"),
            "source": "涨停池",
        })
    for x in inflow[:10]:
        code = str(x.get("code"))
        if code in seen:
            continue
        seen.add(code)
        candidates.append({
            "code": code, "name": x.get("name"),
            "pct": x.get("pct"),
            "flow_yi": x.get("flow_yi"),
            "amount_yi": x.get("amount_yi"),
            "turnover": x.get("turnover"),
            "vol_ratio": x.get("vol_ratio"),
            "lbc": 0, "fbt": "", "lbt": "", "zbc": 0, "industry": "",
            "source": "主力资金",
        })
    candidates = candidates[:16]
    candidates = fetch_watchlist_ticks(candidates)
    spot_map = fetch_spot_map([c["code"] for c in candidates])
    for s in candidates:
        row = spot_map.get(s["code"])
        if row:
            s["vol_ratio"] = to_num(row.get("f10"))
            s["turnover"] = to_num(row.get("f8"))
            s["main_flow"] = round(to_num(row.get("f62")) / 100000000, 2)

    for s in candidates:
        alerts = []
        if s.get("above_avg") is None:
            alerts.append("分时均价暂缺")
        elif s.get("above_avg"):
            alerts.append("站上分时均价线")
        else:
            alerts.append("均价线下方")
        if s.get("break_high"):
            alerts.append("突破日内前高")
        if s.get("break_auction_high"):
            alerts.append("突破竞价高点")
        rg = s.get("recent_gain") or 0
        if rg > 2.5:
            alerts.append(f"短线拉升{rg}%，等回踩")
        if s.get("zbc"):
            alerts.append(f"炸板{s['zbc']}次")
        if s.get("zbc") and s.get("lbt") and s.get("fbt") and int(s.get("lbt") or 0) > int(s.get("fbt") or 0):
            alerts.append("炸板后回封")
        flow_check = s.get("main_flow") if s.get("main_flow") is not None else s.get("flow_yi")
        if (s.get("vol_ratio") or 0) >= 2 and (flow_check or 0) < 0:
            alerts.append("量比大但主力净流出，警惕诱多")
        s["alerts"] = alerts

    emotion = compute_emotion(zt, zb, dt)
    phase = time_phase()
    sh = next((i for i in indices if i.get("name") == "上证指数"), {})
    top_sector = industry_flow[0] if industry_flow else {}
    def flow_value(s):
        v = s.get("main_flow")
        return v if v is not None else s.get("flow_yi")
    buy_confirm = sum(1 for s in candidates if s.get("above_avg") and (s.get("break_high") or s.get("break_auction_high")))
    fund_ok = sum(1 for s in candidates if (flow_value(s) or 0) > 0 and (s.get("vol_ratio") or 0) >= 1.5)
    trap = [s for s in candidates if (s.get("vol_ratio") or 0) >= 2 and (flow_value(s) or 0) < 0]
    signals = [
        {"name": "大盘情绪", "ok": sh.get("above_avg", False) and breadth.get("up", 0) > breadth.get("down", 0), "detail": f"上涨{breadth.get('up',0)}/下跌{breadth.get('down',0)}，炸板率{emotion['zhaban_rate']}%"},
        {"name": "板块过滤", "ok": bool(top_sector) and top_sector.get("pct", 0) > 0 and top_sector.get("flow_yi", 0) > 0 and top_sector.get("zt_count", 0) >= 3, "detail": f"{top_sector.get('name','')} {top_sector.get('pct',0):+.2f}% 主力{top_sector.get('flow_yi',0):+.2f}亿 涨停{top_sector.get('zt_count',0)}家"},
        {"name": "资金盘口", "ok": fund_ok >= 2, "detail": f"{fund_ok}只候选量比≥1.5且主力净流入为正"},
        {"name": "买点确认", "ok": buy_confirm >= 1, "detail": f"{buy_confirm}只候选站上均价线且突破前高/竞价高点"},
        {"name": "诱多预警", "ok": not trap, "detail": f"{len(trap)}只量比大但主力净流出"},
    ]

    _RT_PREV = {"industry": industry}
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rt": True,
        "indices": indices,
        "breadth": breadth,
        "emotion": emotion,
        "yesterday_zt": yzt,
        "phase": phase,
        "signals": signals,
        "industry_top": industry_top,
        "industry_flow": industry_flow,
        "concept_top_flow": concept_top_flow,
        "watchlist": candidates,
        "errors": errors,
    }

REALTIME_CACHE = SnapshotCache(ttl=30, fetcher=fetch_realtime)

def fetch_kline_hist(code):
    prefix = "sh" if code.startswith(("6", "9")) else "bj" if code.startswith(("4", "8", "92")) else "sz"
    symbol = prefix + code
    rows = []
    try:
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + urllib.parse.urlencode({"param": f"{symbol},day,,,45,qfq"})
        data = http_get_json(url, headers={"Referer": "https://gu.qq.com/"})
        node = (data.get("data") or {}).get(symbol) or {}
        rows = node.get("qfqday") or node.get("day") or []
    except Exception:
        rows = []
    if not rows:
        try:
            url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20t=/CN_MarketDataService.getKLineData?" + urllib.parse.urlencode({"symbol": symbol, "scale": 240, "ma": "no", "datalen": 45})
            text = http_get(url, headers={"Referer": "https://finance.sina.com.cn/"})
            m = re.search(r"\[(.*)\]", text, re.S)
            if m:
                rows = json.loads("[" + m.group(1) + "]")
        except Exception:
            rows = []
    out = []
    for row in rows[-45:]:
        try:
            if isinstance(row, list):
                date = row[0]
                open_ = to_num(row[1]); close = to_num(row[2])
                high = to_num(row[3]); low = to_num(row[4]); volume = to_num(row[5])
            else:
                date = row.get("day")
                open_ = to_num(row.get("open")); close = to_num(row.get("close"))
                high = to_num(row.get("high")); low = to_num(row.get("low")); volume = to_num(row.get("volume"))
            pct = 0.0
            if out:
                prev_close = out[-1]["close"]
                pct = round((close / prev_close - 1) * 100, 2) if prev_close else 0.0
            out.append({"date": date, "open": open_, "close": close, "high": high, "low": low, "volume": volume, "amount": 0.0, "pct": pct})
        except Exception:
            continue
    if len(out) >= 25:
        return out
    try:
        secid = ("1." if code.startswith("6") else "0.") + code
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": 101, "fqt": 1, "beg": "20260701", "end": "20500101",
        }
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
        data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/", "Connection": "close"})["data"]
        out = []
        for line in (data.get("klines") or []):
            p = line.split(",")
            if len(p) < 11:
                continue
            out.append({"date": p[0], "open": to_num(p[1]), "close": to_num(p[2]), "high": to_num(p[3]), "low": to_num(p[4]), "volume": to_num(p[5]), "amount": to_num(p[6]), "pct": to_num(p[8])})
        return out
    except Exception:
        return []


def fetch_volume_price_scan():
    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "stocks": ex.submit(safe, "stocks", lambda: fetch_paged(ALL_A_FS, "f2,f3,f6,f8,f10,f12,f14,f15,f16,f17,f18,f22,f62,f184,f100", limit=6000)),
            "industry": ex.submit(safe, "industry", fetch_industry_boards),
            "indices": ex.submit(safe, "indices", fetch_indices),
            "breadth": ex.submit(safe, "breadth", fetch_breadth),
            "zt": ex.submit(safe, "zt", fetch_zt_pool),
            "zb": ex.submit(safe, "zb", fetch_zb_pool),
            "dt": ex.submit(safe, "dt", fetch_dt_pool),
            "amount": ex.submit(safe, "amount", fetch_market_amount),
        }
        results = {k: f.result() for k, f in futures.items()}

    errors = [str(v.get("error")) for v in results.values() if isinstance(v, dict) and "error" in v]
    stocks = results["stocks"][1] if not isinstance(results["stocks"], dict) else []
    industry = results["industry"][1] if not isinstance(results["industry"], dict) else []
    indices = results["indices"][1] if not isinstance(results["indices"], dict) else []
    breadth = results["breadth"][1] if not isinstance(results["breadth"], dict) else {"up": 0, "down": 0, "flat": 0}
    zt = results["zt"][1] if not isinstance(results["zt"], dict) else {"tc": 0, "pool": []}
    zb = results["zb"][1] if not isinstance(results["zb"], dict) else {"tc": 0, "pool": []}
    dt = results["dt"][1] if not isinstance(results["dt"], dict) else {"tc": 0, "pool": []}
    amount = results["amount"][1] if not isinstance(results["amount"], dict) else None

    candidates = []
    for r in stocks:
        amount_v = to_num(r.get("f6"))
        turn = to_num(r.get("f8"))
        vr = to_num(r.get("f10"))
        pct = to_num(r.get("f3"))
        if amount_v < 500000000 or not (5 <= turn <= 20):
            continue
        if not (vr >= 1.5 or vr <= 0.9):
            continue
        if not (-7 <= pct <= 7):
            continue
        high = to_num(r.get("f15"))
        low = to_num(r.get("f16"))
        prev_close = to_num(r.get("f18")) or 0
        candidates.append({
            "code": r.get("f12"),
            "name": r.get("f14"),
            "close": to_num(r.get("f2")),
            "pct": pct,
            "speed": to_num(r.get("f22")),
            "vol_ratio": vr,
            "turnover": turn,
            "amount_yi": round(amount_v / 100000000, 2),
            "main_flow": round(to_num(r.get("f62")) / 100000000, 2),
            "industry": r.get("f100"),
            "high_pct": round((high / prev_close - 1) * 100, 2) if prev_close else pct,
            "low_pct": round((low / prev_close - 1) * 100, 2) if prev_close else pct,
        })
    big = sorted([c for c in candidates if c["vol_ratio"] >= 1.5], key=lambda x: -x["vol_ratio"])[:30]
    small = sorted([c for c in candidates if c["vol_ratio"] <= 0.9], key=lambda x: x["vol_ratio"])[:20]
    candidates = (big + small)[:150]

    def enrich(c):
        try:
            hist = fetch_kline_hist(c["code"])
        except Exception:
            hist = []
        if len(hist) >= 22:
            closes = [h["close"] for h in hist]
            vols = [h["volume"] for h in hist]
            highs = [h["high"] for h in hist]
            amounts = [h["amount"] for h in hist]
            today = hist[-1]
            prev5 = vols[-6:-1]
            prev5_avg = sum(prev5) / len(prev5) if prev5 else 0
            prev10 = vols[-11:-6]
            prev10_avg = sum(prev10) / len(prev10) if prev10 else 0
            c["hist_vol_ratio"] = round(today["volume"] / prev5_avg, 2) if prev5_avg else None
            c["ma20"] = round(sum(closes[-20:]) / 20, 2)
            c["high10"] = max(highs[-11:-1]) if len(highs) >= 11 else max(highs[:-1]) if len(highs) > 1 else today["high"]
            c["high20"] = max(highs[-21:-1]) if len(highs) >= 21 else c["high10"]
            c["amount20_max"] = max(amounts[-21:-1]) if len(amounts) >= 21 else max(amounts[:-1]) if len(amounts) > 1 else today["amount"]
            c["above_ma20"] = today["close"] > c["ma20"]
            c["break_high10"] = today["close"] > c["high10"]
            c["break_high20"] = today["close"] > c["high20"]
            c["amount_new20"] = today["amount"] > c["amount20_max"]
            c["vol_shrink_then_expand"] = bool(prev10_avg and prev5_avg and prev5_avg <= prev10_avg * 0.95 and today["volume"] >= prev5_avg * 1.5)
        else:
            c["hist_vol_ratio"] = None
            c["ma20"] = None
            c["above_ma20"] = None
            c["break_high10"] = None
            c["break_high20"] = None
            c["amount_new20"] = None
            c["vol_shrink_then_expand"] = None
        return c
    with ThreadPoolExecutor(max_workers=8) as ex:
        candidates = list(ex.map(enrich, candidates))

    board_map = {b["name"]: b.get("flow_yi", 0) for b in industry}
    for c in candidates:
        c["board_flow"] = board_map.get(c.get("industry"), 0)

    cats = {
        "放量上攻": [], "放量滞涨": [], "冲高回落": [],
        "缩量上涨": [], "放量下跌": [], "缩量回踩": [],
    }
    for c in candidates:
        vr = c["vol_ratio"]
        pct = c["pct"]
        flow = c.get("main_flow") or 0
        pullback = round(c.get("high_pct", pct) - pct, 2)
        tags = []
        if vr >= 2 and 1 <= pct <= 7 and (c.get("break_high10") or c.get("break_high20")) and flow > 0 and c.get("board_flow", 0) > 0:
            cats["放量上攻"].append(c); tags.append("放量上攻")
        if vr >= 2 and -0.5 <= pct <= 1.5 and (pullback >= 2 or flow < 0):
            cats["放量滞涨"].append(c); tags.append("放量滞涨")
        if c.get("high_pct", pct) >= 3 and pullback >= 2 and vr >= 1.5:
            cats["冲高回落"].append(c); tags.append("冲高回落")
        if vr <= 0.8 and pct >= 2:
            cats["缩量上涨"].append(c); tags.append("缩量上涨")
        if vr >= 2 and pct <= -1:
            cats["放量下跌"].append(c); tags.append("放量下跌")
        if vr <= 0.8 and -3 <= pct <= 0.5 and (c.get("above_ma20") or (c.get("ma20") and c.get("close", 0) >= c["ma20"] * 0.97)):
            cats["缩量回踩"].append(c); tags.append("缩量回踩")
        c["tags"] = tags

    for key in cats:
        cats[key].sort(key=lambda x: (-(x.get("hist_vol_ratio") or x["vol_ratio"]), -x.get("main_flow", 0)))
        cats[key] = cats[key][:30]

    strong_boards = sorted(industry, key=lambda x: -(x.get("flow_yi") or 0))[:10]
    emotion = compute_emotion(zt, zb, dt)
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": indices,
            "breadth": breadth,
            "emotion": emotion,
            "amount_yi": amount,
        },
        "strong_boards": strong_boards,
        "total_scanned": len(candidates),
        "categories": cats,
        "errors": errors,
    }


VOLPRICE_CACHE = SnapshotCache(ttl=120, fetcher=fetch_volume_price_scan)
def fetch_pullback_scan():
    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            "stocks": ex.submit(safe, "stocks", lambda: fetch_paged(ALL_A_FS, "f2,f3,f6,f8,f10,f12,f14,f15,f16,f18,f22,f62,f184,f100", limit=6000)),
            "industry": ex.submit(safe, "industry", fetch_industry_boards),
            "indices": ex.submit(safe, "indices", fetch_indices),
            "breadth": ex.submit(safe, "breadth", fetch_breadth),
            "zt": ex.submit(safe, "zt", fetch_zt_pool),
            "zb": ex.submit(safe, "zb", fetch_zb_pool),
            "dt": ex.submit(safe, "dt", fetch_dt_pool),
            "amount": ex.submit(safe, "amount", fetch_market_amount),
        }
        results = {k: f.result() for k, f in futures.items()}

    errors = [str(v.get("error")) for v in results.values() if isinstance(v, dict) and "error" in v]
    stocks = results["stocks"][1] if not isinstance(results["stocks"], dict) else []
    industry = results["industry"][1] if not isinstance(results["industry"], dict) else []
    indices = results["indices"][1] if not isinstance(results["indices"], dict) else []
    breadth = results["breadth"][1] if not isinstance(results["breadth"], dict) else {"up": 0, "down": 0, "flat": 0}
    zt = results["zt"][1] if not isinstance(results["zt"], dict) else {"tc": 0, "pool": []}
    zb = results["zb"][1] if not isinstance(results["zb"], dict) else {"tc": 0, "pool": []}
    dt = results["dt"][1] if not isinstance(results["dt"], dict) else {"tc": 0, "pool": []}
    amount = results["amount"][1] if not isinstance(results["amount"], dict) else None

    candidates = []
    for r in stocks:
        amount_v = to_num(r.get("f6"))
        pct = to_num(r.get("f3"))
        vr = to_num(r.get("f10"))
        if amount_v < 500000000 or not (-5 <= pct <= 3) or vr > 1.2:
            continue
        candidates.append({
            "code": r.get("f12"),
            "name": r.get("f14"),
            "close": to_num(r.get("f2")),
            "pct": pct,
            "speed": to_num(r.get("f22")),
            "vol_ratio": vr,
            "turnover": to_num(r.get("f8")),
            "amount_yi": round(amount_v / 100000000, 2),
            "main_flow": round(to_num(r.get("f62")) / 100000000, 2),
            "industry": r.get("f100"),
        })
    candidates.sort(key=lambda x: -x["amount_yi"])
    candidates = candidates[:120]

    def enrich(c):
        try:
            c["hist"] = fetch_kline_hist(c["code"])
        except Exception:
            c["hist"] = []
        return c
    with ThreadPoolExecutor(max_workers=8) as ex:
        candidates = list(ex.map(enrich, candidates))

    zt_by_industry = {}
    for x in (zt.get("pool") or []):
        b = x.get("hybk") or "未知"
        zt_by_industry[b] = zt_by_industry.get(b, 0) + 1
    hot_set = {
        b["name"] for b in industry
        if (b.get("flow_yi") or 0) > 0 and (b.get("pct") or 0) > 0
        or zt_by_industry.get(b["name"], 0) >= 1
    }
    board_flow_map = {b["name"]: b.get("flow_yi", 0) for b in industry}

    results = []
    for c in candidates:
        hist = c.get("hist") or []
        if len(hist) < 25:
            continue
        code = c["code"]
        threshold = 29.5 if code.startswith(("4", "8", "92")) else 19.5 if code.startswith(("3", "68")) else 9.8
        last20 = hist[-20:]
        limit_idx = None
        for i in range(len(last20) - 1, -1, -1):
            if (last20[i].get("pct") or 0) >= threshold:
                limit_idx = i
                break
        if limit_idx is None:
            continue
        limit_bar = last20[limit_idx]
        today = hist[-1]
        vols = [h["volume"] for h in hist]
        closes = [h["close"] for h in hist]
        lows = [h["low"] for h in hist]
        prev5 = vols[-6:-1]
        prev5_avg = sum(prev5) / len(prev5) if prev5 else 0
        hist_vr = round(today["volume"] / prev5_avg, 2) if prev5_avg else None
        if hist_vr is None or hist_vr > 0.85:
            continue
        ma20 = sum(closes[-20:]) / 20
        ma20_prev5 = sum(closes[-25:-5]) / 20 if len(closes) >= 25 else None
        close = today["close"]
        if close <= ma20:
            continue
        if ma20_prev5 is not None and ma20 <= ma20_prev5:
            continue
        recent_low = min(lows[-5:])
        prior_low = min(lows[-15:-5])
        if recent_low <= prior_low * 0.98:
            continue
        support = min(limit_bar["low"], limit_bar["close"])
        if today["low"] < support * 0.98:
            continue
        days_since = (len(last20) - 1) - limit_idx
        if days_since <= 0:
            continue
        hot = c.get("industry") in hot_set
        shrink = round((1 - hist_vr) * 10, 1) if hist_vr else 5
        trend = (5 if close > ma20 else 0) + (3 if (ma20_prev5 is not None and ma20 > ma20_prev5) else 0)
        recency = 5 if days_since <= 5 else 2 if days_since <= 10 else 1
        score = round(shrink + trend + recency + (8 if hot else 0), 1)
        tags = ["20日涨停", "上升趋势", "缩量回踩"]
        if hot:
            tags.append("市场热点")
        results.append({
            "code": code, "name": c["name"],
            "price": round(close, 2), "pct": c["pct"], "speed": c["speed"],
            "vol_ratio": c["vol_ratio"], "hist_vol_ratio": hist_vr,
            "turnover": c["turnover"], "amount_yi": c["amount_yi"],
            "main_flow": c["main_flow"], "industry": c.get("industry"),
            "ma20": round(ma20, 2), "board_flow": round(board_flow_map.get(c.get("industry"), 0), 2),
            "limit_date": limit_bar["date"], "limit_pct": round(limit_bar.get("pct") or 0, 2),
            "days_since": days_since, "hot": hot, "score": score, "tags": tags,
        })
    results.sort(key=lambda x: -x["score"])
    emotion = compute_emotion(zt, zb, dt)
    hot_boards = sorted(industry, key=lambda x: -(x.get("flow_yi") or 0))[:10]
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": indices, "breadth": breadth, "emotion": emotion, "amount_yi": amount,
        },
        "hot_boards": hot_boards,
        "scanned": len(candidates), "matched": len(results), "stocks": results,
        "errors": errors,
    }


PULLBACK_CACHE = SnapshotCache(ttl=120, fetcher=fetch_pullback_scan)
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
        elif path == "/api/version":
            self._send_json({"version": 2, "rt": True})
        elif path == "/api/refresh":
            self._send_json(CACHE.get(force=True))
        elif path == "/api/realtime":
            self._send_json(REALTIME_CACHE.get())
        elif path == "/api/realtime_refresh":
            self._send_json(REALTIME_CACHE.get(force=True))
        elif path == "/api/volprice":
            self._send_json(VOLPRICE_CACHE.get())
        elif path == "/api/volprice_refresh":
            self._send_json(VOLPRICE_CACHE.get(force=True))
        elif path == "/api/pullback":
            self._send_json(PULLBACK_CACHE.get())
        elif path == "/api/pullback_refresh":
            self._send_json(PULLBACK_CACHE.get(force=True))
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
