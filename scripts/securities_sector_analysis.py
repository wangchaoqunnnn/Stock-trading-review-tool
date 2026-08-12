# -*- coding: utf-8 -*-
"""证券板块现状分析：板块走势、成交额、个股资金、消息面。"""
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
EM_UT = "bd1d9ddb04089700cf9c27f6f7426281"


def get_text(url, headers=None, decode="utf-8", timeout=25):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(decode, errors="replace")


def get_json(url, headers=None):
    return json.loads(get_text(url, headers=headers))


def fetch_paged(fs, fields, pz=100, fid="f3"):
    rows = []
    pn = 1
    while True:
        params = {
            "pn": pn,
            "pz": pz,
            "po": 1,
            "np": 1,
            "ut": EM_UT,
            "fltt": 2,
            "invt": 2,
            "fid": fid,
            "fs": fs,
            "fields": fields,
        }
        url = "https://push2delay.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode(params)
        data = get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
        total = int(data["total"])
        diff = data.get("diff") or []
        rows.extend(diff)
        if len(rows) >= total or not diff:
            break
        pn += 1
        time.sleep(0.1)
    return rows


def board_kline(secid, lmt=80):
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
    return get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]


def stock_quote(secids, fields):
    params = {"fltt": 2, "invt": 2, "fields": fields, "secids": secids}
    url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
    data = get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
    return (data.get("data") or {}).get("diff") or []


def market_amount():
    total = 0.0
    for secid in ["1.000001", "0.399001"]:
        data = board_kline(secid, lmt=2)
        last = data["klines"][-1].split(",")
        total += float(last[6])
    return total / 1e8


def news():
    hits = []
    keywords = ["券商", "证券", "资本市场", "并购重组", "IPO", "两融", "融资余额", "降佣", "牛市", "成交额", "活跃资本市场"]
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
                        hits.append((item.get("showTime"), item.get("title"), item.get("url"), text[:180]))
            except Exception:
                pass
            time.sleep(0.1)
    return hits


def main():
    print("=" * 100)
    print(f"证券板块现状  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    print("\n【证券板块行情】")
    boards = fetch_paged("m:90+t:2+f:!50", "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f184")
    for b in boards:
        if "证券" in (b.get("f14") or ""):
            print("代码", b.get("f12"), "板块", b.get("f14"), "涨跌", b.get("f3"), "主力净流入亿", round((b.get("f62") or 0) / 1e8, 2))
            secid = "90." + b["f12"]
            data = board_kline(secid, lmt=60)
            kl = data["klines"]
            print("最近5日：")
            for row in kl[-5:]:
                p = row.split(",")
                print(p[0], "收", p[2], "涨跌", p[8], "%", "成交额亿", round(float(p[6]) / 1e8, 1))
            print("60日区间：", "最高", max(float(r.split(',')[3]) for r in kl), "最低", min(float(r.split(',')[4]) for r in kl))
            break

    print("\n【两市成交额(沪+深，亿元)】", round(market_amount(), 0))

    codes = [
        ("1.600030", "中信证券"), ("0.300059", "东方财富"), ("1.601688", "华泰证券"),
        ("1.601211", "国泰海通"), ("1.600999", "招商证券"), ("1.601066", "中信建投"),
        ("0.000776", "广发证券"), ("1.601881", "中国银河"), ("1.601995", "中金公司"),
        ("1.601901", "方正证券"), ("1.601162", "天风证券"), ("0.300033", "同花顺"),
        ("0.300803", "指南针"), ("1.688318", "财富趋势"), ("1.601519", "大智慧"),
        ("1.601099", "太平洋"), ("1.601136", "首创证券"), ("1.600958", "东方证券"),
    ]
    secids = ",".join(c for c, _ in codes)
    quotes = stock_quote(secids, "f2,f3,f6,f8,f10,f12,f14,f62,f184")
    print("\n【券商个股：涨跌/主力净流入/成交额/量比】")
    quotes.sort(key=lambda x: -((x.get("f62") or 0)))
    for q in quotes:
        print(
            f"{q.get('f12')} {q.get('f14')} 涨跌{q.get('f3')}% 主力净流入{(q.get('f62') or 0)/1e8:.2f}亿 "
            f"成交额{(q.get('f6') or 0)/1e8:.2f}亿 量比{q.get('f10')} 换手{q.get('f8')}%"
        )

    print("\n【近期券商/资本市场消息】")
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
