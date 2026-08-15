# -*- coding: utf-8 -*-
"""纯计算逻辑：情绪指标、信号检查表、观察池、时间窗口与扫描分类/评分。

不发起任何网络请求，便于单元测试与等价性验证。
"""
from datetime import datetime

from .utils import to_num


def time_phase():
    """根据当前时间给出盘中阶段提示。"""
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


def compute_emotion(zt, zb, dt):
    """市场情绪指标：涨停/炸板/跌停家数、竞价涨停、最高连板、炸板率。"""
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
    """涨停池汇总：行业分布、连板梯队、竞价封板。"""
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
    """短线框架信号检查表（满足/未满足）。"""
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
    """每日复盘观察池：连板/资金靠前的涨停股 + 主力净流入榜补充。"""
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


# ---------- 量价异动分类 ----------

VOLPRICE_CATEGORIES = ["放量上攻", "放量滞涨", "冲高回落", "缩量上涨", "放量下跌", "缩量回踩"]


def categorize_volprice(candidates):
    """把候选股按量价特征分入六类（可多类命中），每类排序并截断 30 只。"""
    cats = {k: [] for k in VOLPRICE_CATEGORIES}
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
    return cats


# ---------- 涨停回踩筛选 ----------

def limit_threshold(code):
    """按代码段返回涨停幅度阈值。"""
    if code.startswith(("4", "8", "92")):
        return 29.5
    if code.startswith(("3", "68")):
        return 19.5
    return 9.8


def build_hot_sectors(industry, zt_pool):
    """市场热点板块集合：板块涨跌与主力净流入为正，或板块当日有涨停。"""
    zt_by_industry = {}
    for x in zt_pool:
        b = x.get("hybk") or "未知"
        zt_by_industry[b] = zt_by_industry.get(b, 0) + 1
    hot_set = {
        b["name"] for b in industry
        if (b.get("flow_yi") or 0) > 0 and (b.get("pct") or 0) > 0
        or zt_by_industry.get(b["name"], 0) >= 1
    }
    return hot_set, zt_by_industry


def evaluate_pullback(c, hist, hot_set, board_flow_map):
    """评估单只候选是否满足"20日内涨停+上升趋势+缩量回踩不破+市场热点"，命中返回结果 dict。"""
    if len(hist) < 25:
        return None
    code = c["code"]
    threshold = limit_threshold(code)
    last20 = hist[-20:]
    limit_idx = None
    for i in range(len(last20) - 1, -1, -1):
        if (last20[i].get("pct") or 0) >= threshold:
            limit_idx = i
            break
    if limit_idx is None:
        return None
    limit_bar = last20[limit_idx]
    today = hist[-1]
    vols = [h["volume"] for h in hist]
    closes = [h["close"] for h in hist]
    lows = [h["low"] for h in hist]
    prev5 = vols[-6:-1]
    prev5_avg = sum(prev5) / len(prev5) if prev5 else 0
    hist_vr = round(today["volume"] / prev5_avg, 2) if prev5_avg else None
    if hist_vr is None or hist_vr > 0.85:
        return None
    ma20 = sum(closes[-20:]) / 20
    ma20_prev5 = sum(closes[-25:-5]) / 20 if len(closes) >= 25 else None
    close = today["close"]
    if close <= ma20:
        return None
    if ma20_prev5 is not None and ma20 <= ma20_prev5:
        return None
    recent_low = min(lows[-5:])
    prior_low = min(lows[-15:-5])
    if recent_low <= prior_low * 0.98:
        return None
    support = min(limit_bar["low"], limit_bar["close"])
    if today["low"] < support * 0.98:
        return None
    days_since = (len(last20) - 1) - limit_idx
    if days_since <= 0:
        return None
    hot = c.get("industry") in hot_set
    shrink = round((1 - hist_vr) * 10, 1) if hist_vr else 5
    trend = (5 if close > ma20 else 0) + (3 if (ma20_prev5 is not None and ma20 > ma20_prev5) else 0)
    recency = 5 if days_since <= 5 else 2 if days_since <= 10 else 1
    score = round(shrink + trend + recency + (8 if hot else 0), 1)
    tags = ["20日涨停", "上升趋势", "缩量回踩"]
    if hot:
        tags.append("市场热点")
    return {
        "code": code, "name": c["name"],
        "price": round(close, 2), "pct": c["pct"], "speed": c["speed"],
        "vol_ratio": c["vol_ratio"], "hist_vol_ratio": hist_vr,
        "turnover": c["turnover"], "amount_yi": c["amount_yi"],
        "main_flow": c["main_flow"], "industry": c.get("industry"),
        "ma20": round(ma20, 2), "board_flow": round(board_flow_map.get(c.get("industry"), 0), 2),
        "limit_date": limit_bar["date"], "limit_pct": round(limit_bar.get("pct") or 0, 2),
        "days_since": days_since, "hot": hot, "score": score, "tags": tags,
    }
