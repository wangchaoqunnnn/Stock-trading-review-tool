# -*- coding: utf-8 -*-
"""按短线信号框架筛选今日观察池。"""
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
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
        try:
            data = get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
        except Exception:
            time.sleep(1)
            continue
        total = int(data["total"])
        diff = data.get("diff") or []
        rows.extend(diff)
        if len(rows) >= total or not diff:
            break
        pn += 1
        time.sleep(0.1)
    return rows


def fetch_zt_pool(date):
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": 0,
        "pagesize": 500,
        "sort": "fbt:asc",
        "date": date,
    }
    url = "https://push2ex.eastmoney.com/getTopicZTPool?" + urllib.parse.urlencode(params)
    data = get_json(url, headers={"Referer": "https://quote.eastmoney.com/ztb/detail"})
    return data.get("data", {}).get("pool", [])


def to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def main():
    today = datetime.now().strftime("%Y%m%d")
    print("=" * 100)
    print(f"短线观察池筛选  {today}  (收盘数据)")
    print("=" * 100)

    print("\n[1] 拉取全A实时/涨停池/行业板块 ...")
    all_rows = fetch_paged(
        "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f184",
    )
    stocks = []
    for r in all_rows:
        stocks.append(
            {
                "code": r.get("f12"),
                "name": r.get("f14"),
                "pct": to_num(r.get("f3")),
                "amount": to_num(r.get("f6")),
                "turnover": to_num(r.get("f8")),
                "vr": to_num(r.get("f10")),
                "flow": to_num(r.get("f62")),
                "flow_ratio": to_num(r.get("f184")),
                "open": to_num(r.get("f17")),
                "prev": to_num(r.get("f18")),
            }
        )

    pool = fetch_zt_pool(today)
    zt_map = {str(x["c"]).zfill(6): x for x in pool}
    print(f"全A {len(stocks)} 只，涨停 {len(pool)} 只")

    boards = fetch_paged(
        "m:90+t:2+f:!50",
        "f2,f3,f6,f8,f10,f12,f14,f17,f18,f62,f184",
    )
    board_map = {b.get("f14"): b for b in boards}

    # 板块涨停统计
    board_zt = defaultdict(lambda: {"count": 0, "fund": 0.0, "lbcs": [], "fbt_early": 0, "zbc0": 0})
    for x in pool:
        sec = x.get("hybk", "未知")
        b = board_zt[sec]
        b["count"] += 1
        b["fund"] += to_num(x.get("fund")) / 1e8
        b["lbcs"].append(to_num(x.get("lbc")))
        if to_num(x.get("fbt")) <= 100000:
            b["fbt_early"] += 1
        if to_num(x.get("zbc")) == 0:
            b["zbc0"] += 1

    strong_sectors = []
    for sec, b in board_zt.items():
        if b["count"] < 3:
            continue
        bd = board_map.get(sec) or next((v for k, v in board_map.items() if sec in k or k in sec), {})
        bd_pct = to_num(bd.get("f3"))
        bd_flow = to_num(bd.get("f62")) / 1e8
        strong_sectors.append(
            {
                "sector": sec,
                "zt_count": b["count"],
                "fund": b["fund"],
                "max_lbc": max(b["lbcs"]) if b["lbcs"] else 0,
                "early": b["fbt_early"],
                "zbc0": b["zbc0"],
                "board_pct": bd_pct,
                "board_flow": bd_flow,
            }
        )
    strong_sectors.sort(key=lambda x: (-x["zt_count"], -x["fund"]))
    print("\n[2] 板块涨停>=3家的行业")
    for s in strong_sectors:
        print(
            f"{s['sector']} 涨停{s['zt_count']}家 封单合计{s['fund']:.1f}亿 最高连板{s['max_lbc']} "
            f"早盘封板{s['early']}家 未炸板{s['zbc0']}家 板块涨{s['board_pct']:.2f}% 主力净流入{s['board_flow']:.2f}亿"
        )

    valid_sectors = [s["sector"] for s in strong_sectors if s["board_flow"] > 0 and s["board_pct"] > 0]

    print("\n[3] 候选个股（板块>=3家涨停且板块资金为正）")
    candidates = []
    for x in pool:
        sec = x.get("hybk", "")
        code = str(x["c"]).zfill(6)
        if sec not in valid_sectors:
            continue
        fund = to_num(x.get("fund"))
        ltsz = to_num(x.get("ltsz"))
        fbt = to_num(x.get("fbt"))
        zbc = to_num(x.get("zbc"))
        lbc = to_num(x.get("lbc"))
        hs = to_num(x.get("hs"))
        seal_ratio = fund / ltsz * 100 if ltsz and ltsz > 0 else 0
        tags = []
        if fbt <= 92500:
            tags.append("竞价封板")
        elif fbt <= 100000:
            tags.append("早盘首板")
        if zbc == 0:
            tags.append("未炸板")
        if seal_ratio >= 3:
            tags.append(f"封单/流通{seal_ratio:.1f}%")
        if lbc >= 3:
            tags.append(f"{int(lbc)}连板")
        candidates.append(
            {
                "code": code,
                "name": x.get("n"),
                "sector": sec,
                "pct": to_num(x.get("zdp")),
                "lbc": int(lbc) if lbc == lbc else 0,
                "fbt": fbt,
                "zbc": int(zbc) if zbc == zbc else 0,
                "hs": hs,
                "fund": fund / 1e8,
                "seal_ratio": seal_ratio,
                "amount": to_num(x.get("amount")) / 1e8,
                "tags": tags,
            }
        )
    candidates.sort(key=lambda x: (x["fbt"], -x["seal_ratio"]))
    for c in candidates[:40]:
        fbt_str = f"{int(c['fbt']):06d}" if c["fbt"] == c["fbt"] else "-"
        print(
            f"{c['code']} {c['name']} {c['sector']} {c['pct']:.2f}% 连板{c['lbc']} "
            f"首封{fbt_str} 炸板{c['zbc']} 换手{c['hs']:.2f}% 封单{c['fund']:.2f}亿 "
            f"封单/流通{c['seal_ratio']:.2f}% {' '.join(c['tags'])}"
        )

    print("\n[4] 非涨停强势股（涨幅>=5%，量比>=2，主力净流入>0，换手5-20%）")
    strong = [
        s for s in stocks
        if s["code"] not in zt_map
        and s["pct"] >= 5
        and s["vr"] >= 2
        and s["flow"] > 0
        and 5 <= s["turnover"] <= 20
        and s["amount"] > 2e8
    ]
    strong.sort(key=lambda x: (-x["flow"], -x["pct"]))
    for s in strong[:25]:
        print(
            f"{s['code']} {s['name']} 涨{s['pct']:.2f}% 量比{s['vr']:.2f} 换手{s['turnover']:.2f}% "
            f"主力净流入{s['flow']/1e8:.2f}亿 成交额{s['amount']/1e8:.2f}亿"
        )

    # 顶部连板高度
    print("\n[5] 今日连板高度榜")
    top_lb = sorted(pool, key=lambda x: (-to_num(x.get("lbc")), -to_num(x.get("fund"))))[:15]
    for x in top_lb:
        print(
            f"{x['c']} {x['n']} {x.get('hybk')} {int(to_num(x.get('lbc')))}连板 "
            f"首封{int(to_num(x.get('fbt'))):06d} 炸板{int(to_num(x.get('zbc')))} 封单{to_num(x.get('fund'))/1e8:.2f}亿"
        )


if __name__ == "__main__":
    main()
