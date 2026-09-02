# -*- coding: utf-8 -*-
"""东方财富公开行情数据抓取。

每个函数对应原 server.py 中同名函数，输出结构保持完全一致。
"""
import json
import re
import time
import urllib.parse
from datetime import datetime, timedelta

from .config import ALL_A_FS, EMEX_UT, INDEX_UT, NEWS_KEYWORDS
from .net import fetch_paged, http_get, http_get_json, race_fns, ttl_cache
from .utils import to_num

# 指数分时/日K回退查询使用的基础字段串
_TRENDS_PARAMS = {
    "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
    "iscr": 0, "iscca": 1, "ndays": 1,
}

# 六大指数（用于指数快照）
INDICES = [
    ("上证指数", "1.000001"),
    ("深证成指", "0.399001"),
    ("创业板指", "0.399006"),
    ("科创50", "1.000688"),
    ("沪深300", "1.000300"),
    ("北证50", "0.899050"),
]


@ttl_cache(15)
def fetch_indices():
    """指数快照：优先分时接口取最新价与分时均价，失败回退 ulist 行情。"""
    indices = INDICES
    out = []
    for name, secid in indices:
        try:
            params = {
                "secid": secid,
                "ut": INDEX_UT,
                **_TRENDS_PARAMS,
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


@ttl_cache(15)
def fetch_market_amount():
    """两市（上证+深证）成交额合计，单位亿。"""
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


@ttl_cache(15)
def fetch_breadth(date=None):
    """涨跌家数分布（date 可选，默认当日，YYYYMMDD）。"""
    date = date or datetime.now().strftime("%Y%m%d")
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


def fetch_ex_pool(path, date=None):
    """东方财富 push2ex 池子接口（涨停池/炸板池/跌停池）翻页抓取（并行）。"""
    date = date or datetime.now().strftime("%Y%m%d")

    def one(page):
        url = (
            f"https://push2ex.eastmoney.com/{path}?ut={EMEX_UT}&dpt=wz.ztzt"
            f"&Pageindex={page}&pagesize=100&sort=fbt%3Aasc&date={date}"
        )
        d = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
        dd = d.get("data") or {}
        return (dd.get("pool") or []), int(dd.get("tc") or 0)

    first_pool, tc = one(0)
    pool = list(first_pool)
    pages = min(8, (max(tc, len(pool)) + 99) // 100)
    if pages > 1 and len(pool) < tc:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as ex:
            for rows, _ in ex.map(one, range(1, pages)):
                pool.extend(rows)
                if len(pool) >= tc:
                    break
    return {"tc": tc, "pool": pool}


@ttl_cache(15)
def fetch_zt_pool():
    return fetch_ex_pool("getTopicZTPool")


@ttl_cache(15)
def fetch_zb_pool():
    return fetch_ex_pool("getTopicZBPool")


@ttl_cache(15)
def fetch_dt_pool():
    return fetch_ex_pool("getTopicDTPool")


def find_previous_zt_pool():
    """向前找最近一个有涨停数据的交易日。"""
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


@ttl_cache(15)
def fetch_yesterday_zt_perf():
    """昨日涨停股今日溢价统计。"""
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


def board_rows(rows):
    """板块行数据标准化（行业/概念通用）。"""
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


@ttl_cache(15)
def fetch_industry_boards():
    rows = fetch_paged(
        "m:90+t:2+f:!50",
        "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f184,f104,f105,f128,f141",
    )
    return board_rows(rows)


@ttl_cache(15)
def fetch_concept_boards():
    rows = fetch_paged(
        "m:90+t:3+f:!50",
        "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f184,f104,f105,f128,f141",
    )
    return board_rows(rows)


@ttl_cache(15)
def fetch_stock_flow_top(po=1, pz=40):
    """个股主力净流入榜（po=1 净流入榜，po=0 净流出榜）。"""
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
    """当日财经快讯（按关键词过滤、去重）。"""
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


def fetch_spot_map(codes, fields="f2,f3,f6,f8,f10,f12,f14,f62"):
    """批量获取个股实时行情，返回 code -> 行情行。

    fields 可选：需要成交量(f5)时可传入扩展字段串（默认保持历史行为）。
    """
    out = {}
    if not codes:
        return out
    secids = ",".join(("1." if c.startswith("6") else "0.") + c for c in codes)
    params = {"fltt": 2, "invt": 2, "fields": fields, "secids": secids}
    url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
    try:
        data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
        for r in data.get("data", {}).get("diff") or []:
            out[str(r.get("f12"))] = r
    except Exception:
        pass
    return out


def fetch_amount_minutes(secid, ndays=2):
    """指数分时每分钟成交额（trends2 行[6]），按日期分组。

    返回 {date: [(HH:MM, 每分钟成交额元), ...]}。push2his 与 push2delay 并发，
    谁先成功用谁（push2his 优先，支持多日）。
    """
    params = {
        "secid": secid,
        "ut": INDEX_UT,
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "iscr": 0, "iscca": 1, "ndays": ndays,
    }

    def _one(host):
        try:
            url = f"https://{host}/api/qt/stock/trends2/get?" + urllib.parse.urlencode(params)
            data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"}, tries=1, timeout=8)
            trends = (data.get("data") or {}).get("trends") or []
            out = {}
            for t in trends:
                p = t.split(",")
                if len(p) < 7:
                    continue
                day, tm = p[0][:10], p[0][11:16]
                out.setdefault(day, []).append((tm, to_num(p[6])))
            return out or None
        except Exception:
            return None

    return race_fns([lambda: _one("push2his.eastmoney.com"), lambda: _one("push2delay.eastmoney.com")], prefer=0) or {}


def _em_kline_rows(klines, end_date=None):
    """东财 kline csv 行解析（date,open,close,high,low,vol,amount,...）。"""
    out = []
    for line in klines or []:
        p = line.split(",")
        if len(p) < 11:
            continue
        out.append({"date": p[0], "open": to_num(p[1]), "close": to_num(p[2]),
                    "high": to_num(p[3]), "low": to_num(p[4]), "volume": to_num(p[5]),
                    "amount": to_num(p[6]), "pct": to_num(p[8])})
    if end_date:
        out = [r for r in out if r["date"] <= end_date]
    return out


@ttl_cache(15)
def fetch_kline_hist(code, limit=45, end_date=None):
    """日K线历史：东财/腾讯/新浪三源并发，谁先成功用谁（东财优先，失败快速切换备源）。

    end_date: "YYYY-MM-DD" 时返回截至该日期的K线（历史回放用）。
    """
    prefix = "sh" if code.startswith(("6", "9")) else "bj" if code.startswith(("4", "8", "92")) else "sz"
    symbol = prefix + code

    def _tencent():
        try:
            param = f"{symbol},day,{end_date},,{limit},qfq" if end_date else f"{symbol},day,,,{limit},qfq"
            url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + urllib.parse.urlencode({"param": param})
            data = http_get_json(url, headers={"Referer": "https://gu.qq.com/"}, tries=1, timeout=8)
            node = (data.get("data") or {}).get(symbol) or {}
            rows = node.get("qfqday") or node.get("day") or []
            out = _parse_kline_list(rows[-limit:])
            if end_date:
                out = [r for r in out if r["date"] <= end_date]
            return out if len(out) >= 25 else None
        except Exception:
            return None

    def _sina():
        try:
            url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20t=/CN_MarketDataService.getKLineData?" + urllib.parse.urlencode({"symbol": symbol, "scale": 240, "ma": "no", "datalen": min(max(limit * 2, 45), 1000)})
            text = http_get(url, headers={"Referer": "https://finance.sina.com.cn/"}, tries=1, timeout=8)
            m = re.search(r"\[(.*)\]", text, re.S)
            if not m:
                return None
            out = _parse_kline_list(json.loads("[" + m.group(1) + "]")[-limit:])
            if end_date:
                out = [r for r in out if r["date"] <= end_date]
            return out if len(out) >= 25 else None
        except Exception:
            return None

    def _em():
        try:
            secid = ("1." if code.startswith("6") else "0.") + code
            params = {
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 101, "fqt": 1, "beg": "20260701",
                "end": end_date.replace("-", "") if end_date else "20500101",
            }
            url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
            data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/", "Connection": "close"}, tries=1, timeout=8)
            out = _em_kline_rows((data.get("data") or {}).get("klines") or [], end_date)
            return out if len(out) >= 25 else None
        except Exception:
            return None

    return race_fns([_em, _tencent, _sina], prefer=0) or []


def _parse_kline_list(rows):
    """把 K 线行转为字典行，兼容 list（腾讯/东财）与 dict（新浪）两种格式。"""
    out = []
    for row in rows:
        try:
            if isinstance(row, list):
                out.append({
                    "date": row[0],
                    "open": to_num(row[1]), "close": to_num(row[2]),
                    "high": to_num(row[3]), "low": to_num(row[4]),
                    "volume": to_num(row[5]), "amount": 0.0,
                })
            else:
                out.append({
                    "date": row.get("day"),
                    "open": to_num(row.get("open")), "close": to_num(row.get("close")),
                    "high": to_num(row.get("high")), "low": to_num(row.get("low")),
                    "volume": to_num(row.get("volume")), "amount": to_num(row.get("amount") or 0),
                })
        except Exception:
            continue
    return out


@ttl_cache(15)
def fetch_long_kline(code, limit=250, end_date=None):
    """长周期日K线（用于突破新高判定）。

    东财/腾讯/新浪三源并发，谁先成功用谁（东财优先，失败快速切换备源）。
    end_date: "YYYY-MM-DD" 时返回截至该日期的K线。
    """
    prefix = "sh" if code.startswith(("6", "9")) else "bj" if code.startswith(("4", "8", "92")) else "sz"
    symbol = prefix + code

    def _tencent():
        try:
            param = f"{symbol},day,{end_date},,{limit},qfq" if end_date else f"{symbol},day,,,{limit},qfq"
            url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + urllib.parse.urlencode({"param": param})
            data = http_get_json(url, headers={"Referer": "https://gu.qq.com/"}, tries=1, timeout=8)
            node = (data.get("data") or {}).get(symbol) or {}
            rows = node.get("qfqday") or node.get("day") or []
            out = _parse_kline_list(rows[-limit:])
            if end_date:
                out = [r for r in out if r["date"] <= end_date]
            return out if len(out) >= 25 else None
        except Exception:
            return None

    def _em():
        try:
            ref = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
            beg = (ref - timedelta(days=int(limit * 1.6) + 30)).strftime("%Y%m%d")
            secid = ("1." if code.startswith("6") else "0.") + code
            params = {
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 101, "fqt": 1, "beg": beg,
                "end": end_date.replace("-", "") if end_date else "20500101",
            }
            url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
            data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/", "Connection": "close"}, tries=1, timeout=8)
            out = _em_kline_rows((data.get("data") or {}).get("klines") or [], end_date)
            return out if len(out) >= 25 else None
        except Exception:
            return None

    def _sina():
        try:
            datalen = min(max(limit * 2, 100), 1000)
            url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20t=/CN_MarketDataService.getKLineData?" + urllib.parse.urlencode({"symbol": symbol, "scale": 240, "ma": "no", "datalen": datalen})
            text = http_get(url, headers={"Referer": "https://finance.sina.com.cn/"}, tries=1, timeout=8)
            m = re.search(r"\[(.*)\]", text, re.S)
            if not m:
                return None
            out = _parse_kline_list(json.loads("[" + m.group(1) + "]"))
            if end_date:
                out = [r for r in out if r["date"] <= end_date]
            return out if len(out) >= 25 else None
        except Exception:
            return None

    return race_fns([_em, _tencent, _sina], prefer=0) or []


@ttl_cache(15)
def fetch_fflow_daykline(secid, limit=0):
    """主力资金流历史（日线）。host 并发 + 短超时 + 15s 缓存。"""
    params = {
        "lmt": limit, "klt": 101, "secid": secid,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
    }

    def _one(host):
        try:
            url = f"https://{host}/api/qt/stock/fflow/daykline/get?" + urllib.parse.urlencode(params)
            data = http_get_json(url, headers={"Referer": "https://data.eastmoney.com/zjlx/detail.html"}, tries=1, timeout=8)
            rows = (data.get("data") or {}).get("klines") or []
            if rows:
                _note_history_ok()
                return rows
            return None
        except Exception:
            _note_history_fail()
            return None

    return race_fns([lambda h=h: _one(h) for h in _history_hosts()], prefer=0) or []


@ttl_cache(15)
def fetch_board_kline(code, limit=45, end_date=None):
    """板块日K线（东财 kline 接口，secid=90.BKxxxx）。host 并发 + 短超时 + 15s 缓存。"""
    params = {
        "secid": "90." + code,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": 101, "fqt": 1, "end": end_date.replace("-", "") if end_date else "20500101", "lmt": limit,
    }

    def _one(host):
        try:
            url = f"https://{host}/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
            data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/", "Connection": "close"}, tries=1, timeout=8)
            out = _em_kline_rows((data.get("data") or {}).get("klines") or [], end_date)
            if out:
                _note_history_ok()
                return out
            return None
        except Exception:
            _note_history_fail()
            return None

    return race_fns([lambda h=h: _one(h) for h in _history_hosts()], prefer=0) or []


def fetch_index_kline(secid, limit=45, end_date=None):
    """指数日K线。东财/腾讯两源并发，谁先成功用谁（东财优先）。返回 [{date, open, close, high, low, volume, amount, pct}]。"""

    def _tencent():
        try:
            prefix = "sh" if secid.startswith("1.") else "sz" if secid.startswith("0.") else "bj"
            symbol = prefix + secid.split(".")[1]
            param = f"{symbol},day,{end_date},,{limit},qfq" if end_date else f"{symbol},day,,,{limit},qfq"
            url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + urllib.parse.urlencode({"param": param})
            data = http_get_json(url, headers={"Referer": "https://gu.qq.com/"}, tries=1, timeout=8)
            node = (data.get("data") or {}).get(symbol) or {}
            rows = node.get("qfqday") or node.get("day") or []
            out = []
            prev = None
            for row in rows[-limit:]:
                item = {"date": row[0], "open": to_num(row[1]), "close": to_num(row[2]),
                        "high": to_num(row[3]), "low": to_num(row[4]), "volume": to_num(row[5]), "amount": 0.0}
                item["pct"] = round((item["close"] / prev - 1) * 100, 2) if prev else 0.0
                prev = item["close"]
                out.append(item)
            if end_date:
                out = [r for r in out if r["date"] <= end_date]
            return out if len(out) >= 2 else None
        except Exception:
            return None

    def _em():
        try:
            params = {
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 101, "fqt": 1, "beg": "20240101",
                "end": end_date.replace("-", "") if end_date else "20500101",
                "lmt": limit,
            }
            for host in _history_hosts():
                try:
                    url = f"https://{host}/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
                    data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/", "Connection": "close"}, tries=1, timeout=8)
                    out = _em_kline_rows((data.get("data") or {}).get("klines") or [], end_date)
                    if out:
                        _note_history_ok()
                        return out
                except Exception:
                    _note_history_fail()
                    continue
            return None
        except Exception:
            return None

    return race_fns([_em, _tencent], prefer=0) or []


# ---------- 历史接口熔断（push2his 连续失败时短暂跳过，避免扫描被重试拖垮） ----------

_HISTORY_STATE = {"fails": 0, "skip_push2his_until": 0.0}


def _history_hosts():
    """返回待尝试的历史接口 host 列表（熔断生效时跳过 push2his）。"""
    if time.time() < _HISTORY_STATE["skip_push2his_until"]:
        return ("push2delay.eastmoney.com",)
    return ("push2his.eastmoney.com", "push2delay.eastmoney.com")


def _note_history_fail():
    _HISTORY_STATE["fails"] += 1
    if _HISTORY_STATE["fails"] >= 8:
        _HISTORY_STATE["skip_push2his_until"] = time.time() + 300  # 5 分钟内跳过
        _HISTORY_STATE["fails"] = 0


def _note_history_ok():
    _HISTORY_STATE["fails"] = 0
