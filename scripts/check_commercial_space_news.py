# -*- coding: utf-8 -*-
"""检索今日商业航天相关消息与板块资金去向。"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

KEYWORDS = ["商业航天", "航天", "卫星", "火箭", "发射", "SpaceX", "星网", "千帆", "星座", "星链", "Starship", "低轨"]


def get_text(url, headers=None, decode="utf-8", timeout=25):
    h = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept": "*/*",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(decode, errors="replace")


def em_news():
    hits = []
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
                data = json.loads(get_text(url, headers={"Referer": "https://finance.eastmoney.com/"}))
                for item in data.get("data", {}).get("list", []):
                    if not str(item.get("showTime", "")).startswith("2026-08-03"):
                        continue
                    text = str(item.get("title", "")) + " " + str(item.get("summary", ""))
                    if any(k in text for k in KEYWORDS):
                        hits.append((item.get("showTime"), item.get("title"), item.get("url"), text[:200]))
            except Exception as exc:
                pass
            time.sleep(0.15)
    return hits


def sina_zhibo():
    hits = []
    for page in range(1, 4):
        url = (
            "https://zhibo.sina.com.cn/api/zhibo/feed?"
            + urllib.parse.urlencode(
                {"page": page, "page_size": 100, "zhibo_id": 152, "tag_id": 0, "dire": "f", "dpc": 1}
            )
        )
        try:
            data = json.loads(get_text(url, headers={"Referer": "https://finance.sina.com.cn/7x24/"}))
            feed = data["result"]["data"]["feed"]["list"]
            for item in feed:
                rich = str(item.get("rich_text", "")) or ""
                tag = item.get("tag") or []
                tag_text = ""
                if isinstance(tag, list):
                    tag_text = " ".join(str(t.get("name", "")) for t in tag if isinstance(t, dict))
                text = rich + " " + tag_text
                if any(k in text for k in KEYWORDS):
                    hits.append((item.get("create_time"), rich[:250]))
        except Exception as exc:
            pass
        time.sleep(0.15)
    return hits


def board_flow():
    params = {
        "pn": 1,
        "pz": 100,
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": "b:BK0963",
        "fields": "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f184",
    }
    url = "https://push2delay.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode(params)
    data = json.loads(get_text(url, headers={"Referer": "https://quote.eastmoney.com/"}))
    diff = data["data"]["diff"]
    rows = []
    for r in diff:
        rows.append(
            {
                "code": r.get("f12"),
                "name": r.get("f14"),
                "pct": r.get("f3"),
                "flow": r.get("f62"),
                "amount": r.get("f6"),
                "ratio": r.get("f184"),
            }
        )
    rows.sort(key=lambda x: -(x["flow"] or 0))
    return rows


def main():
    print("=== 东财今日快讯命中 ===")
    for show_time, title, url, text in em_news():
        print(f"[{show_time}] {title}")
        print("  ", text)
        print("  ", url)
        print()

    print("=== 新浪7x24命中 ===")
    for create_time, text in sina_zhibo():
        print(f"[{create_time}] {text}")
        print()

    print("=== 商业航天板块主力净流入TOP20 ===")
    rows = board_flow()
    for r in rows[:20]:
        print(f"{r['code']} {r['name']} 涨跌{r['pct']}% 主力净流入{r['flow']/1e8:.2f}亿 成交额{r['amount']/1e8:.2f}亿 净占比{r['ratio']}%")
    print("=== 涨幅TOP15 ===")
    rows.sort(key=lambda x: -(x["pct"] or -999))
    for r in rows[:15]:
        print(f"{r['code']} {r['name']} 涨跌{r['pct']}% 主力净流入{r['flow']/1e8:.2f}亿 成交额{r['amount']/1e8:.2f}亿")


if __name__ == "__main__":
    main()
