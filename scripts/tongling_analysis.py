# -*- coding: utf-8 -*-
"""铜陵有色(000630)个股分析：K线形态、资金、估值、铜价、消息面。"""
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
EM_UT = "bd1d9ddb04089700cf9c27f6f7426281"


def get_text(url, headers=None, decode="utf-8", timeout=25, tries=4):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode(decode, errors="replace")
        except Exception as exc:
            last = exc
            time.sleep(2.5)
    raise last


def get_json(url, headers=None):
    return json.loads(get_text(url, headers=headers))


def daily_kline(secid, lmt=100):
    symbol_map = {"0.000630": "sz000630"}
    try:
        params = {
            "secid": secid,
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": 101,
            "fqt": 1,
            "beg": 0,
            "end": 20500101,
            "lmt": lmt,
        }
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
        data = get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
        rows = []
        for item in data.get("klines", []):
            p = item.split(",")
            rows.append(
                {
                    "date": p[0],
                    "open": float(p[1]),
                    "close": float(p[2]),
                    "high": float(p[3]),
                    "low": float(p[4]),
                    "volume": float(p[5]),
                    "amount": float(p[6]),
                    "pct": float(p[8]),
                    "turnover": float(p[10]),
                }
            )
        if rows:
            return rows
    except Exception:
        pass
    symbol = symbol_map.get(secid, secid.replace(".", ""))
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{lmt},qfq"
    data = get_json(url, headers={"Referer": "https://gu.qq.com/"})
    arr = data["data"][symbol]["qfqday"]
    rows = []
    prev = None
    for item in arr:
        date = item[0]
        open_ = float(item[1])
        close = float(item[2])
        high = float(item[3])
        low = float(item[4])
        volume = float(item[5])
        pct = (close / prev["close"] - 1) * 100 if prev else 0.0
        amount = volume * 100 * close
        rows.append(
            {"date": date, "open": open_, "close": close, "high": high, "low": low, "volume": volume, "amount": amount, "pct": pct, "turnover": None}
        )
        prev = rows[-1]
    return rows


def quote(secid):
    params = {
        "fltt": 2,
        "invt": 2,
        "fields": "f2,f3,f6,f8,f9,f10,f12,f14,f17,f18,f20,f21,f23,f26,f62,f100,f103,f184",
        "secids": secid,
    }
    url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
    data = get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
    diff = (data.get("data") or {}).get("diff") or []
    return diff[0] if diff else {}


def copper_futures():
    try:
        txt = get_text(
            "https://hq.sinajs.cn/list=nf_CU0",
            headers={"Referer": "https://finance.sina.com.cn/"},
            decode="gbk",
        )
        return txt.strip()
    except Exception as exc:
        return f"ERR {exc!r}"


def news():
    hits = []
    keywords = ["铜陵有色", "铜价", "铜矿", "电解铜", "铜精矿", "加工费", "TC", "铜库存", "智利", "秘鲁", "紫金", "江西铜业"]
    for col in [348, 350, 351]:
        for page in range(1, 4):
            params = {
                "client": "web",
                "biz": "web_news_col",
                "column": col,
                "order": 1,
                "needInteractData": 0,
                "page_index": page,
                "page_size": 50,
                "req_trace": "eastmoney",
            }
            url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?" + urllib.parse.urlencode(params)
            try:
                data = get_json(url, headers={"Referer": "https://finance.eastmoney.com/"})
                for item in data.get("data", {}).get("list", []):
                    text = str(item.get("title", "")) + " " + str(item.get("summary", ""))
                    if any(k in text for k in keywords):
                        hits.append((item.get("showTime"), item.get("title"), item.get("url"), text[:220]))
            except Exception:
                pass
            time.sleep(0.1)
    return hits


def ma(values, n):
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def main():
    secid = "0.000630"
    print("=" * 100)
    print("铜陵有色 000630 个股分析")
    print("=" * 100)

    q = quote(secid)
    print("\n【最新行情】")
    print(
        f"现价 {q.get('f2')}  涨跌 {q.get('f3')}%  成交额 {(q.get('f6') or 0)/1e8:.2f}亿 "
        f"换手 {q.get('f8')}%  量比 {q.get('f10')}  主力净流入 {(q.get('f62') or 0)/1e8:.2f}亿 "
        f"净占比 {q.get('f184')}%  PE {q.get('f9')}  PB {q.get('f23')}"
    )
    print(f"总市值 {(q.get('f20') or 0)/1e8:.0f}亿  流通市值 {(q.get('f21') or 0)/1e8:.0f}亿  行业 {q.get('f100')}")
    print("概念：", q.get("f103"))

    rows = daily_kline(secid)
    closes = [r["close"] for r in rows]
    vols = [r["volume"] for r in rows]
    print("\n【最近40个交易日：收盘/涨跌/成交额/换手/量比(相对5日均量)/MA】")
    print("日期         收盘    涨跌%   成交额(亿) 换手%  量比  MA5     MA20    MA60")
    for i, r in enumerate(rows[-40:], start=len(rows) - 40):
        v5 = sum(vols[max(0, i - 5):i]) / max(1, min(5, i))
        vr = r["volume"] / v5 if v5 else 0
        ma5 = ma(closes[: i + 1], 5)
        ma20 = ma(closes[: i + 1], 20)
        ma60 = ma(closes[: i + 1], 60)
        turn = f"{r['turnover']:.2f}" if r['turnover'] is not None else "-"
        print(
            f"{r['date']} {r['close']:8.2f} {r['pct']:6.2f} {r['amount']/1e8:8.2f} "
            f"{turn:>5} {vr:5.2f} {ma5 if ma5 is None else round(ma5,2)} "
            f"{ma20 if ma20 is None else round(ma20,2)} {ma60 if ma60 is None else round(ma60,2)}"
        )

    print("\n【近5日】")
    for r in rows[-5:]:
        turn5 = f"{r['turnover']:.2f}" if r['turnover'] is not None else "-"
        print(f"{r['date']} 开{r['open']:.2f} 收{r['close']:.2f} 高{r['high']:.2f} 低{r['low']:.2f} 涨跌{r['pct']:.2f}% 换手{turn5}%")

    print("\n【区间统计】")
    if rows:
        last60 = rows[-60:]
        print("60日最高:", max(r["high"] for r in last60), "最低:", min(r["low"] for r in last60))
        print("60日涨幅:", round((rows[-1]["close"] / rows[-60]["close"] - 1) * 100, 2), "%")
        print("20日涨幅:", round((rows[-1]["close"] / rows[-20]["close"] - 1) * 100, 2), "%")

    print("\n【沪铜连续(新浪)】")
    print(copper_futures())

    print("\n【近期铜/有色消息面】")
    seen = set()
    for show_time, title, url, text in news():
        if (show_time, title) in seen:
            continue
        seen.add((show_time, title))
        print(f"[{show_time}] {title}")
        print("  ", text)
        print("  ", url)
        print()


if __name__ == "__main__":
    main()
