# -*- coding: utf-8 -*-
"""短线情绪周期：判断当前市场情绪阶段（冰点/启动/发酵/高潮/退潮）与关键节点。

量化依据（全部来自真实行情数据）：
- 涨停家数、炸板率、跌停家数、连板高度（今日池）
- 晋级率（昨日涨停股今日继续涨停比例）、大面数（昨日涨停今日跌超7%）：
  由"昨日涨停池 + 今日行情"计算
- 龙头股表现：昨日最高板（空间龙头）今日晋级/断板/跌停
- 量能：两市成交额与前一日同时段环比

阶段判定：多因子打分 + 龙头状态修正（区分冰点/退潮）。
节点检测：龙头断板、龙头跌停、启动点、退潮点。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em
from .analysis import compute_emotion
from .emotion_history import emotion_score, fetch_emotion_history
from .snapshot import _prev_amount_at
from .utils import big_loss_pct, limit_pct, to_num

RISK_TEXT = "本文为情绪周期研究参考，不构成任何投资建议。市场有风险，投资需谨慎。"

SPOT_FIELDS = "f2,f3,f12,f14"

# 阶段操作策略（对应文字版）
PHASE_STRATEGY = {
    "冰点": {
        "desc": "情绪极度低迷，亏钱效应显著：涨停少（<30家）、高度低（≤3板）、跌停多、板块快速轮动（电风扇行情）。",
        "action": "空仓或极小仓位试错。市场无明确主线，操作难度极大，耐心等待冰点后的启动信号。",
    },
    "启动": {
        "desc": "亏钱效应收敛、情绪回暖：出现新题材，涨停家数与晋级率回升，首板开始有溢价，可能出现破局龙（首个突破4板）。",
        "action": "轻仓试错。关注新题材首板或1进2个股试探方向；警惕假启动（回暖一天后再度走弱）。",
    },
    "发酵": {
        "desc": "赚钱效应扩散、最赚钱的阶段：主线题材明确，龙头换手走强，板块梯队成型（龙头+中军+跟风）。",
        "action": "上仓位、主升接力。聚焦龙头股与卡位股，敢于在龙头给机会时介入。",
    },
    "高潮": {
        "desc": "情绪见顶、市场狂热：高位股加速、一字板增多、龙头放巨量分歧、人人喊多。",
        "action": "只持不加、准备撤退。最危险阶段，前期利润常在此回吐；只持有现有仓位，时刻准备离场。",
    },
    "退潮": {
        "desc": "赚钱效应急剧消退：炸板率飙升（>30%）、高位股断板跌停、大面（昨涨停今跌超7%）遍地。",
        "action": "空仓或仅轻仓参与低位首板，严禁高位接力；退潮常有反复，不轻易判断反转。",
    },
}


def _prev_trading_date(date=None):
    """最近两个交易日（YYYYMMDD，旧→新）。复用情绪历史的交易日历。"""
    try:
        from .emotion_history import _recent_trading_dates
        dates = _recent_trading_dates(days=2, ref_date=date)
        return dates[-2] if len(dates) >= 2 else None
    except Exception:
        return None


def _yesterday_pool(date=None):
    """昨日涨停池（代码集合 + 最高板龙头）。"""
    prev = _prev_trading_date(date)
    if not prev:
        return None, None, None
    try:
        data = em.fetch_ex_pool("getTopicZTPool", date=prev)
        pool = data.get("pool") or []
        codes = {str(x.get("c")) for x in pool}
        max_lb = max((int(x.get("lbc") or 0) for x in pool), default=0)
        leader = None
        for x in pool:
            if int(x.get("lbc") or 0) == max_lb and max_lb > 0:
                leader = {"code": str(x.get("c")), "name": x.get("n"), "lb": max_lb}
                break
        return prev, codes, leader
    except Exception:
        return None, None, None


def _today_spot(codes):
    """昨日涨停股今日行情（f2现价/f3涨跌幅）。"""
    if not codes:
        return {}
    codes = sorted(codes)
    out = {}
    for i in range(0, len(codes), 50):
        chunk = codes[i:i + 50]
        try:
            m = em.fetch_spot_map(chunk, fields=SPOT_FIELDS)
            for c, row in m.items():
                out[str(c)] = row
        except Exception:
            continue
    return out


def _compute_metrics(zt, zb, dt, spot, total_amount, amount_prev, is_preopen=False):
    """核心量化指标。is_preopen（开盘前/周末）时盘中口径指标不可用。"""
    zt_tc = zt["tc"] or len(zt["pool"])
    zb_tc = zb["tc"] or 0
    dt_tc = dt["tc"] or 0
    zb_rate = round(zb_tc / (zt_tc + zb_tc) * 100, 1) if (zt_tc + zb_tc) else 0.0
    pool = zt.get("pool") or []
    max_lb = max((int(x.get("lbc") or 0) for x in pool), default=0)

    promo = None
    big_loss = None
    promo_rate = None
    prev_total = len(spot) if not is_preopen else None
    if not is_preopen and prev_total:
        promo = 0
        big_loss = 0
        for code, r in spot.items():
            pct = to_num(r.get("f3"))
            if pct != pct:
                continue
            # 逐票按板块口径判定（北交所 30%、创业板·科创板 20%、主板 10%）
            if pct >= limit_pct(code):
                promo += 1
            if pct <= big_loss_pct(code):
                big_loss += 1
        promo_rate = round(promo / prev_total * 100, 1)

    amount_diff_pct = None
    if total_amount and amount_prev:
        amount_diff_pct = round((total_amount / amount_prev - 1) * 100, 1)

    return {
        "zt": zt_tc, "zb": zb_tc, "dt": dt_tc, "zb_rate": zb_rate, "max_lb": max_lb,
        "promo": promo, "promo_rate": promo_rate, "big_loss": big_loss,
        "prev_zt": len(spot) if prev_total else (len(spot) if spot else None),
        "amount_yi": total_amount,
        "amount_diff_pct": amount_diff_pct,
    }


def _phase_of(score, m, prev_phase, leader_status):
    """阶段判定：打分 + 龙头/量能修正。"""
    if leader_status == "limit_down" and m["max_lb"] <= 3:
        return "退潮"  # 龙头跌停 → 旧周期结束
    if leader_status == "break" and m["zb_rate"] > 30:
        return "退潮"  # 龙头断板 + 炸板率高 → 退潮
    if score >= 6:
        return "高潮"
    if score >= 3:
        return "发酵"
    if score >= 0:
        return "启动"
    # score < 0：区分退潮与冰点
    if prev_phase in ("高潮", "发酵", "退潮") and (m["zb_rate"] > 30 or m["big_loss"] >= 15):
        return "退潮"
    return "冰点"


def _score(m):
    s = 0
    zt = m["zt"]
    if zt < 30:
        s -= 2
    elif zt >= 150:
        s += 3
    elif zt >= 100:
        s += 2
    elif zt >= 60:
        s += 1
    if m["zb_rate"] > 40:
        s -= 2
    elif m["zb_rate"] > 30:
        s -= 1
    elif m["zb_rate"] <= 10:
        s += 2
    elif m["zb_rate"] <= 15:
        s += 1
    lb = m["max_lb"]
    if lb <= 2:
        s -= 2
    elif lb == 3:
        s -= 1
    elif lb >= 7:
        s += 2
    elif lb >= 6:
        s += 1
    if m.get("promo_rate") is not None:
        if m["promo_rate"] > 50:
            s += 1
        elif m["promo_rate"] < 15:
            s -= 2
        elif m["promo_rate"] < 30:
            s -= 1
    if m.get("big_loss") is not None:
        if m["big_loss"] >= 30:
            s -= 2
        elif m["big_loss"] >= 15:
            s -= 1
        elif m["big_loss"] <= 5:
            s += 1
    if m["dt"] >= 15:
        s -= 1
    elif m["dt"] <= 3:
        s += 1
    if m["amount_diff_pct"] is not None:
        if m["amount_diff_pct"] >= 10:
            s += 1
        elif m["amount_diff_pct"] <= -10:
            s -= 1
    return s


def _detect_nodes(phase, prev_phase, leader_status, leader_name, m):
    """关键节点检测。"""
    nodes = []
    if leader_status == "limit_down" and leader_name:
        nodes.append({"type": "龙头跌停", "desc": f"空间龙头「{leader_name}」跌停，旧周期结束，资金将流向新题材，关注新周期开启。", "time": datetime.now().strftime("%H:%M:%S")})
    elif leader_status == "break" and leader_name:
        nodes.append({"type": "龙头断板", "desc": f"空间龙头「{leader_name}」断板，资金从高位流向低位，当日2板股成补涨龙概率大增。", "time": datetime.now().strftime("%H:%M:%S")})
    if phase == "启动" and prev_phase in ("冰点", "退潮"):
        nodes.append({"type": "启动点", "desc": "情绪从冰点/退潮回暖：涨停家数与晋级率回升，可轻仓试错新题材首板/1进2。", "time": datetime.now().strftime("%H:%M:%S")})
    if phase == "高潮" and prev_phase in ("启动", "发酵"):
        nodes.append({"type": "高潮点", "desc": "情绪冲顶：只持不加、准备撤退，警惕高位股放量分歧。", "time": datetime.now().strftime("%H:%M:%S")})
    if phase == "退潮" and prev_phase in ("启动", "发酵", "高潮"):
        nodes.append({"type": "退潮点", "desc": "情绪转弱：炸板率/大面数上升，空仓或仅低位首板，严禁高位接力。", "time": datetime.now().strftime("%H:%M:%S")})
    return nodes


def _leader_status(prev_leader, spot):
    """昨日空间龙头今日状态：晋级 / 断板 / 跌停 / 停牌未知。"""
    if not prev_leader:
        return None, None
    row = spot.get(prev_leader["code"])
    if not row:
        return "unknown", prev_leader["name"]
    pct = to_num(row.get("f3"))
    if pct != pct:
        return "unknown", prev_leader["name"]
    thr = limit_pct(prev_leader["code"])
    if pct <= -thr:
        return "limit_down", prev_leader["name"]
    if pct < thr:
        return "break", prev_leader["name"]
    return "up", prev_leader["name"]


def fetch_emotion_cycle(date=None):
    """情绪周期主函数。date 非空时为历史回放。"""
    errors = []
    ds = date.replace("-", "") if date else None

    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=6) as ex:
        f_zt = ex.submit(safe, "zt", lambda: em.fetch_ex_pool("getTopicZTPool", date=ds) if ds else em.fetch_zt_pool())
        f_zb = ex.submit(safe, "zb", lambda: em.fetch_ex_pool("getTopicZBPool", date=ds) if ds else em.fetch_zb_pool())
        f_dt = ex.submit(safe, "dt", lambda: em.fetch_ex_pool("getTopicDTPool", date=ds) if ds else em.fetch_dt_pool())
        f_prev = ex.submit(safe, "prev", lambda: _yesterday_pool(date))
        f_amount = ex.submit(safe, "amount", lambda: em.fetch_market_amount() if not date else None)
        f_eh = ex.submit(safe, "eh", lambda: fetch_emotion_history(date, days=10))
        r_zt = f_zt.result()[1]
        r_zb = f_zb.result()[1]
        r_dt = f_dt.result()[1]
        r_prev = f_prev.result()[1]
        r_amount = f_amount.result()[1]
        r_eh = f_eh.result()[1]

    for r in (r_zt, r_zb, r_dt, r_prev, r_amount, r_eh):
        if isinstance(r, dict) and "error" in r:
            errors.append(r.get("error"))

    def _val(r, default):
        return r if not (isinstance(r, dict) and "error" in r) else default

    zt = _val(r_zt, {"tc": 0, "pool": []})
    zb = _val(r_zb, {"tc": 0, "pool": []})
    dt = _val(r_dt, {"tc": 0, "pool": []})
    prev_date, prev_codes, prev_leader = _val(r_prev, (None, None, None))
    total_amount = _val(r_amount, None)
    eh = _val(r_eh, {"rows": []})

    # 昨日涨停股今日表现（spot 批量）
    spot = _today_spot(prev_codes) if prev_codes else {}

    # 盘前/周末：今日盘中数据未更新（zt=0 属正常），盘中口径指标标注不可用
    now = datetime.now()
    is_preopen = now.strftime("%H:%M") < "09:30" or now.weekday() >= 5

    # 量能环比（实时口径：前一日同时段）
    amount_prev = _prev_amount_at(now.strftime("%Y-%m-%d %H:%M")) if not date else None

    m = _compute_metrics(zt, zb, dt, spot, total_amount, amount_prev, is_preopen)
    score = _score(m)

    # 前一阶段（情绪历史最近一行）
    rows = eh.get("rows") or []
    prev_phase = None
    if rows:
        prev_phase = rows[-1].get("level")

    leader_status, leader_name = _leader_status(prev_leader, spot)
    if is_preopen:
        leader_status = "unknown" if prev_leader else None
    phase = _phase_of(score, m, prev_phase, leader_status)
    nodes = _detect_nodes(phase, prev_phase, leader_status, leader_name, m)

    # 今日空间龙头
    pool = zt.get("pool") or []
    max_lb = m["max_lb"]
    cur_leader = None
    for x in sorted([x for x in pool if int(x.get("lbc") or 0) == max_lb and max_lb > 0],
                    key=lambda x: -(to_num(x.get("fund")) or 0)):
        cur_leader = {"code": str(x.get("c")), "name": x.get("n"), "lb": max_lb, "fund_yi": round(to_num(x.get("fund")) / 100000000, 2)}
        break

    strategy = PHASE_STRATEGY.get(phase, PHASE_STRATEGY["冰点"])
    emo = emotion_score(zt, zb, dt, {"up": 0, "down": 0, "flat": 0})

    note = ""
    if is_preopen and not date:
        note = "当前为开盘前/周末，今日盘中数据未更新（涨停/晋级率/大面等为昨日收盘口径参考），阶段判定仅供参考，开盘后自动刷新。"

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "history_date": date,
        "phase": phase,
        "phase_desc": strategy["desc"],
        "strategy": strategy["action"],
        "score": score,
        "emotion_score": emo.get("score"),
        "note": note,
        "metrics": m,
        "leader": {
            "today": cur_leader,
            "yesterday": prev_leader,
            "status": leader_status,
            "status_text": {
                "up": "昨日龙头今日晋级（空间打开）",
                "break": "昨日龙头今日断板（补涨窗口）",
                "limit_down": "昨日龙头今日跌停（旧周期结束）",
                "unknown": "昨日龙头今日表现数据未更新（盘前或数据暂缺）",
                None: "无昨日龙头",
            }.get(leader_status, ""),
        },
        "nodes": nodes,
        "history": {
            "rows": rows,
            "prev_phase": prev_phase,
        },
        "risk": RISK_TEXT,
        "errors": errors,
    }
