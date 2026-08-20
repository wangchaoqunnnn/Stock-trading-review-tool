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


# ---------- 连续资金净流入/流出 ----------

MIN_STREAK_DAYS = 3


def parse_fflow_rows(lines):
    """解析东方财富主力资金流历史（daykline）行。

    每行: 日期,主力净流入,小单,中单,大单,超大单,主力占比%,小单占比,中单占比,
    大单占比,超大单占比,收盘价,涨跌幅,0,0
    """
    out = []
    for line in lines:
        p = line.split(",")
        if len(p) < 13:
            continue
        out.append({
            "date": p[0],
            "main_flow": to_num(p[1]),
            "main_pct": to_num(p[6]),
            "close": to_num(p[11]),
            "pct": to_num(p[12]),
        })
    return out


def trailing_days(rows, predicate):
    """从最新一天往前数，连续满足 predicate 的天数。"""
    n = 0
    for r in reversed(rows):
        if predicate(r):
            n += 1
        else:
            break
    return n


def trailing_inflow_days(rows):
    """主力资金连续净流入天数（含当日）。"""
    return trailing_days(rows, lambda r: r["main_flow"] > 0)


def trailing_outflow_days(rows):
    """主力资金连续净流出天数（含当日）。"""
    return trailing_days(rows, lambda r: r["main_flow"] < 0)


def streak_flow_sum(rows, n):
    """最近 n 天（含当日）主力资金净流入合计，单位元。"""
    return sum(r["main_flow"] for r in rows[-n:])


# ---------- 连续小幅放量阳线 + 上升趋势 ----------

# 温和放量：成交量较前一日放大 5%~150%
YANG_VOL_MIN = 1.05
YANG_VOL_MAX = 2.5


def yang_streak(hist):
    """从最新一天往前数，连续"阳线 + 温和放量"的天数。"""
    n = 0
    for i in range(len(hist) - 1, 0, -1):
        cur = hist[i]
        prev = hist[i - 1]
        if cur["close"] > cur["open"] and prev["volume"] > 0:
            ratio = cur["volume"] / prev["volume"]
            if YANG_VOL_MIN <= ratio <= YANG_VOL_MAX:
                n += 1
            else:
                break
        else:
            break
    return n


def is_uptrend(hist):
    """上升趋势：收盘站上 MA20 且 MA20 走高。"""
    if len(hist) < 25:
        return False
    closes = [h["close"] for h in hist]
    ma20 = sum(closes[-20:]) / 20
    ma20_prev = sum(closes[-25:-5]) / 20
    return closes[-1] > ma20 and ma20 > ma20_prev


def pct_5d(hist):
    """近 5 个交易日累计涨幅（%）。"""
    if len(hist) < 6:
        return None
    base = hist[-6]["close"]
    return round((hist[-1]["close"] / base - 1) * 100, 2) if base else None


# ---------- 涨停后形态：横盘震荡 / 上升趋势 ----------

# 横盘震荡判定参数
SIDEWAYS_RANGE = 0.15     # 近10日振幅上限（最高-最低）/最低
SIDEWAYS_MA_BAND = 0.05   # 收盘价偏离 MA20 上限
SIDEWAYS_MA_FLAT = 0.03   # MA20 走平阈值（相对5日前）


def is_sideways(hist):
    """横盘震荡：近10日振幅收敛、价格贴近走平的 MA20。"""
    if len(hist) < 25:
        return False
    closes = [h["close"] for h in hist]
    highs = [h["high"] for h in hist]
    lows = [h["low"] for h in hist]
    ma20 = sum(closes[-20:]) / 20
    ma20_prev5 = sum(closes[-25:-5]) / 20
    if ma20 <= 0 or ma20_prev5 <= 0:
        return False
    recent_high = max(highs[-10:])
    recent_low = min(lows[-10:])
    if recent_low <= 0:
        return False
    rng = (recent_high - recent_low) / recent_low
    close = closes[-1]
    return (
        rng <= SIDEWAYS_RANGE
        and abs(close / ma20 - 1) <= SIDEWAYS_MA_BAND
        and abs(ma20 / ma20_prev5 - 1) <= SIDEWAYS_MA_FLAT
    )


def classify_state(hist):
    """涨停后当前状态：uptrend（上升趋势）/ sideways（横盘震荡）/ downtrend（下降趋势）。"""
    if is_uptrend(hist):
        return "uptrend"
    if is_sideways(hist):
        return "sideways"
    return "downtrend"


STATE_LABELS = {"uptrend": "上升趋势", "sideways": "横盘震荡", "downtrend": "下降趋势"}


# ---------- 支撑位有效性（回测验证规则） ----------
# 回测结论：仅"回踩+收盘站稳"胜率≈50%不可行；叠加"缩量回踩 + 次日放量阳线
# 确认"后 3 日胜率 78%/5 日 72%（样本 423，scripts/backtest_support.py 可复现）。

SUPPORT_WINDOW = 60     # 支撑位：近 60 日最低点（箱体下沿/前低）
SUPPORT_TOUCH = 0.02    # 回踩触及容忍：low <= S * 1.02
SUPPORT_FLOOR = 0.98    # 收盘站稳：close >= S * 0.98
SUPPORT_SHRINK = 0.9    # 缩量：vol <= 前5日均量 * 0.9
CONFIRM_VOL = 1.0       # 确认日放量：vol >= 前5日均量


def support_level(hist, window=SUPPORT_WINDOW, exclude=1):
    """支撑位：最近 window 日最低价（不含最近 exclude 日）。"""
    if len(hist) < window + exclude:
        return None
    lows = [h["low"] for h in hist[-(window + exclude):-exclude] if h["low"] > 0]
    return min(lows) if lows else None


def is_pullback_signal(hist, i, window=SUPPORT_WINDOW, touch=SUPPORT_TOUCH,
                       floor=SUPPORT_FLOOR, shrink=SUPPORT_SHRINK):
    """t=i 日是否为"缩量回踩支撑"信号日：触及支撑 + 收盘站稳 + 缩量。"""
    if i < window or i >= len(hist):
        return False, None, None
    S = support_level(hist[:i + 1], window=window, exclude=1)
    if not S:
        return False, None, None
    t = hist[i]
    if not (t["low"] <= S * (1 + touch) and t["close"] >= S * floor):
        return False, None, None
    prev5 = hist[max(0, i - 5):i]
    prev5_avg = sum(h["volume"] for h in prev5) / len(prev5) if prev5 else 0
    if prev5_avg <= 0:
        return False, None, None
    ratio = t["volume"] / prev5_avg
    if ratio > shrink:
        return False, None, None
    return True, S, ratio


def is_confirm_day(hist, i, vol_ratio=CONFIRM_VOL):
    """t=i 日是否为确认日：放量阳线（收盘>开盘 且 量 ≥ 前5日均量）。"""
    if i <= 0 or i >= len(hist):
        return False, None
    t = hist[i]
    prev5 = hist[max(0, i - 5):i]
    prev5_avg = sum(h["volume"] for h in prev5) / len(prev5) if prev5 else 0
    if prev5_avg <= 0:
        return False, None
    ratio = t["volume"] / prev5_avg
    return (t["close"] > t["open"] and ratio >= vol_ratio), ratio


def support_confirmed_recent(hist, max_lag=3):
    """最近 max_lag 个交易日内是否完成"缩量回踩支撑 + 次日放量阳线确认"。

    返回 (信号日索引, 确认日索引, 支撑位, 信号缩量比, 确认量比) 或 None。
    """
    for lag in range(1, max_lag + 1):
        sig = len(hist) - 1 - lag
        cfm = sig + 1
        if sig < 1 or cfm >= len(hist):
            continue
        ok_s, S, shrink_r = is_pullback_signal(hist, sig)
        if not ok_s:
            continue
        ok_c, cfm_r = is_confirm_day(hist, cfm)
        if ok_c:
            return sig, cfm, S, shrink_r, cfm_r
    return None


# ---------- 突破新高判定 ----------

def ma_of(hist, n):
    """最近 n 日均线（收盘价）。数据不足返回 None。"""
    if len(hist) < n:
        return None
    return sum(h["close"] for h in hist[-n:]) / n


def vol_shrink_ratio(hist, n=5):
    """今日成交量 / 前 n 日均量（不含当日）的比值，用于"缩量回踩"判定。"""
    if len(hist) < n + 1:
        return None
    prev = hist[-(n + 1):-1]
    avg = sum(h["volume"] for h in prev) / n if n else 0
    if avg <= 0:
        return None
    return today_volume(hist) / avg


def today_volume(hist):
    return hist[-1]["volume"] if hist else 0


def pullback_to_ma(hist, n, touch=0.005, floor=0.985, shrink=0.9):
    """上升趋势中缩量回踩 n 日均线：盘中最低触及均线附近，收盘未明显跌破，
    且当日成交量缩量（≤前5日均量×shrink，默认0.9）。

    返回 (是否回踩, 均线值)；非上升趋势或数据不足返回 (None, None)。
    touch: 最低价相对均线的触及容忍（1+0.5% 内算触及）
    floor: 收盘相对均线的最低容忍（跌破 1.5% 以上不算回踩支撑）
    shrink: 缩量阈值（今日量 ≤ 前5日均量 × shrink 才算缩量回踩）
    """
    if len(hist) < max(n, 25) or not is_uptrend(hist):
        return None, None
    ma = ma_of(hist, n)
    if not ma or ma <= 0:
        return None, None
    today = hist[-1]
    prev5 = hist[-6:-1]
    prev5_avg = sum(h["volume"] for h in prev5) / len(prev5) if prev5 else 0
    if prev5_avg <= 0:
        return None, None
    vol_ok = today["volume"] <= prev5_avg * shrink
    if today["low"] <= ma * (1 + touch) and today["close"] >= ma * floor and vol_ok:
        return True, ma
    return False, ma


def breakout_short(hist, days=20):
    """突破近 days 日最高价。

    返回 (是否突破, 前高) 或 None（数据不足）。
    """
    if len(hist) < days + 2:
        return None
    today = hist[-1]
    prev_high = max(h["high"] for h in hist[-(days + 1):-1])
    if prev_high <= 0:
        return None
    return today["high"] > prev_high, prev_high


def breakout_hist(hist):
    """突破可得历史最高价（除今日外的全部K线）。

    返回 (是否突破, 前历史高) 或 None（数据不足）。
    """
    if len(hist) < 30:
        return None
    today = hist[-1]
    prev_high = max(h["high"] for h in hist[:-1])
    if prev_high <= 0:
        return None
    return today["high"] > prev_high, prev_high
