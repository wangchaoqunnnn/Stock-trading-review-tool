# -*- coding: utf-8 -*-
"""实时盘口聚合：大盘情绪、板块过滤器、盘中观察池、买点信号。"""
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .analysis import compute_emotion, time_phase
from .config import INDEX_UT
from .utils import to_num


def fetch_watchlist_ticks(stocks):
    """批量抓取个股分时数据并计算买点信号字段。"""
    def one(s):
        try:
            secid = ("1." if s["code"].startswith("6") else "0.") + s["code"]
            params = {
                "secid": secid,
                "ut": INDEX_UT,
                "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                "iscr": 0, "iscca": 1, "ndays": 1,
            }
            url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get?" + urllib.parse.urlencode(params)
            data = net.http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
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


# 上一轮板块数据，用于计算环比涨跌/资金/涨停数
_RT_PREV = None


def fetch_realtime():
    """实时盘口聚合主函数。"""
    global _RT_PREV

    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {
            "indices": ex.submit(safe, "indices", em.fetch_indices),
            "breadth": ex.submit(safe, "breadth", em.fetch_breadth),
            "zt": ex.submit(safe, "zt", em.fetch_zt_pool),
            "zb": ex.submit(safe, "zb", em.fetch_zb_pool),
            "dt": ex.submit(safe, "dt", em.fetch_dt_pool),
            "industry": ex.submit(safe, "industry", em.fetch_industry_boards),
            "concept": ex.submit(safe, "concept", em.fetch_concept_boards),
            "inflow": ex.submit(safe, "inflow", lambda: em.fetch_stock_flow_top(po=1)),
            "yzt": ex.submit(safe, "yzt", em.fetch_yesterday_zt_perf),
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
    spot_map = em.fetch_spot_map([c["code"] for c in candidates])
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
