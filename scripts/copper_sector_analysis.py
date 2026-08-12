# -*- coding: utf-8 -*-
"""有色/铜板块当日快照：指数、行业板块、铜股、沪铜期货、消息面。"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

EM_UT = "bd1d9ddb04089700cf9c27f6f7426281"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


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
        time.sleep(0.12)
    return rows


def index_snapshot():
    indices = [
        ("上证指数", "1.000001"),
        ("深证成指", "0.399001"),
        ("创业板指", "0.399006"),
        ("科创50", "1.000688"),
    ]
    out = []
    for name, secid in indices:
        params = {
            "secid": secid,
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "iscr": 0,
            "iscca": 1,
            "ndays": 1,
        }
        url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get?" + urllib.parse.urlencode(params)
        data = get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
        pre_close = float(data["preClose"])
        trends = data.get("trends") or []
        last = trends[-1].split(",")
        cur = float(last[2])
        out.append((name, pre_close, cur, (cur / pre_close - 1) * 100, data.get("time", "")))
    return out


def boards():
    rows = fetch_paged(
        "m:90+t:2+f:!50",
        "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f66,f72,f78,f84,f104,f105,f128,f140,f141",
    )
    out = []
    for r in rows:
        out.append(
            {
                "code": r.get("f12"),
                "name": r.get("f14"),
                "pct": r.get("f3"),
                "gap": r.get("f17"),
                "prev": r.get("f18"),
                "flow": r.get("f62"),
                "amount": r.get("f6"),
                "ratio": r.get("f184"),
                "leader": r.get("f128"),
                "leader_pct": r.get("f141"),
            }
        )
    return out


def copper_stocks():
    codes = [
        ("601899", "紫金矿业"),
        ("600362", "江西铜业"),
        ("000878", "云南铜业"),
        ("000630", "铜陵有色"),
        ("603993", "洛阳钼业"),
        ("601168", "西部矿业"),
        ("000737", "北方铜业"),
        ("600961", "株冶集团"),
        ("000060", "中金岭南"),
        ("601600", "中国铝业"),
        ("002203", "海亮股份"),
        ("600577", "精达股份"),
        ("002171", "楚江新材"),
        ("601137", "博威合金"),
        ("603527", "众源新材"),
        ("601609", "金田股份"),
        ("601618", "中国中冶"),
        ("000657", "中钨高新"),
    ]
    secids = ",".join(("1." if c.startswith("6") else "0.") + c for c, _ in codes)
    params = {
        "fltt": 2,
        "invt": 2,
        "fields": "f2,f3,f4,f6,f8,f10,f12,f14,f15,f16,f17,f18,f62,f184",
        "secids": secids,
    }
    url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
    data = get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
    diff = data.get("data", {}).get("diff") or []
    rows = []
    for r in diff:
        rows.append(
            {
                "code": r.get("f12"),
                "name": r.get("f14"),
                "pct": r.get("f3"),
                "amount": r.get("f6"),
                "flow": r.get("f62"),
                "ratio": r.get("f184"),
                "turnover": r.get("f8"),
                "volume_ratio": r.get("f10"),
            }
        )
    return rows


def futures():
    try:
        text = get_text(
            "https://hq.sinajs.cn/list=nf_CU0",
            headers={"Referer": "https://finance.sina.com.cn/"},
            decode="gbk",
        )
        return text.strip()
    except Exception as exc:
        return f"ERR {exc!r}"


def news(today):
    hits = []
    keywords = ["铜", "有色", "铜价", "铜矿", "紫金", "江西铜业", "智利", "秘鲁", "关税", "铜关税", "LME", "沪铜"]
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
                    if not str(item.get("showTime", "")).startswith(today):
                        continue
                    text = str(item.get("title", "")) + " " + str(item.get("summary", ""))
                    if any(k in text for k in keywords):
                        hits.append((item.get("showTime"), item.get("title"), item.get("url"), text[:220]))
            except Exception:
                pass
            time.sleep(0.12)
    return hits


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print("=" * 90)
    print(f"有色/铜板块快照  {today}  {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 90)

    print("\n【指数】")
    for name, pre, cur, pct, ts in index_snapshot():
        print(f"{name} 昨收{pre:.2f} 最新{cur:.2f} 涨跌{pct:.2f}%")

    print("\n【行业板块中含“有色/铜/金属”名称】")
    all_boards = boards()
    matched = [b for b in all_boards if any(k in b["name"] for k in ["有色", "铜", "金属", "工业金属", "小金属"])]
    matched.sort(key=lambda x: -(x["pct"] or -999))
    for b in matched[:25]:
        print(
            f"{b['name']} 涨跌{b['pct']}% 高开{((b['gap']/b['prev']-1)*100) if b['prev'] else 0:.2f}% "
            f"主力净流入{b['flow']/1e8:.2f}亿 领涨{b['leader']} {b['leader_pct']}%"
        )

    print("\n【有色/工业金属 行业主力净流入TOP】")
    matched.sort(key=lambda x: -(x["flow"] or -999))
    for b in matched[:15]:
        print(f"{b['name']} 涨跌{b['pct']}% 主力净流入{b['flow']/1e8:.2f}亿 净占比{b['ratio']}%")

    print("\n【铜相关个股】")
    rows = copper_stocks()
    rows.sort(key=lambda x: -(x["flow"] or -999))
    print("--- 按主力净流入 ---")
    for r in rows:
        print(
            f"{r['code']} {r['name']} 涨跌{r['pct']}% 主力净流入{r['flow']/1e8:.2f}亿 "
            f"净占比{r['ratio']}% 成交额{r['amount']/1e8:.2f}亿 换手{r['turnover']}% 量比{r['volume_ratio']}"
        )

    print("\n【沪铜连续(新浪)】")
    print(futures())

    print("\n【今日消息面：铜/有色相关】")
    for show_time, title, url, text in news(today):
        print(f"[{show_time}] {title}")
        print("  ", text)
        print("  ", url)
        print()


if __name__ == "__main__":
    main()
