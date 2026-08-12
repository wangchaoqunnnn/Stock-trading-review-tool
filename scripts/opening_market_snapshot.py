# -*- coding: utf-8 -*-
"""
开盘集合竞价与板块强弱快照
数据源：东方财富（行情、资金流、涨停池、快讯）
用法：python scripts/opening_market_snapshot.py --date 20260803
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime

import akshare as ak
import pandas as pd

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
EM_UT = "bd1d9ddb04089700cf9c27f6f7426281"


def http_get_json(url, timeout=30, tries=8):
    for i in range(tries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/", "Accept": "*/*", "Connection": "close"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3.0)


def clist_get(params):
    url = "https://push2delay.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode(params)
    return http_get_json(url)


def fetch_paged(fs, fields, pz=100, fid="f3"):
    rows = []
    pn = 1
    total = None
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
        data = clist_get(params)["data"]
        total = int(data["total"])
        diff = data.get("diff") or []
        rows.extend(diff)
        if len(rows) >= total or not diff:
            break
        pn += 1
        time.sleep(0.12)
    return rows


def to_num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def fetch_index_auction():
    indices = [
        ("上证指数", "1.000001"),
        ("深证成指", "0.399001"),
        ("创业板指", "0.399006"),
        ("沪深300", "1.000300"),
        ("科创50", "1.000688"),
        ("北证50", "0.899050"),
    ]
    result = []
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
        data = http_get_json(url)["data"]
        pre_close = float(data["preClose"])
        trends = data.get("trends") or []
        first = trends[0].split(",") if trends else None
        last = trends[-1].split(",") if trends else None
        if not first:
            continue
        open_price = float(first[1])
        open_amount = float(first[6]) if len(first) > 6 else 0.0
        open_volume = float(first[5]) if len(first) > 5 else 0.0
        current = float(last[2]) if last else open_price
        result.append(
            {
                "指数": name,
                "昨收": pre_close,
                "竞价开盘": open_price,
                "竞价高开%": round((open_price / pre_close - 1) * 100, 2),
                "竞价成交额(亿)": round(open_amount / 100000000, 2),
                "竞价成交量(万手)": round(open_volume / 10000, 2),
                "最新": current,
                "当前涨跌%": round((current / pre_close - 1) * 100, 2),
                "快照时间": data.get("time", ""),
            }
        )
    return result


def board_rows(rows):
    out = []
    for r in rows:
        f18 = to_num(r.get("f18"))
        f17 = to_num(r.get("f17"))
        gap = (f17 / f18 - 1) * 100 if f18 and f18 > 0 else 0.0
        out.append(
            {
                "代码": r.get("f12"),
                "板块": r.get("f14"),
                "最新": to_num(r.get("f2")),
                "涨跌%": to_num(r.get("f3")),
                "高开%": round(gap, 2),
                "成交额(亿)": round(to_num(r.get("f6")) / 100000000, 2),
                "换手%": to_num(r.get("f8")),
                "量比": to_num(r.get("f10")),
                "主力净流入(亿)": round(to_num(r.get("f62")) / 100000000, 2),
                "超大单(亿)": round(to_num(r.get("f66")) / 100000000, 2),
                "大单(亿)": round(to_num(r.get("f72")) / 100000000, 2),
                "中单(亿)": round(to_num(r.get("f78")) / 100000000, 2),
                "小单(亿)": round(to_num(r.get("f84")) / 100000000, 2),
                "上涨家数": r.get("f104"),
                "下跌家数": r.get("f105"),
                "领涨股": r.get("f128"),
                "领涨股代码": r.get("f140"),
                "领涨涨幅%": to_num(r.get("f141")),
            }
        )
    return out


def spot_rows(rows):
    out = []
    for r in rows:
        f17 = to_num(r.get("f17"))
        f18 = to_num(r.get("f18"))
        f3 = to_num(r.get("f3"))
        gap = (f17 / f18 - 1) * 100 if f18 and f18 > 0 else float("nan")
        out.append(
            {
                "代码": r.get("f12"),
                "名称": r.get("f14"),
                "最新": to_num(r.get("f2")),
                "涨跌%": f3,
                "今开": f17,
                "昨收": f18,
                "高开%": gap,
                "成交额(亿)": round(to_num(r.get("f6")) / 100000000, 3),
                "换手%": to_num(r.get("f8")),
                "量比": to_num(r.get("f10")),
                "主力净流入(亿)": round(to_num(r.get("f62")) / 100000000, 3),
                "主力净占比%": to_num(r.get("f184")),
            }
        )
    return out


def market_breadth(stocks):
    total = len(stocks)
    up = sum(1 for s in stocks if s["涨跌%"] > 0)
    down = sum(1 for s in stocks if s["涨跌%"] < 0)
    flat = total - up - down
    high_open = sum(1 for s in stocks if s["高开%"] > 0.05)
    low_open = sum(1 for s in stocks if s["高开%"] < -0.05)
    flat_open = total - high_open - low_open
    amount = sum(s["成交额(亿)"] for s in stocks if s["成交额(亿)"] == s["成交额(亿)"])
    return {
        "总数": total,
        "上涨": up,
        "下跌": down,
        "平盘": flat,
        "高开": high_open,
        "低开": low_open,
        "平开": flat_open,
        "总成交额(亿)": round(amount, 2),
    }


def format_zt_pool(df, date):
    if df is None or df.empty:
        return None
    df = df.copy()
    df["首次封板时间"] = df["首次封板时间"].astype(str)
    jingjia = df[df["首次封板时间"].str.startswith("0925")].copy()
    grp = (
        df.groupby("所属行业")
        .agg(涨停家数=("代码", "count"),
             竞价涨停=("首次封板时间", lambda x: int(x.astype(str).str.startswith("0925").sum())),
             封板资金合计亿=("封板资金", lambda x: round(x.sum() / 100000000, 2)),
             最高连板=("连板数", "max"))
        .sort_values(["涨停家数", "封板资金合计亿"], ascending=False)
        .reset_index()
    )
    return {
        "total": len(df),
        "jingjia_total": len(jingjia),
        "by_board": grp.head(12),
        "top_liangban": df.sort_values("连板数", ascending=False).head(12),
        "auction_sealed": jingjia.sort_values("封板资金", ascending=False).head(12),
    }


def fetch_news(today):
    items = []
    for page in range(1, 4):
        params = {
            "client": "web",
            "biz": "web_news_col",
            "column": 350,
            "order": 1,
            "needInteractData": 0,
            "page_index": page,
            "page_size": 30,
            "req_trace": "eastmoney",
        }
        url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?" + urllib.parse.urlencode(params)
        try:
            data = http_get_json(url)
            items.extend(data.get("data", {}).get("list", []))
        except Exception:
            break
        time.sleep(0.15)
    keywords = [
        "A股", "两市", "涨停", "成交", "资金", "央行", "货币政策", "风电", "光伏", "电网",
        "电力", "新能源", "储能", "特高压", "半导体", "芯片", "稀土", "军工", "航天",
        "农业", "教育", "民爆", "人工智能", "AI", "机器人", "华为", "特斯拉", "出口",
    ]
    today_items = [x for x in items if str(x.get("showTime", "")).startswith(today)]
    hits = []
    for x in today_items:
        text = (str(x.get("title", "")) + " " + str(x.get("summary", "")))
        if any(k in text for k in keywords):
            hits.append(
                {
                    "时间": x.get("showTime", ""),
                    "标题": x.get("title", ""),
                    "摘要": (x.get("summary", "") or "")[:140],
                    "链接": x.get("url", ""),
                }
            )
    return hits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYYMMDD")
    args = parser.parse_args()
    today = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:8]}"

    print("=" * 100)
    print(f"A股开盘集合竞价与板块强弱快照  {today}  (东财实时数据)")
    print("=" * 100)

    print("\n【一、主要指数：09:30竞价成交与高开】")
    for row in fetch_index_auction():
        print(row)

    print("\n【二、沪深A股开盘结构】")
    all_rows = fetch_paged(
        "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "f2,f3,f6,f8,f10,f12,f14,f15,f16,f17,f18,f62,f184",
    )
    stocks = spot_rows(all_rows)
    breadth = market_breadth(stocks)
    print(breadth)
    gap_top = sorted([s for s in stocks if s["高开%"] == s["高开%"]], key=lambda x: -x["高开%"])[:20]
    print("--- 高开幅度TOP20 ---")
    for s in gap_top:
        print(f"{s['代码']} {s['名称']} 高开{s['高开%']:.2f}% 现{s['涨跌%']:.2f}% 额{s['成交额(亿)']}亿")
    inflow_top = sorted([s for s in stocks if s["主力净流入(亿)"] == s["主力净流入(亿)"]], key=lambda x: -x["主力净流入(亿)"])[:20]
    print("--- 主力净流入TOP20 ---")
    for s in inflow_top:
        print(f"{s['代码']} {s['名称']} 涨{s['涨跌%']:.2f}% 主力净流入{s['主力净流入(亿)']}亿")

    print("\n【三、行业板块（东财细分行业）】")
    ind_rows = fetch_paged("m:90+t:2+f:!50", "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f66,f72,f78,f84,f104,f105,f128,f140,f141")
    ind_df = pd.DataFrame(board_rows(ind_rows))
    if not ind_df.empty:
        print("--- 涨幅TOP15 ---")
        print(ind_df.sort_values("涨跌%", ascending=False).head(15).to_string(index=False))
        print("--- 主力净流入TOP15 ---")
        print(ind_df.sort_values("主力净流入(亿)", ascending=False).head(15).to_string(index=False))
        print("--- 跌幅TOP10 ---")
        print(ind_df.sort_values("涨跌%", ascending=True).head(10).to_string(index=False))

    print("\n【四、概念板块】")
    con_rows = fetch_paged("m:90+t:3+f:!50", "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f66,f72,f78,f84,f104,f105,f128,f140,f141")
    con_df = pd.DataFrame(board_rows(con_rows))
    if not con_df.empty:
        print("--- 涨幅TOP15 ---")
        print(con_df.sort_values("涨跌%", ascending=False).head(15).to_string(index=False))
        print("--- 主力净流入TOP15 ---")
        print(con_df.sort_values("主力净流入(亿)", ascending=False).head(15).to_string(index=False))

    print("\n【五、涨停池】")
    try:
        zt = ak.stock_zt_pool_em(date=args.date)
        zt_summary = format_zt_pool(zt, today)
        if zt_summary:
            print("涨停总数:", zt_summary["total"], " 竞价(09:25)涨停:", zt_summary["jingjia_total"])
            print("--- 涨停家数行业分布TOP12 ---")
            print(zt_summary["by_board"].to_string(index=False))
            print("--- 连板高度TOP12 ---")
            print(zt_summary["top_liangban"][["代码", "名称", "所属行业", "连板数", "首次封板时间", "封板资金"]].to_string(index=False))
            print("--- 09:25竞价封板个股（按封单） ---")
            print(zt_summary["auction_sealed"][["代码", "名称", "所属行业", "连板数", "封板资金", "首次封板时间"]].to_string(index=False))
    except Exception as exc:
        print("涨停池获取失败:", repr(exc))

    print("\n【六、当日财经快讯（相关性过滤）】")
    for n in fetch_news(today):
        print(f"[{n['时间']}] {n['标题']}")
        print("   ", n["摘要"])


if __name__ == "__main__":
    main()
